import os
import sys
from unittest.mock import MagicMock
import pandas as pd

from fastapi.testclient import TestClient

# Path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app


def test_api_endpoints():
    with TestClient(app) as client:
        # 1. Test GET /
        res_root = client.get("/")
        assert res_root.status_code == 200
        assert res_root.json() == {"message": "Business Intelligence Agent API"}
        print("test GET / PASSED")

        # 2. Test GET /health
        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "healthy"}
        print("test GET /health PASSED")

        # 3. Test GET /metrics
        res_metrics = client.get("/metrics")
        assert res_metrics.status_code == 200
        data = res_metrics.json()
        assert "dashboard_metrics" in data
        assert "pipeline_summary" in data["dashboard_metrics"]
        print("test GET /metrics PASSED")

        # 4. Test POST /ask with mocked BI Agent
        mock_agent = MagicMock()
        mock_agent.answer_question.return_value = {
            "answer": "Mocked analysis for question",
            "dashboard_metrics": {},
            "data_quality_notes": ["Note 1"],
        }
        app.state.bi_agent = mock_agent

        res_ask = client.post("/ask", json={"question": "What is our revenue?"})
        assert res_ask.status_code == 200
        ask_data = res_ask.json()
        assert ask_data["answer"] == "Mocked analysis for question"
        assert ask_data["data_quality_notes"] == ["Note 1"]
        print("test POST /ask PASSED")

        # 5. Test GET /leadership-report with mocked BI Agent
        mock_agent.generate_leadership_report.return_value = {
            "report": "# Executive Summary\nMock report.",
            "generated_at": "2026-07-21T00:00:00Z",
        }
        res_report = client.get("/leadership-report")
        assert res_report.status_code == 200
        report_data = res_report.json()
        assert "# Executive Summary" in report_data["report"]
        assert report_data["generated_at"] == "2026-07-21T00:00:00Z"
        print("test GET /leadership-report PASSED")


if __name__ == "__main__":
    test_api_endpoints()
    print("\nALL FASTAPI ENDPOINT TESTS PASSED SUCCESSFULLY!")
