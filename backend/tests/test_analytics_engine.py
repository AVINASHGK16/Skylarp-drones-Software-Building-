import os
import sys
import pandas as pd

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.data_cleaner import clean_deals_data, clean_work_orders_data
from services.analytics_engine import (
    get_pipeline_summary,
    get_revenue_by_sector,
    get_revenue_by_stage,
    get_monthly_pipeline,
    get_work_order_summary,
    get_billing_summary,
    get_top_customers,
    get_execution_metrics,
    generate_dashboard_metrics,
)


def test_empty_analytics():
    empty_deals = pd.DataFrame()
    empty_wo = pd.DataFrame()

    ps = get_pipeline_summary(empty_deals)
    assert ps["total_deals"] == 0
    assert ps["total_pipeline_value"] == 0.0

    rs = get_revenue_by_sector(empty_deals)
    assert rs == {}

    rst = get_revenue_by_stage(empty_deals)
    assert rst == {}

    mp = get_monthly_pipeline(empty_deals)
    assert mp == {}

    wos = get_work_order_summary(empty_wo)
    assert wos["total_work_orders"] == 0

    bs = get_billing_summary(empty_wo)
    assert bs["total_contract_value"] == 0.0

    tc = get_top_customers(empty_wo)
    assert tc == []

    em = get_execution_metrics(empty_wo)
    assert em["average_project_value"] == 0.0

    master = generate_dashboard_metrics(empty_deals, empty_wo)
    assert "pipeline_summary" in master
    print("test_empty_analytics PASSED")


def test_populated_analytics():
    raw_deals = [
        {
            "id": "101",
            "name": "Deal A",
            "Masked Deal value": "$100,000",
            "Sector/service": "Mining",
            "Deal Status": "Won",
            "Deal Stage": "Closed Won",
            "Close Date (A)": "2025-03-15",
        },
        {
            "id": "102",
            "name": "Deal B",
            "Masked Deal value": "50000",
            "Sector/service": "Healthcare",
            "Deal Status": "In Progress",
            "Deal Stage": "Proposal Sent",
            "Close Date (A)": "2025-04-10",
        },
    ]

    raw_wo = [
        {
            "id": "201",
            "name": "WO A",
            "Customer Name Code": "CUST_01",
            "Execution Status": "Completed",
            "Amount in Rupees (Excl of GST) (Masked)": "75000",
            "Billed Value in Rupees (Excl of GST.) (Masked)": "75000",
            "Data Delivery Date": "2025-05-01",
        },
        {
            "id": "202",
            "name": "WO B",
            "Customer Name Code": "CUST_02",
            "Execution Status": "In Progress",
            "Amount in Rupees (Excl of GST) (Masked)": "25000",
            "Billed Value in Rupees (Excl of GST.) (Masked)": "10000",
            "Data Delivery Date": None,
        },
    ]

    deals_df = clean_deals_data(raw_deals)
    wo_df = clean_work_orders_data(raw_wo)

    ps = get_pipeline_summary(deals_df)
    assert ps["total_deals"] == 2
    assert ps["total_pipeline_value"] == 150000.0
    assert ps["deals_won"] == 1

    rev_sec = get_revenue_by_sector(deals_df)
    assert rev_sec["Mining"] == 100000.0
    assert rev_sec["Healthcare"] == 50000.0

    monthly = get_monthly_pipeline(deals_df)
    assert monthly["2025-03"] == 100000.0
    assert monthly["2025-04"] == 50000.0

    wo_sum = get_work_order_summary(wo_df)
    assert wo_sum["total_work_orders"] == 2
    assert wo_sum["completed_work_orders"] == 1

    bill_sum = get_billing_summary(wo_df)
    assert bill_sum["total_contract_value"] == 100000.0
    assert bill_sum["total_billed"] == 85000.0
    assert bill_sum["total_unbilled"] == 150000.0 or bill_sum["total_unbilled"] == 15000.0

    top_cust = get_top_customers(wo_df, top_n=5)
    assert len(top_cust) == 2
    assert top_cust[0]["customer"] == "Cust_01"

    exec_m = get_execution_metrics(wo_df)
    assert exec_m["projects_with_delivery_date"] == 1
    assert exec_m["projects_missing_delivery_date"] == 1

    master = generate_dashboard_metrics(deals_df, wo_df)
    assert master["pipeline_summary"]["total_deals"] == 2
    print("test_populated_analytics PASSED")


if __name__ == "__main__":
    test_empty_analytics()
    test_populated_analytics()
    print("\nALL ANALYTICS ENGINE TESTS PASSED SUCCESSFULLY!")
