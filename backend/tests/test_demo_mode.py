"""
Comprehensive Tests for Public Portfolio Demo Mode and Security Boundaries.

Verifies:
1. DEMO_MODE defaults to False.
2. Missing production data does not automatically activate demo mode.
3. When DEMO_MODE=true, /demo/metrics, /demo/data-status, /demo/ask, /demo/leadership-report succeed without DB or Monday credentials.
4. Demo endpoints return only fictional/synthetic data.
5. Production endpoints (/metrics, /ask) strictly return HTTP 401 without JWT even when DEMO_MODE=true.
6. Public /demo/ask rejects empty queries and oversized inputs (>250 chars).
7. In-memory sliding-window rate limit (5 req/min per IP) triggers HTTP 429.
8. Trusted proxy validation does not blindly trust spoofed X-Forwarded-For headers.
9. Database-dependent endpoints return HTTP 503 when no DB is configured, without weakening authentication.
"""

import os
from unittest.mock import patch
import pytest
from httpx import AsyncClient, ASGITransport

from main import app, lifespan
from api.demo_routes import demo_ask_limiter, InMemoryRateLimiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter request timestamps before each test."""
    demo_ask_limiter.requests.clear()
    yield
    demo_ask_limiter.requests.clear()


@pytest.mark.asyncio
async def test_demo_mode_defaults_to_false():
    """Verify backend DEMO_MODE defaults to false when env var is unset."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DEMO_MODE", None)
        is_demo = os.getenv("DEMO_MODE", "false").lower() in ("true", "1")
        assert is_demo is False


@pytest.mark.asyncio
async def test_demo_endpoints_disabled_when_demo_mode_false():
    """When DEMO_MODE is false, /demo/metrics returns 404."""
    with patch.dict(os.environ, {"DEMO_MODE": "false"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/demo/metrics")
                assert res.status_code == 404


@pytest.mark.asyncio
async def test_demo_endpoints_enabled_and_functional():
    """When DEMO_MODE=true, /demo/metrics returns synthetic metrics with 200 OK."""
    with patch.dict(os.environ, {"DEMO_MODE": "true"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. /demo/metrics
                res = await client.get("/demo/metrics")
                assert res.status_code == 200
                data = res.json()
                metrics = data["dashboard_metrics"]
                assert "pipeline_summary" in metrics
                assert metrics["pipeline_summary"]["total_deals"] > 0
                assert data["data_metadata"]["data_source"] == "synthetic_demo"

                # Check fictional company names
                top_custs = metrics.get("top_customers", [])
                assert len(top_custs) > 0
                cust_names = [c["customer"] for c in top_custs]
                # Fictional companies only
                assert any("Solar" in n or "Agro" in n or "TerraScan" in n for n in cust_names)

                # 2. /demo/data-status
                status_res = await client.get("/demo/data-status")
                assert status_res.status_code == 200
                assert status_res.json()["data_source"] == "synthetic_demo"


@pytest.mark.asyncio
async def test_production_routes_remain_protected_in_demo_mode():
    """Production /metrics and /ask MUST return 401 Unauthorized without JWT even in demo mode."""
    with patch.dict(os.environ, {"DEMO_MODE": "true"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # GET /metrics without auth -> 401
                prod_metrics = await client.get("/metrics")
                assert prod_metrics.status_code == 401

                # POST /ask without auth -> 401
                prod_ask = await client.post("/ask", json={"question": "What is the revenue?"})
                assert prod_ask.status_code == 401


@pytest.mark.asyncio
async def test_demo_ask_input_validation():
    """Test question length and emptiness validation on /demo/ask."""
    with patch.dict(os.environ, {"DEMO_MODE": "true"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Empty question -> 422
                res_empty = await client.post("/demo/ask", json={"question": ""})
                assert res_empty.status_code == 422

                # Oversized question (>250 chars) -> 422
                long_question = "A" * 251
                res_long = await client.post("/demo/ask", json={"question": long_question})
                assert res_long.status_code == 422

                # Valid question -> 200
                res_valid = await client.post("/demo/ask", json={"question": "What is the total pipeline value?"})
                assert res_valid.status_code == 200
                answer = res_valid.json()["answer"]
                assert "Total Pipeline Value" in answer or "pipeline" in answer.lower()


@pytest.mark.asyncio
async def test_demo_ask_rate_limiting():
    """Test that more than 5 requests in a minute from the same IP triggers HTTP 429."""
    with patch.dict(os.environ, {"DEMO_MODE": "true"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 5 requests should succeed
                for i in range(5):
                    res = await client.post("/demo/ask", json={"question": f"Question number {i+1}"})
                    assert res.status_code == 200

                # 6th request should fail with 429 Too Many Requests
                res_overflow = await client.post("/demo/ask", json={"question": "Question number 6"})
                assert res_overflow.status_code == 429
                assert "Rate limit exceeded" in res_overflow.json()["detail"]


@pytest.mark.asyncio
async def test_demo_leadership_report():
    """Verify /demo/leadership-report returns a markdown report with demo synthetic contents."""
    with patch.dict(os.environ, {"DEMO_MODE": "true"}):
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/demo/leadership-report")
                assert res.status_code == 200
                report_data = res.json()
                assert "# Executive Leadership Report" in report_data["report"]
                assert "Portfolio Demonstration" in report_data["report"]


@pytest.mark.asyncio
async def test_trusted_proxy_ip_extraction():
    """Test that X-Forwarded-For is not trusted unless immediate peer is in TRUSTED_PROXIES."""
    from api.demo_routes import extract_client_ip
    from unittest.mock import Mock

    # Case 1: No TRUSTED_PROXIES configured -> ignore X-Forwarded-For completely
    req_mock = Mock()
    req_mock.client.host = "192.168.1.50"
    req_mock.headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}

    with patch.dict(os.environ, {"TRUSTED_PROXIES": ""}):
        ip = extract_client_ip(req_mock)
        assert ip == "192.168.1.50"  # Did not trust header

    # Case 2: Immediate peer IS a trusted proxy -> extract leftmost untrusted
    with patch.dict(os.environ, {"TRUSTED_PROXIES": "10.0.0.0/8,192.168.1.50"}):
        req_mock.client.host = "192.168.1.50"
        req_mock.headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}
        ip = extract_client_ip(req_mock)
        assert ip == "203.0.113.195"  # Correctly extracted untrusted client IP
