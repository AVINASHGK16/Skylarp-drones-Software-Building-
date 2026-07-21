import os
import sys
import pandas as pd
from unittest.mock import MagicMock, patch

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.bi_agent import BIAgent


def test_bi_agent_init():
    # Test missing API key raises ValueError
    try:
        agent = BIAgent(api_key="")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print("test_bi_agent_init missing key test PASSED:", e)

    # Test explicit API key initialization with Gemini
    agent = BIAgent(api_key="fake-gemini-key")
    assert agent.model == "gemini-2.5-flash"
    print("test_bi_agent_init initialization PASSED")


def test_build_context():
    agent = BIAgent(api_key="fake-gemini-key")
    mock_metrics = {
        "pipeline_summary": {"total_pipeline_value": 1000.0, "total_deals": 5},
        "revenue_by_sector": {"Mining": 1000.0},
        "revenue_by_stage": {"Won": 1000.0},
        "monthly_pipeline": {"2025-01": 1000.0},
        "work_order_summary": {"total_work_orders": 2},
        "billing_summary": {"total_contract_value": 500.0},
        "top_customers": [{"customer": "C1", "revenue": 500.0}],
        "execution_metrics": {"projects_with_delivery_date": 2},
    }
    mock_report = {"caveats": ["Sample caveat test"]}

    context = agent._build_context(mock_metrics, mock_report)
    assert "=== BUSINESS ANALYTICS METRICS CONTEXT ===" in context
    assert "Mining" in context
    assert "Sample caveat test" in context
    print("test_build_context PASSED")


@patch("services.bi_agent.genai.Client")
def test_answer_question_mocked(mock_genai_client_cls):
    # Setup mock Gemini client response
    mock_client = MagicMock()
    mock_genai_client_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "Analysis: Total pipeline value is strong at 100k."
    mock_client.models.generate_content.return_value = mock_response

    agent = BIAgent(api_key="fake-gemini-key")
    deals_df = pd.DataFrame([{"Masked Deal value": 100000.0, "Deal Status": "Won"}])
    wo_df = pd.DataFrame([{"Amount in Rupees (Excl of GST) (Masked)": 50000.0}])

    res = agent.answer_question("What is our total pipeline?", deals_df, wo_df)
    assert "answer" in res
    assert "dashboard_metrics" in res
    assert "data_quality_notes" in res
    assert "Total pipeline value is strong" in res["answer"]
    print("test_answer_question_mocked PASSED")


@patch("services.bi_agent.genai.Client")
def test_generate_leadership_report_mocked(mock_genai_client_cls):
    mock_client = MagicMock()
    mock_genai_client_cls.return_value = mock_client

    mock_report_content = (
        "# Executive Summary\nSummary text.\n\n"
        "# Sales Pipeline Health\nPipeline text.\n\n"
        "# Revenue Insights\nRevenue text.\n\n"
        "# Operational Performance\nOps text.\n\n"
        "# Billing Overview\nBilling text.\n\n"
        "# Key Risks\nRisks text.\n\n"
        "# Recommended Actions\nActions text.\n\n"
        "# Data Quality Notes\nQuality text."
    )
    mock_response = MagicMock()
    mock_response.text = mock_report_content
    mock_client.models.generate_content.return_value = mock_response

    agent = BIAgent(api_key="fake-gemini-key")
    deals_df = pd.DataFrame()
    wo_df = pd.DataFrame()

    res = agent.generate_leadership_report(deals_df, wo_df)
    assert "report" in res
    assert "generated_at" in res
    assert "# Executive Summary" in res["report"]
    assert "# Recommended Actions" in res["report"]
    print("test_generate_leadership_report_mocked PASSED")


if __name__ == "__main__":
    test_bi_agent_init()
    test_build_context()
    test_answer_question_mocked()
    test_generate_leadership_report_mocked()
    print("\nALL BI AGENT UNIT TESTS PASSED SUCCESSFULLY!")
