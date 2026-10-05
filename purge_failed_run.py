"""
One-off recovery: remove leads that were saved to leads.db by a run
that crashed before its CSV was written.

Usage (from the folder containing leads.db):
    python purge_failed_run.py
    python purge_failed_run.py "Industry Name As Stored" [YYYY-MM-DD]
"""
import sqlite3
import sys

industry = (
    sys.argv[1] if len(sys.argv) > 1
    else "Roofing / HVAC / Plumbing / Home Services"
)

conn = sqlite3.connect("leads.db")
cur = conn.cursor()

day_filter = "date(scraped_at) = date('now', 'localtime')"
params = [industry]

if len(sys.argv) > 2:
    day_filter = "date(scraped_at) = ?"
    params.append(sys.argv[2])

rows = cur.execute(
    f"SELECT id, title, scraped_at FROM leads "
    f"WHERE industry = ? AND {day_filter}",
    params,
).fetchall()

print(f"Industry: {industry}")
print(f"Rows that would be deleted: {len(rows)}")
for row in rows[:20]:
    print("  ", row)

if rows and input("Delete these rows? (y/N): ").strip().lower() == "y":
    with conn:
        cur.execute(
            f"DELETE FROM leads WHERE industry = ? AND {day_filter}",
            params,
        )
    print("Deleted.")
else:
    print("Nothing deleted.")
