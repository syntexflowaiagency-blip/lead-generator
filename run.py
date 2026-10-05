import asyncio
import csv
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from lead_database import LeadDatabase, phone_key, name_key
from py_lead_generation import GoogleMapsEngine
from py_lead_generation.src.misc.enrichment import enrich_website

# ============================================================
# MULTI-CITY RUN CONFIGURATION
# ============================================================

# Define all your target campaigns here
# Sub-locality targeting breaks Google Maps 120-cap and yields 500+ fresh leads per city
CAMPAIGNS = [
    # --------------------------------------------------------
    # MUMBAI — Interior Designers & Architects
    # --------------------------------------------------------
    {
        "city": "Bandra, Mumbai, Maharashtra, India",
        "industry": "Interior Designers & Architects",
        "query": "luxury interior designers",
        "count": 30,
        "zoom": 13
    },
    {
        "city": "Andheri West, Mumbai, Maharashtra, India",
        "industry": "Interior Designers & Architects",
        "query": "luxury interior designers",
        "count": 30,
        "zoom": 13
    },
    {
        "city": "South Mumbai, Maharashtra, India",
        "industry": "Interior Designers & Architects",
        "query": "luxury interior designers",
        "count": 30,
        "zoom": 13
    },

    # --------------------------------------------------------
    # BENGALURU — Dental & Specialist Clinics
    # --------------------------------------------------------
    {
        "city": "Indiranagar, Bengaluru, Karnataka, India",
        "industry": "Dental & Specialist Clinics",
        "query": "dental clinics dental implants",
        "count": 30,
        "zoom": 13
    },
    {
        "city": "Koramangala, Bengaluru, Karnataka, India",
        "industry": "Dental & Specialist Clinics",
        "query": "dental clinics dental implants",
        "count": 30,
        "zoom": 13
    },
    {
        "city": "Whitefield, Bengaluru, Karnataka, India",
        "industry": "Dental & Specialist Clinics",
        "query": "dental clinics dental implants",
        "count": 30,
        "zoom": 13
    },

    # --------------------------------------------------------
    # GURUGRAM — Commercial HVAC & Home Services
    # --------------------------------------------------------
    {
        "city": "DLF Phase 1, Gurugram, Haryana, India",
        "industry": "Roofing - HVAC - Plumbing - Home Services",
        "query": "commercial hvac contractors",
        "count": 30,
        "zoom": 13
    },
    {
        "city": "Golf Course Road, Gurugram, Haryana, India",
        "industry": "Roofing - HVAC - Plumbing - Home Services",
        "query": "commercial hvac contractors",
        "count": 30,
        "zoom": 13
    },
]





# Defaults; main() overwrites these for every campaign
CITY = CAMPAIGNS[0]["city"]
ZOOM = CAMPAIGNS[0]["zoom"]
SEARCHES = []


# ============================================================
# CSV STRUCTURE
# ============================================================

CSV_COLUMNS = [
    "LeadID",
    "Title",
    "Rating",
    "ReviewCount",
    "PhoneNumber",
    "Email",
    "Instagram",
    "LinkedIn",
    "WebsiteURL",
    "Address",
    "Industry",
    "City",
    "LeadPriority",
    "QualificationScore",
    "MapsLink",
    "WebsiteQuality",
    "ProblemFound",
    "Notes",
]


# ============================================================
# HELPERS
# ============================================================

def normalize(value: str) -> str:
    """Normalize text for duplicate detection."""
    if not value:
        return ""
    return " ".join(value.lower().strip().split())


def make_maps_link(title: str, address: str) -> str:
    """Create a Google Maps search link."""
    search_text = f"{title}, {address}"
    return (
        "https://www.google.com/maps/search/"
        f"?api=1&query={quote_plus(search_text)}"
    )


def get_city_code(city: str) -> str:
    """Create a short city code for LeadID."""
    city_lower = city.lower()

    if "chandigarh" in city_lower:
        return "CHD"
    if "bengaluru" in city_lower:
        return "BLR"
    if "bangalore" in city_lower:
        return "BLR"
    if "mohali" in city_lower:
        return "MOH"
    if "kharar" in city_lower:
        return "KHR"
    if "kyoto" in city_lower:
        return "KYO"
    if "mumbai" in city_lower:
        return "MUM"
    if "gurugram" in city_lower or "gurgaon" in city_lower:
        return "GGN"

    # Generic fallback
    words = city.replace(",", "").split()
    if len(words) >= 3:
        return "".join(word[0].upper() for word in words[:3])
    return city[:3].upper()


def get_industry_code(industry: str) -> str:
    """Create a short industry code for LeadID."""
    industry_code_map = {
        "Premium Restaurants & Cafes": "RC",
        "Dental & Specialist Clinics": "DC",
        "Interior Designers & Architects": "IA",

        # Previous / future supported industries
        "Traditional Ryokans & Boutique Stays": "R",
        "Kimono & Yukata Rental Shops": "K",
        "Private Cultural Experience Operators": "C",
        "Independent Craft & Souvenir Shops": "S",
        "Medical Spas & Cosmetic Clinics": "MS",
        "Dentists": "D",
        "Restaurants & Cafes": "RC",
        "Roofing / HVAC / Plumbing / Home Services": "HS",
        "Boutique Hotels / Resorts / B&Bs": "BH",
        "Roofing - HVAC - Plumbing - Home Services": "HS",
    }
    return industry_code_map.get(industry, "L")


def make_lead_id(title: str, industry: str, index: int) -> str:
    """
    Generate a human-readable LeadID.

    Example:
    CHD-RC-0001
    """
    city_code = get_city_code(CITY)
    industry_code = get_industry_code(industry)
    return f"{city_code}-{industry_code}-{index:04d}"


# ============================================================
# QUALIFICATION
# ============================================================

def get_qualification_score(lead: dict) -> int:
    """
    Rule-based qualification score.

    This is NOT a full website audit.
    It only uses information reliably available
    from the Google Maps scraper.
    """
    score = 0

    website = lead.get("WebsiteURL", "").strip()
    phone = lead.get("PhoneNumber", "").strip()
    title = lead.get("Title", "").strip()
    address = lead.get("Address", "").strip()
    industry = lead.get("Industry", "").strip()

    target_industries = {
        "Premium Restaurants & Cafes",
        "Dental & Specialist Clinics",
        "Interior Designers & Architects",

        # Previous / future supported industries
        "Traditional Ryokans & Boutique Stays",
        "Kimono & Yukata Rental Shops",
        "Private Cultural Experience Operators",
        "Independent Craft & Souvenir Shops",
        "Medical Spas & Cosmetic Clinics",
        "Dentists",
        "Restaurants & Cafes",
        "Roofing / HVAC / Plumbing / Home Services",
        "Boutique Hotels / Resorts / B&Bs",
        "Roofing - HVAC - Plumbing - Home Services",
    }

    # Website
    if not website:
        # Strong website opportunity
        score += 50
    else:
        # Website exists, but quality still needs auditing
        score += 20

    # Phone
    if phone:
        score += 15

    # Target industry
    if industry in target_industries:
        score += 15

    # Complete business information
    if title and address:
        score += 5

    # Rating & Review credibility boost
    try:
        rating_val = float(lead.get("Rating") or 0)
        review_val = int(lead.get("ReviewCount") or 0)
        if rating_val >= 4.5 and review_val >= 15:
            score += 10
    except (ValueError, TypeError):
        pass

    # Direct contact email boost
    if lead.get("Email"):
        score += 10

    return score


def get_lead_priority(score: int) -> str:
    """Convert qualification score into priority."""
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "MEDIUM"
    return "LOW"


def qualify_lead(raw_lead: dict) -> dict:
    """
    Add agency-specific qualification information.

    Important:
    This does NOT perform a visual website audit.

    A website that exists is marked as
    'Needs Review' until the separate website
    audit stage is implemented.
    """
    website = raw_lead.get("WebsiteURL", "").strip()

    if not website:
        website_quality = "No Website"
        problem_found = "No website listed on Google Maps"
        notes = (
            "Automated high-opportunity signal: "
            "no website listed. "
            "Inspect business and create BI report "
            "if priority is HIGH."
        )
    else:
        website_quality = "Needs Review"
        problem_found = ""
        notes = (
            "Website found. "
            "Manual website inspection required "
            "before BI report."
        )

    raw_lead["WebsiteQuality"] = website_quality
    raw_lead["ProblemFound"] = problem_found
    raw_lead["Notes"] = notes

    score = get_qualification_score(raw_lead)
    raw_lead["QualificationScore"] = score
    raw_lead["LeadPriority"] = get_lead_priority(score)

    return raw_lead


# ============================================================
# LEAD CONVERSION
# ============================================================

def convert_raw_lead(raw_lead: dict, industry: str, lead_index: int) -> dict:
    """Convert scraper output into final CSV structure."""
    title = str(raw_lead.get("Title", "")).strip()
    address = str(raw_lead.get("Address", "")).strip()
    phone = str(raw_lead.get("PhoneNumber", "")).strip()
    website = str(raw_lead.get("WebsiteURL", "")).strip()
    rating = str(raw_lead.get("Rating", "")).strip()
    review_count = str(raw_lead.get("ReviewCount", "")).strip()
    maps_link = str(raw_lead.get("MapsLink", "")).strip() or make_maps_link(title, address)

    lead = {
        "LeadID": make_lead_id(title, industry, lead_index),
        "Title": title,
        "Rating": rating,
        "ReviewCount": review_count,
        "PhoneNumber": phone,
        "Email": str(raw_lead.get("Email", "")).strip(),
        "Instagram": str(raw_lead.get("Instagram", "")).strip(),
        "LinkedIn": str(raw_lead.get("LinkedIn", "")).strip(),
        "WebsiteURL": website,
        "Address": address,
        "Industry": industry,
        "City": CITY,
        "LeadPriority": "",
        "QualificationScore": 0,
        "MapsLink": maps_link,
        "WebsiteQuality": "",
        "ProblemFound": "",
        "Notes": "",
    }

    return qualify_lead(lead)


# ============================================================
# DUPLICATE DETECTION (within this run)
# ============================================================

def is_duplicate(lead: dict, seen: set) -> bool:
    """Duplicate inside this run: same phone (last 10 digits) OR same title+address."""
    keys = []

    phone = phone_key(lead["PhoneNumber"])
    if phone:
        keys.append(("phone", phone))

    name = name_key(lead["Title"], lead["Address"])
    if name:
        keys.append(("name", name))

    if any(key in seen for key in keys):
        return True

    seen.update(keys)
    return False


# ============================================================
# FILE NAMING
# ============================================================

def build_filename() -> str:
    """
    Filename format:

    YYYY-MM-DD__CITY__INDUSTRIES__TOTAL.csv
    """
    today = date.today().isoformat()

    industry_parts = "_".join(
        f"{item['industry'].replace(' ', '-')}-{item['count']}"
        for item in SEARCHES
    )

    total = sum(item["count"] for item in SEARCHES)

    safe_city = CITY.replace(",", "").replace(" ", "-")

    name = f"{today}__{safe_city}__{industry_parts}__{total}.csv"

    # Windows-illegal characters (e.g. "/" in industry names) -> "-"
    name = re.sub(r'[\\/:*?"<>|]', "-", name)

    return re.sub(r"-{2,}", "-", name)


# ============================================================
# SAVE CSV
# ============================================================

def save_csv(leads: list[dict]) -> Path:
    """Save the output CSV."""
    filename = build_filename()
    output_path = Path.cwd() / filename

    # Same campaign run twice in one day: keep both files
    counter = 2
    while output_path.exists():
        output_path = Path.cwd() / f"{Path(filename).stem}_{counter}.csv"
        counter += 1

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(leads)

    return output_path


# ============================================================
# SCRAPING
# ============================================================

async def scrape_industry(
    industry: str,
    query: str,
    target_count: int,
    db: LeadDatabase,
) -> tuple[list[dict], dict]:
    """
    Scrape one campaign and return (new unique leads, stats).

    Duplicates (inside this campaign, or already in the database) are
    removed BEFORE the target count is applied, so a rerun still fills
    the target with fresh leads when Maps returned enough listings.
    """
    print()
    print("=" * 60)
    print(f"Searching: {industry}")
    print(f"Query: {query}")
    print(f"Location: {CITY}")
    print(f"Target: {target_count}")
    print("=" * 60)

    existing_count = db.get_count_for_campaign(CITY, industry)
    engine = GoogleMapsEngine(
        query=query,
        location=CITY,
        zoom=ZOOM,
        target_count=target_count,
        existing_count=existing_count,
        db=db,
    )

    await engine.run()

    raw_entries = engine.entries
    stats = {"raw": len(raw_entries), "dup_run": 0, "dup_db": 0}

    print(f"Google Maps returned: {stats['raw']} results")

    seen = set()
    leads = []

    for raw_entry in raw_entries:
        if len(leads) >= target_count:
            break

        # Index is assigned after dedupe, so LeadIDs have no gaps
        lead = convert_raw_lead(raw_entry, industry, len(leads) + 1)

        # Ignore completely empty records
        if not lead["Title"] and not lead["Address"]:
            continue

        if is_duplicate(lead, seen):
            stats["dup_run"] += 1
            continue

        if db.is_duplicate(lead):
            stats["dup_db"] += 1
            continue

        leads.append(lead)

    # --------------------------------------------------------
    # Website Contact Enrichment (Async Emails & Social Profiles)
    # --------------------------------------------------------
    if leads:
        websites_to_check = [l for l in leads if l["WebsiteURL"]]
        if websites_to_check:
            print(f"Enriching {len(websites_to_check)} websites for emails & social links...")
            tasks = [enrich_website(l["WebsiteURL"]) for l in websites_to_check]
            enrichment_results = await asyncio.gather(*tasks, return_exceptions=True)

            for l, res in zip(websites_to_check, enrichment_results):
                if isinstance(res, dict):
                    l["Email"] = res.get("Email", "")
                    l["Instagram"] = res.get("Instagram", "")
                    l["LinkedIn"] = res.get("LinkedIn", "")
                    # Recompute score with email boost
                    score = get_qualification_score(l)
                    l["QualificationScore"] = score
                    l["LeadPriority"] = get_lead_priority(score)

    print(f"New unique leads: {len(leads)} / {target_count}")

    if len(leads) < target_count:
        print(
            f"Warning: only {len(leads)} new leads for {industry} "
            f"({stats['dup_db']} already in database, "
            f"{stats['dup_run']} repeats in this run)."
        )

    return leads, stats


# ============================================================
# MAIN
# ============================================================

async def main() -> None:
    global CITY, ZOOM, SEARCHES

    print()
    print("QUILL LABS — GOOGLE MAPS LEAD GENERATOR")
    print("=" * 60)
    print(f"Campaigns: {len(CAMPAIGNS)}")
    print("Duplicate removal: Enabled (this run + lead database)")
    print("=" * 60)

    db = LeadDatabase()

    total_scraped = 0
    skipped_in_run = 0
    skipped_in_db = 0
    total_saved = 0
    saved_files = []
    failed_campaigns = []

    for campaign in CAMPAIGNS:

        # Set the globals the helper functions rely on
        CITY = campaign["city"]
        ZOOM = campaign["zoom"]
        SEARCHES = [{
            "industry": campaign["industry"],
            "query": campaign["query"],
            "count": campaign["count"],
        }]

        print()
        print("=" * 60)
        print(f"STARTING CAMPAIGN: {campaign['industry']} in {campaign['city']}")
        print("=" * 60)

        # One failed campaign must not stop the others
        try:
            new_leads, stats = await scrape_industry(
                industry=campaign["industry"],
                query=campaign["query"],
                target_count=campaign["count"],
                db=db,
            )
        except Exception as error:
            print(f"Campaign FAILED: {error}")
            failed_campaigns.append(f"{campaign['industry']} in {campaign['city']}")
            continue

        total_scraped += stats["raw"]
        skipped_in_run += stats["dup_run"]
        skipped_in_db += stats["dup_db"]

        if not new_leads:
            print("No brand-new unique leads found for this campaign.")
            continue

        # Best automated opportunities first
        new_leads.sort(
            key=lambda lead: lead["QualificationScore"],
            reverse=True,
        )

        # Save the CSV first, remember the leads only after it succeeded
        output_path = save_csv(new_leads)
        db.add_leads(new_leads, source="GoogleMaps")

        total_saved += len(new_leads)
        saved_files.append(output_path.name)

        high_count = sum(1 for l in new_leads if l["LeadPriority"] == "HIGH")
        medium_count = sum(1 for l in new_leads if l["LeadPriority"] == "MEDIUM")
        low_count = sum(1 for l in new_leads if l["LeadPriority"] == "LOW")
        no_website_count = sum(
            1 for l in new_leads if l["WebsiteQuality"] == "No Website"
        )

        print(f"Successfully saved {len(new_leads)} fresh leads for this campaign.")
        print(f"HIGH: {high_count} | MEDIUM: {medium_count} | LOW: {low_count}")
        print(
            f"No website: {no_website_count} | "
            f"Website found: {len(new_leads) - no_website_count}"
        )
        print(f"CSV: {output_path.name}")

        print()
        print("TOP QUALIFIED LEADS")
        print("-" * 60)
        for lead in new_leads[:10]:
            print(
                f"{lead['LeadPriority']:6} | "
                f"{lead['QualificationScore']:2} | "
                f"{lead['Industry']:35} | "
                f"{lead['Title']}"
            )
        print("-" * 60)

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("[RUN COMPLETE]")
    print("=" * 60)
    print(f"Scraper pulled {total_scraped} total listings from Maps.")
    print(
        f"Skipped {skipped_in_run} duplicates inside campaigns and "
        f"{skipped_in_db} already in your database."
    )
    print(f"Successfully added {total_saved} BRAND NEW leads across {len(saved_files)} CSV file(s).")
    for name in saved_files:
        print(f"  - {name}")
    if failed_campaigns:
        print("Failed campaigns (rerun them):")
        for name in failed_campaigns:
            print(f"  - {name}")
    print(
        f"Total unique leads safely sitting in database: "
        f"{db.get_total_unique_count()}"
    )
    print("=" * 60)
    db.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())