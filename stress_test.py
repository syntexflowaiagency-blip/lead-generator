import sys
import os
import time
import random
import unicodedata
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from lead_database import LeadDatabase, phone_key, name_key
from run import is_duplicate, convert_raw_lead, get_qualification_score, get_lead_priority

def run_all_stress_tests():
    print("=" * 70)
    print("STARTING EXTENSIVE STRESS TEST & LOGIC VALIDATION")
    print("=" * 70)

    test_db_path = "test_stress_leads.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = LeadDatabase(db_name=test_db_path)

    # -------------------------------------------------------------
    # TEST 1: Phone Normalization Key Tests
    # -------------------------------------------------------------
    print("\n[TEST 1] Phone Key Normalization & Edge Cases...")
    phone_cases = [
        ("+91 99158 00821", "9915800821"),
        ("09915800821", "9915800821"),
        ("919915800821", "9915800821"),
        ("(022) 2654-3210", "02226543210"[-10:]), # 2226543210
        ("1800-111-2222", "8001112222"),
        ("", ""),
        (None, ""),
        ("123", ""),       # < 8 digits
        ("N/A", ""),
        ("+1 (555) 234-5678", "5552345678"),
    ]
    for raw_phone, expected in phone_cases:
        actual = phone_key(raw_phone)
        assert actual == expected, f"Failed phone_key for '{raw_phone}': expected '{expected}', got '{actual}'"
    print("  PASS: Phone key normalization passed all cases.")

    # -------------------------------------------------------------
    # TEST 2: Name Key Normalization & Unicode Math / Accents
    # -------------------------------------------------------------
    print("\n[TEST 2] Name Key Normalization & Unicode / Whitespace...")
    name_cases = [
        ("Acme Studio", "123 Main St, Mumbai", "acmestudio|123mainstmumbai"),
        ("  ACME   STUDIO  ", "123 Main St., Mumbai  ", "acmestudio|123mainstmumbai"),
        ("𝐀𝐜𝐦𝐞 𝐒𝐭𝐮𝐝𝐢𝐨", "123 Main St, Mumbai", "acmestudio|123mainstmumbai"), # Unicode math bold
        ("Studio & Co.", "Bandra West", "studioco|bandrawest"),
        ("", "Some Address", ""),
        (None, "Some Address", ""),
    ]
    for title, addr, expected in name_cases:
        actual = name_key(title, addr)
        assert actual == expected, f"Failed name_key for '{title}' & '{addr}': expected '{expected}', got '{actual}'"
    print("  PASS: Name key normalization passed all cases.")

    # -------------------------------------------------------------
    # TEST 3: Multi-Run Simulation (The Exact User Issue)
    # -------------------------------------------------------------
    print("\n[TEST 3] Multi-Run Duplicate Prevention Simulation...")
    # Simulate a search that returns 50 Google Maps results
    pool_of_raw_listings = []
    for i in range(1, 51):
        pool_of_raw_listings.append({
            "Title": f"Designer Studio {i}",
            "Address": f"{i} Linking Rd, Bandra, Mumbai",
            "PhoneNumber": f"+91 98200 {i:05d}",
            "WebsiteURL": f"https://studio{i}.com" if i % 2 == 0 else ""
        })

    # RUN 1: Target = 20 leads
    target_count = 20
    seen_run1 = set()
    run1_leads = []
    for raw in pool_of_raw_listings:
        if len(run1_leads) >= target_count:
            break
        lead = convert_raw_lead(raw, "Interior Designers & Architects", len(run1_leads) + 1)
        if is_duplicate(lead, seen_run1):
            continue
        if db.is_duplicate(lead):
            continue
        run1_leads.append(lead)

    assert len(run1_leads) == 20, f"Run 1 expected 20 leads, got {len(run1_leads)}"
    # Add to DB
    added_run1 = db.add_leads(run1_leads)
    assert added_run1 == 20, f"Run 1 expected 20 added to DB, got {added_run1}"
    print(f"  Run 1: Got {len(run1_leads)} fresh leads (Lead #1 to #20). Database count: {db.get_total_unique_count()}")

    # RUN 2: Run exact same search with target = 20 leads
    seen_run2 = set()
    run2_leads = []
    skipped_db_count = 0
    for raw in pool_of_raw_listings:
        if len(run2_leads) >= target_count:
            break
        lead = convert_raw_lead(raw, "Interior Designers & Architects", len(run2_leads) + 1)
        if is_duplicate(lead, seen_run2):
            continue
        if db.is_duplicate(lead):
            skipped_db_count += 1
            continue
        run2_leads.append(lead)

    assert skipped_db_count == 20, f"Expected 20 skipped from DB in Run 2, got {skipped_db_count}"
    assert len(run2_leads) == 20, f"Run 2 expected 20 new leads, got {len(run2_leads)}"
    # Verify NO overlap between run 1 and run 2 leads
    run1_titles = {l["Title"] for l in run1_leads}
    run2_titles = {l["Title"] for l in run2_leads}
    overlap = run1_titles.intersection(run2_titles)
    assert len(overlap) == 0, f"Overlap detected between Run 1 and Run 2: {overlap}"
    
    added_run2 = db.add_leads(run2_leads)
    assert added_run2 == 20
    print(f"  Run 2: Got {len(run2_leads)} BRAND NEW leads (Lead #21 to #40). Skipped {skipped_db_count} from Run 1. Database count: {db.get_total_unique_count()}")

    # RUN 3: Run again with target = 20 leads (Only 10 left in pool)
    seen_run3 = set()
    run3_leads = []
    skipped_db_count_3 = 0
    for raw in pool_of_raw_listings:
        if len(run3_leads) >= target_count:
            break
        lead = convert_raw_lead(raw, "Interior Designers & Architects", len(run3_leads) + 1)
        if is_duplicate(lead, seen_run3):
            continue
        if db.is_duplicate(lead):
            skipped_db_count_3 += 1
            continue
        run3_leads.append(lead)

    assert skipped_db_count_3 == 40, f"Expected 40 skipped from DB in Run 3, got {skipped_db_count_3}"
    assert len(run3_leads) == 10, f"Run 3 expected 10 remaining leads, got {len(run3_leads)}"
    added_run3 = db.add_leads(run3_leads)
    assert added_run3 == 10
    print(f"  Run 3: Correctly fetched remaining {len(run3_leads)} leads (Lead #41 to #50). Skipped {skipped_db_count_3}. Total in DB: {db.get_total_unique_count()}")

    # RUN 4: Run again when pool is fully exhausted
    seen_run4 = set()
    run4_leads = []
    skipped_db_count_4 = 0
    for raw in pool_of_raw_listings:
        if len(run4_leads) >= target_count:
            break
        lead = convert_raw_lead(raw, "Interior Designers & Architects", len(run4_leads) + 1)
        if is_duplicate(lead, seen_run4):
            continue
        if db.is_duplicate(lead):
            skipped_db_count_4 += 1
            continue
        run4_leads.append(lead)

    assert len(run4_leads) == 0, f"Expected 0 new leads, got {len(run4_leads)}"
    assert skipped_db_count_4 == 50, f"Expected 50 skipped, got {skipped_db_count_4}"
    print(f"  Run 4: Correctly detected 0 new leads when all 50 in pool were already scraped. Skipped {skipped_db_count_4} duplicates.")
    print("  PASS: Multi-run duplicate prevention works as designed!")

    # -------------------------------------------------------------
    # TEST 4: High-Volume Stress Test (10,000 leads)
    # -------------------------------------------------------------
    print("\n[TEST 4] High-Volume Database Stress Test (10,000 Records)...")
    batch_size = 10000
    stress_leads = []
    for i in range(1, batch_size + 1):
        stress_leads.append({
            "Title": f"Business Entity {i}",
            "PhoneNumber": f"+91 91000 {i:05d}",
            "Address": f"Plot {i}, Tech Zone, Sector {i % 50}, Gurugram",
            "Industry": "Commercial HVAC",
            "City": "Gurugram, Haryana, India"
        })

    t0 = time.time()
    inserted = db.add_leads(stress_leads, source="StressTest")
    insert_duration = time.time() - t0
    print(f"  Inserted {inserted} leads in {insert_duration:.3f}s ({inserted/insert_duration:.0f} leads/sec).")

    # Query speed stress test: Check 1,000 duplicate lookups
    sample_to_check = random.sample(stress_leads, 1000)
    t0 = time.time()
    for lead in sample_to_check:
        is_dup = db.is_duplicate(lead)
        assert is_dup is True
    lookup_duration = time.time() - t0
    print(f"  Checked 1,000 duplicate lookups in {lookup_duration:.3f}s ({1000/lookup_duration:.0f} queries/sec).")

    # Check 1,000 non-existent leads
    t0 = time.time()
    for i in range(1, 1001):
        non_existent = {
            "Title": f"Brand New Fake Business {i}",
            "PhoneNumber": f"+91 88888 {i:05d}",
            "Address": f"Nowhere Land {i}"
        }
        is_dup = db.is_duplicate(non_existent)
        assert is_dup is False
    non_dup_duration = time.time() - t0
    print(f"  Checked 1,000 non-duplicate lookups in {non_dup_duration:.3f}s ({1000/non_dup_duration:.0f} queries/sec).")
    print("  PASS: Database performance and scaling stress test passed.")

    # -------------------------------------------------------------
    # TEST 5: Edge cases & Partial Missing Data
    # -------------------------------------------------------------
    print("\n[TEST 5] Edge Cases: Missing Phone, Missing Address, Corrupt Data...")
    no_phone_lead_1 = {"Title": "No Phone Cafe", "Address": "MG Road 1", "PhoneNumber": ""}
    no_phone_lead_2 = {"Title": "No Phone Cafe", "Address": "MG Road 1", "PhoneNumber": ""}
    no_phone_lead_diff_addr = {"Title": "No Phone Cafe", "Address": "MG Road 2", "PhoneNumber": ""}
    
    assert db.is_duplicate(no_phone_lead_1) is False
    db.add_lead(no_phone_lead_1)
    assert db.is_duplicate(no_phone_lead_2) is True, "Should be duplicate based on Title + Address"
    assert db.is_duplicate(no_phone_lead_diff_addr) is False, "Different address should NOT be duplicate"

    # Close and cleanup test db
    db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    print("  PASS: Edge cases passed successfully.")

    print("\n" + "=" * 70)
    print("ALL TESTS & STRESS SCENARIOS PASSED WITH ZERO ERRORS!")
    print("=" * 70)

if __name__ == "__main__":
    run_all_stress_tests()
