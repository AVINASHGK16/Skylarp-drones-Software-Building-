import sys
import os
import pandas as pd

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.data_cleaner import (
    clean_deals_data,
    clean_work_orders_data,
    generate_data_quality_report,
)


def test_empty_inputs():
    empty_deals = clean_deals_data([])
    assert empty_deals.empty
    assert list(empty_deals.columns) == [
        "id",
        "name",
        "Masked Deal value",
        "Close Date (A)",
        "Tentative Close Date",
        "Created Date",
        "Sector/service",
        "Deal Status",
        "Closure Probability",
        "Deal Stage",
    ]

    empty_wo = clean_work_orders_data([])
    assert empty_wo.empty
    print("test_empty_inputs PASSED")


def test_clean_deals():
    raw_deals = [
        {
            "id": "101",
            "name": "Deal Alpha",
            "masked deal value": "$123,456.78",
            "CLOSE DATE (a)": "2026-05-15",
            "sector/service": "  drones & software  ",
            "Deal Status": "WON",
        },
        {
            "id": "102",
            "name": "Deal Beta",
            "masked deal value": None,
            "CLOSE DATE (a)": "invalid date",
        },
    ]
    df_deals = clean_deals_data(raw_deals)
    assert df_deals.loc[0, "Masked Deal value"] == 123456.78
    assert df_deals.loc[0, "Close Date (A)"] == "2026-05-15"
    assert df_deals.loc[0, "Sector/service"] == "Drones & Software"
    assert df_deals.loc[1, "Masked Deal value"] == 0.0
    assert pd.isna(df_deals.loc[1, "Close Date (A)"])
    assert df_deals.loc[1, "Deal Stage"] == "Unspecified"
    print("test_clean_deals PASSED")


def test_clean_work_orders():
    raw_wo = [
        {
            "id": "201",
            "name": "WO Alpha",
            "Amount in Rupees (Excl of GST) (Masked)": "Rs. 50,000.00",
            "execution status": "in progress",
        }
    ]
    df_wo = clean_work_orders_data(raw_wo)
    assert df_wo.loc[0, "Amount in Rupees (Excl of GST) (Masked)"] == 50000.0
    assert df_wo.loc[0, "Execution Status"] == "In Progress"
    print("test_clean_work_orders PASSED")


def test_quality_report():
    df_deals = clean_deals_data([{"id": "101"}, {"id": "102"}])
    df_wo = clean_work_orders_data([{"id": "201"}])
    report = generate_data_quality_report(df_deals, df_wo)
    assert report["total_records"] == 3
    assert report["deals_count"] == 2
    assert report["work_orders_count"] == 1
    assert len(report["caveats"]) == 5
    print("test_quality_report PASSED")


if __name__ == "__main__":
    test_empty_inputs()
    test_clean_deals()
    test_clean_work_orders()
    test_quality_report()
    print("\nALL DATA CLEANER TESTS PASSED SUCCESSFULLY!")
