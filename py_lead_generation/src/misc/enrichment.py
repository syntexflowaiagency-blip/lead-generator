import re
import asyncio
import aiohttp
from urllib.parse import urljoin, urlparse

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Filter out false positive email extensions & domains
IGNORED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".woff", ".ttf"
)
IGNORED_DOMAINS = (
    "sentry.io", "wixpress.com", "example.com", "domain.com", "email.com",
    "google.com", "schema.org", "w3.org", "wordpress.org"
)

async def enrich_website(website_url: str, timeout_s: float = 6.0) -> dict:
    """
    Enriches a website URL by extracting:
    - Direct email addresses
    - Instagram, LinkedIn, and Facebook social profile links
    """
    result = {
        "Email": "",
        "Instagram": "",
        "LinkedIn": "",
        "Facebook": "",
    }

    if not website_url or not website_url.startswith("http"):
        return result

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout_s),
            headers=headers
        ) as session:
            # 1. Fetch homepage
            try:
                async with session.get(website_url, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return result
                    html = await resp.text(errors="ignore")
            except Exception:
                return result

            # Parse social links & emails from homepage
            _extract_from_html(html, website_url, result)

            # 2. If no email found, check /contact or /about-us if found in links
            if not result["Email"]:
                contact_links = re.findall(r'href=["\']([^"\']*(?:contact|about)[^"\']*)["\']', html, re.I)
                for rel_link in contact_links[:2]:
                    target = urljoin(website_url, rel_link)
                    if urlparse(target).netloc == urlparse(website_url).netloc:
                        try:
                            async with session.get(target, allow_redirects=True) as resp2:
                                if resp2.status == 200:
                                    html2 = await resp2.text(errors="ignore")
                                    _extract_from_html(html2, website_url, result)
                                    if result["Email"]:
                                        break
                        except Exception:
                            continue

    except Exception:
        pass

    return result

def _extract_from_html(html: str, base_url: str, result: dict) -> None:
    # 1. Search for mailto links first (highest fidelity)
    mailtos = re.findall(r'href=["\']mailto:([^"?\'\s]+)', html, re.I)
    for m in mailtos:
        cleaned = m.strip().lower()
        if _is_valid_email(cleaned):
            result["Email"] = cleaned
            break

    # 2. Search for regex emails if mailto not found
    if not result["Email"]:
        found_emails = EMAIL_REGEX.findall(html)
        for e in found_emails:
            cleaned = e.strip().lower()
            if _is_valid_email(cleaned):
                result["Email"] = cleaned
                break

    # 3. Search for social links
    if not result["Instagram"]:
        insta = re.search(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.-]+)/?', html, re.I)
        if insta and insta.group(1).lower() not in ("p", "explore", "stories", "reel", "tv"):
            result["Instagram"] = f"https://instagram.com/{insta.group(1)}"

    if not result["LinkedIn"]:
        linkedin = re.search(r'https?://(?:www\.)?linkedin\.com/(?:company|in)/([a-zA-Z0-9_.-]+)/?', html, re.I)
        if linkedin:
            result["LinkedIn"] = linkedin.group(0).rstrip("/")

    if not result["Facebook"]:
        fb = re.search(r'https?://(?:www\.)?facebook\.com/([a-zA-Z0-9_.-]+)/?', html, re.I)
        if fb and fb.group(1).lower() not in ("sharer", "share", "dialog", "policies"):
            result["Facebook"] = f"https://facebook.com/{fb.group(1)}"

def _is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    if any(email.endswith(ext) for ext in IGNORED_EXTENSIONS):
        return False
    domain = email.split("@")[-1]
    if any(ignored in domain for ignored in IGNORED_DOMAINS):
        return False
    return True
