import re
import sqlite3
import unicodedata
from datetime import datetime


def phone_key(phone) -> str:
    """
    Last 10 digits of a phone number, or '' if unusable.

    '09915800821', '+91 99158 00821' and '919915800821'
    all become '9915800821'.
    """
    digits = re.sub(r"\D", "", str(phone or ""))

    if len(digits) < 8:
        return ""

    return digits[-10:]


def name_key(title, address) -> str:
    """
    Normalized 'title|address'. Handles case, punctuation, spacing and
    fancy unicode fonts (e.g. bold math letters) via NFKC.
    """

    def clean(value) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).lower()
        return re.sub(r"[\W_]+", "", text)

    title_part = clean(title)
    address_part = clean(address)

    if not title_part:
        return ""

    return f"{title_part}|{address_part}"


def url_slug_key(url: str) -> str:
    """Extract and normalize business slug from Google Maps URL."""
    if not url:
        return ""
    m = re.search(r"/maps/place/([^/@?]+)", str(url))
    if m:
        from urllib.parse import unquote_plus
        slug = unquote_plus(m.group(1)).lower()
        return re.sub(r"[\W_]+", "", slug)
    return ""


class LeadDatabase:
    """
    Cross-run lead memory.

    A lead counts as a duplicate if EITHER its phone number (last 10
    digits), its normalized title+address, OR its Maps URL slug already exists.
    """

    def __init__(self, db_name="leads.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_or_migrate()

    # --------------------------------------------------------
    # Schema
    # --------------------------------------------------------

    def _create_table(self, name="leads"):
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                phone_number TEXT,
                address TEXT,
                source TEXT,
                scraped_at TEXT,
                industry TEXT,
                city TEXT,
                email TEXT NOT NULL DEFAULT '',
                rating TEXT NOT NULL DEFAULT '',
                review_count TEXT NOT NULL DEFAULT '',
                instagram TEXT NOT NULL DEFAULT '',
                linkedin TEXT NOT NULL DEFAULT '',
                maps_url TEXT NOT NULL DEFAULT '',
                url_slug TEXT NOT NULL DEFAULT '',
                phone_key TEXT NOT NULL DEFAULT '',
                name_key TEXT NOT NULL DEFAULT ''
            )
        """)

    def _create_indexes(self):
        self.cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_phone
            ON leads(phone_key) WHERE phone_key != ''
        """)
        self.cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_name
            ON leads(name_key) WHERE name_key != ''
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_leads_url_slug
            ON leads(url_slug) WHERE url_slug != ''
        """)

    def _create_or_migrate(self):
        existing_cols = {
            row[1]
            for row in self.cursor.execute("PRAGMA table_info(leads)")
        }

        if not existing_cols:
            self._create_table()
        else:
            needed_cols = [
                ("email", "TEXT NOT NULL DEFAULT ''"),
                ("rating", "TEXT NOT NULL DEFAULT ''"),
                ("review_count", "TEXT NOT NULL DEFAULT ''"),
                ("instagram", "TEXT NOT NULL DEFAULT ''"),
                ("linkedin", "TEXT NOT NULL DEFAULT ''"),
                ("maps_url", "TEXT NOT NULL DEFAULT ''"),
                ("url_slug", "TEXT NOT NULL DEFAULT ''"),
                ("phone_key", "TEXT NOT NULL DEFAULT ''"),
                ("name_key", "TEXT NOT NULL DEFAULT ''"),
            ]
            for col_name, col_def in needed_cols:
                if col_name not in existing_cols:
                    try:
                        self.cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}")
                    except Exception:
                        pass

        self._create_indexes()
        self.conn.commit()

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def is_url_duplicate(self, url: str) -> bool:
        """True if the Google Maps place URL slug is already in the database."""
        slug = url_slug_key(url)
        if not slug:
            return False
        row = self.cursor.execute(
            "SELECT 1 FROM leads WHERE url_slug = ? AND url_slug != '' LIMIT 1",
            (slug,)
        ).fetchone()
        return bool(row)

    def is_duplicate(self, lead_data) -> bool:
        """True if this lead is already in the database. Does not write."""
        p_key = phone_key(lead_data.get("PhoneNumber"))
        n_key = name_key(lead_data.get("Title"), lead_data.get("Address"))
        u_slug = url_slug_key(lead_data.get("MapsLink") or lead_data.get("url"))

        if p_key:
            row = self.cursor.execute(
                "SELECT 1 FROM leads WHERE phone_key = ? AND phone_key != '' LIMIT 1", (p_key,)
            ).fetchone()
            if row:
                return True

        if n_key:
            row = self.cursor.execute(
                "SELECT 1 FROM leads WHERE name_key = ? AND name_key != '' LIMIT 1", (n_key,)
            ).fetchone()
            if row:
                return True

        if u_slug:
            row = self.cursor.execute(
                "SELECT 1 FROM leads WHERE url_slug = ? AND url_slug != '' LIMIT 1", (u_slug,)
            ).fetchone()
            if row:
                return True

        return False

    def _insert(self, lead_data, source) -> bool:
        try:
            maps_url = lead_data.get("MapsLink") or lead_data.get("url") or ""
            self.cursor.execute("""
                INSERT INTO leads (title, phone_number, address, source,
                                   scraped_at, industry, city,
                                   email, rating, review_count, instagram, linkedin,
                                   maps_url, url_slug, phone_key, name_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead_data.get("Title", ""),
                lead_data.get("PhoneNumber", ""),
                lead_data.get("Address", ""),
                source,
                datetime.now().isoformat(sep=" ", timespec="seconds"),
                lead_data.get("Industry", ""),
                lead_data.get("City", ""),
                lead_data.get("Email", ""),
                str(lead_data.get("Rating", "")),
                str(lead_data.get("ReviewCount", "")),
                lead_data.get("Instagram", ""),
                lead_data.get("LinkedIn", ""),
                maps_url,
                url_slug_key(maps_url),
                phone_key(lead_data.get("PhoneNumber")),
                name_key(lead_data.get("Title"), lead_data.get("Address")),
            ))
            return True
        except sqlite3.IntegrityError:
            return False

    def add_lead(self, lead_data, source="GoogleMaps") -> bool:
        """Insert one lead. True if new, False if duplicate."""
        added = self._insert(lead_data, source)
        self.conn.commit()
        return added

    def add_leads(self, leads, source="GoogleMaps") -> int:
        """Insert many leads in one transaction. Returns how many were new."""
        added = 0
        with self.conn:
            for lead in leads:
                if self._insert(lead, source):
                    added += 1
        return added

    def get_count_for_campaign(self, city: str, industry: str) -> int:
        """Count existing leads already saved for this specific city and industry."""
        row = self.cursor.execute(
            "SELECT COUNT(*) FROM leads WHERE city = ? AND industry = ?",
            (city, industry)
        ).fetchone()
        return row[0] if row else 0

    def get_total_unique_count(self) -> int:
        self.cursor.execute("SELECT COUNT(*) FROM leads")
        return self.cursor.fetchone()[0]

    def close(self):
        self.conn.close()
