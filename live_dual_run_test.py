import asyncio
import csv
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from lead_database import LeadDatabase
from run import scrape_industry, save_csv, CAMPAIGNS

async def live_dual_test():
    print("=" * 60)
    print("LIVE END-TO-END DUAL RUN TEST (GOOGLE MAPS)")
    print("=" * 60)

    # Use a dedicated test database
    test_db_path = "live_test_leads.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = LeadDatabase(db_name=test_db_path)

    # We will test 1 campaign with count = 5 for fast execution
    campaign = {
        "city": "Bengaluru, Karnataka, India",
        "industry": "Dental & Specialist Clinics",
        "query": "dental clinics dental implants",
        "count": 5,
        "zoom": 12
    }

    import run
    run.CITY = campaign["city"]
    run.ZOOM = campaign["zoom"]
    run.SEARCHES = [{
        "industry": campaign["industry"],
        "query": campaign["query"],
        "count": campaign["count"],
    }]

    print("\n>>> STARTING RUN #1 (Target: 5 leads)...")
    leads_run1, stats_run1 = await scrape_industry(
        industry=campaign["industry"],
        query=campaign["query"],
        target_count=campaign["count"],
        db=db,
    )

    leads_run1.sort(key=lambda l: l["QualificationScore"], reverse=True)
    db.add_leads(leads_run1, source="LiveTestRun1")
    file1_path = Path("live_test_run1.csv")
    with file1_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=run.CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads_run1)

    print(f"\n[RUN 1 COMPLETE] Scraped {len(leads_run1)} leads.")
    for idx, l in enumerate(leads_run1, 1):
        print(f"  {idx}. {l['Title']} | Phone: {l['PhoneNumber']} | Address: {l['Address'][:40]}...")

    print("\n" + "-" * 60)
    print(">>> STARTING RUN #2 (Same search query, Target: 5 leads)...")
    print("Expecting the scraper to skip Run #1 leads and fetch 5 BRAND NEW leads...")
    print("-" * 60)

    leads_run2, stats_run2 = await scrape_industry(
        industry=campaign["industry"],
        query=campaign["query"],
        target_count=campaign["count"],
        db=db,
    )

    leads_run2.sort(key=lambda l: l["QualificationScore"], reverse=True)
    db.add_leads(leads_run2, source="LiveTestRun2")
    file2_path = Path("live_test_run2.csv")
    with file2_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=run.CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads_run2)

    print(f"\n[RUN 2 COMPLETE] Scraped {len(leads_run2)} leads.")
    for idx, l in enumerate(leads_run2, 1):
        print(f"  {idx}. {l['Title']} | Phone: {l['PhoneNumber']} | Address: {l['Address'][:40]}...")

    db.close()

    # -------------------------------------------------------------
    # VERIFICATION & COMPARISON
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("VERIFYING DEDUPLICATION & OVERLAP BETWEEN RUN 1 & RUN 2")
    print("=" * 60)

    titles_run1 = [l["Title"] for l in leads_run1]
    titles_run2 = [l["Title"] for l in leads_run2]
    phones_run1 = [l["PhoneNumber"] for l in leads_run1 if l["PhoneNumber"]]
    phones_run2 = [l["PhoneNumber"] for l in leads_run2 if l["PhoneNumber"]]

    title_overlap = set(titles_run1).intersection(set(titles_run2))
    phone_overlap = set(phones_run1).intersection(set(phones_run2))

    print(f"Run 1 Total Leads: {len(leads_run1)}")
    print(f"Run 2 Total Leads: {len(leads_run2)}")
    print(f"Run 2 Skipped from Database: {stats_run2['dup_db']}")
    print(f"Overlapping Titles: {len(title_overlap)} {title_overlap if title_overlap else '(None)'}")
    print(f"Overlapping Phone Numbers: {len(phone_overlap)} {phone_overlap if phone_overlap else '(None)'}")

    if len(title_overlap) == 0 and len(phone_overlap) == 0 and len(leads_run2) > 0:
        print("\n>>> RESULT: SUCCESS! Zero repeated leads between Run 1 and Run 2.")
    else:
        print("\n>>> RESULT: FAILED! Repeated leads detected.")

    # Cleanup test files
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    if os.path.exists("live_test_run1.csv"):
        os.remove("live_test_run1.csv")
    if os.path.exists("live_test_run2.csv"):
        os.remove("live_test_run2.csv")

if __name__ == "__main__":
    asyncio.run(live_dual_test())
