import csv
import html
import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv(ENV_PATH)

BASE_URL = "https://protennisjobs.com"
LOGIN_URL = "https://protennisjobs.com/members/login.php"
CATEGORY_URL = "https://protennisjobs.com/category/tennis-professional/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_USER_AGENT = "protennisjobs-scraper/1.0"
GEOCODE_CACHE_FILE = os.path.join(DATA_DIR, "geocode_cache.json")
GEOCODE_MIN_INTERVAL = 1.0
FIT_SCORE_CACHE_FILE = os.path.join(DATA_DIR, "fit_score_cache.json")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
OPENAI_MIN_INTERVAL = float(os.getenv("OPENAI_MIN_INTERVAL", "0.2"))
OPENAI_MAX_INPUT_CHARS = int(os.getenv("OPENAI_MAX_INPUT_CHARS", "1500"))

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
)

GEOCODE_SESSION = requests.Session()
GEOCODE_SESSION.headers.update(
    {
        "User-Agent": GEOCODE_USER_AGENT,
        "Accept": "application/json",
    }
)


@dataclass
class JobListing:
    job_title: str
    location: Dict[str, Optional[str]]
    posted_date: Optional[str]
    job_summary: Optional[str]
    position_overview: Optional[str]
    suitability_score: Optional[int]
    key_responsibilities: Optional[str]
    required_qualifications: Optional[str]
    preferred_certifications: Optional[str]
    compensation_benefits: Optional[str]
    work_schedule: Optional[str]
    physical_requirements: Optional[str]
    how_to_apply: Optional[str]
    contact_emails: Optional[str]
    contact_name: Optional[str]
    contact_city: Optional[str]
    contact_address: Optional[str]
    contact_url: Optional[str]
    distance_to_harrogate_tn_miles: Optional[float]
    source_url: str


def login() -> bool:
    """Log in to ProTennisJobs with username/password and get fresh cookies.

    Returns True if login succeeded, False otherwise.
    """
    username = os.getenv("PTJ_USERNAME", "").strip()
    password = os.getenv("PTJ_PASSWORD", "").strip()
    if not username or not password:
        return False

    print(f"Logging in as {username}...")
    payload = {
        "amember_login": username,
        "amember_pass": password,
        "login_attempt_id": str(int(time.time())),
    }
    try:
        response = SESSION.post(LOGIN_URL, data=payload, timeout=30, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Login request failed: {exc}")
        return False

    # aMember sets an amember_nr cookie on successful login
    session_cookie = SESSION.cookies.get("amember_nr")
    if session_cookie:
        print("Login successful — fresh session cookies obtained.")
        return True

    # Check if the response page still shows the login form (login failed)
    if "Please log in to continue" in response.text or "amember_login" in response.text:
        print("Login failed — check PTJ_USERNAME and PTJ_PASSWORD in .env")
        return False

    # If we got redirected away from login and have a PHPSESSID, that's also fine
    if SESSION.cookies.get("PHPSESSID"):
        print("Login successful — session established.")
        return True

    print("Login outcome uncertain — no session cookie found.")
    return False


def load_cookies_from_file() -> bool:
    """Load cookies from data/cookies.json as a fallback.

    Returns True if any cookies were loaded, False otherwise.
    """
    cookie_file = os.path.join(DATA_DIR, "cookies.json")
    loaded = False
    if os.path.exists(cookie_file):
        with open(cookie_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                for name, value in data.items():
                    SESSION.cookies.set(name, value)
                    loaded = True
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    value = item.get("value")
                    if not name or value is None:
                        continue
                    SESSION.cookies.set(
                        name,
                        value,
                        domain=item.get("domain"),
                        path=item.get("path") or "/",
                        secure=bool(item.get("secure")),
                    )
                    loaded = True

    cookie_env = os.getenv("PTJ_COOKIES")
    if cookie_env:
        for pair in cookie_env.split(";"):
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            SESSION.cookies.set(name.strip(), value.strip())
            loaded = True

    return loaded


def load_cookies() -> None:
    """Authenticate with ProTennisJobs.

    Strategy:
    1. Try automated login with PTJ_USERNAME / PTJ_PASSWORD from .env
    2. Fall back to cookies.json if credentials aren't set or login fails
    """
    if login():
        return

    print("Automated login unavailable — falling back to cookies.json")
    if load_cookies_from_file():
        print("Loaded cookies from file/env.")
    else:
        print("WARNING: No cookies loaded. Scraping may fail for login-protected pages.")


def fetch_html(url: str, referer: Optional[str] = None) -> BeautifulSoup:
    headers = {}
    if referer:
        headers["Referer"] = referer
    response = SESSION.get(url, headers=headers, timeout=30)
    if response.status_code == 403 and referer != CATEGORY_URL:
        response = SESSION.get(url, headers={"Referer": CATEGORY_URL}, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(element: Optional[Tag]) -> Optional[str]:
    if not element:
        return None
    text = normalize_whitespace(element.get_text(" ", strip=True))
    return text or None


def parse_location(raw: Optional[str]) -> Dict[str, Optional[str]]:
    if not raw:
        return {"city": None, "state": None}
    raw = normalize_whitespace(raw)

    # Match "City, ST" or "City, State"
    match = re.search(r"([A-Za-z .'-]+),\s*([A-Za-z]{2,})", raw)
    if match:
        city = match.group(1).strip()
        state = match.group(2).strip()
        return {"city": city, "state": state}

    # If only one token, treat as city and leave state empty
    return {"city": raw, "state": None}


def find_location_in_text(text: str) -> Optional[str]:
    # Look for "Location: City, ST" or "Location - City, ST"
    match = re.search(r"Location\s*[:\-]\s*([^\n\r]+)", text, re.IGNORECASE)
    if match:
        return normalize_whitespace(match.group(1))

    # Try to locate a city/state pattern in the text
    match = re.search(r"\b([A-Za-z .'-]+,\s*[A-Za-z]{2})\b", text)
    if match:
        return normalize_whitespace(match.group(1))

    return None


def extract_summary_from_listing(listing: Tag) -> Optional[str]:
    summary = listing.select_one(".entry-summary, .entry-content")
    return extract_text(summary)


def extract_posted_date(soup: BeautifulSoup) -> Optional[str]:
    date = soup.select_one("time.entry-date, time.published, .entry-meta time")
    return extract_text(date)


def extract_json_ld_text(soup: BeautifulSoup) -> Optional[str]:
    script = soup.find("script", type="application/ld+json")
    if not script:
        return None
    return script.get_text() or None


def extract_json_ld_string(text: str, key: str) -> Optional[str]:
    marker = f'"{key}"'
    idx = text.find(marker)
    if idx == -1:
        return None
    colon = text.find(":", idx)
    if colon == -1:
        return None
    quote = text.find('"', colon + 1)
    if quote == -1:
        return None
    value_chars: List[str] = []
    i = quote + 1
    while i < len(text):
        char = text[i]
        if char == '"' and text[i - 1] != "\\":
            break
        value_chars.append(char)
        i += 1
    value = "".join(value_chars)
    return html.unescape(value) if value else None


def extract_json_ld_location(text: str) -> Dict[str, Optional[str]]:
    city = extract_json_ld_string(text, "addressLocality")
    state = extract_json_ld_string(text, "addressRegion")
    if not city and not state:
        street = extract_json_ld_string(text, "streetAddress")
        return parse_location(street)
    return {"city": city, "state": state}


def extract_contact_emails(soup: BeautifulSoup, description: str) -> Optional[str]:
    emails: List[str] = []

    contact_sections = []
    for alert in soup.select("div.alert"):
        heading = alert.find(["h1", "h2", "h3", "h4"])
        if heading and "contact details" in heading.get_text(" ", strip=True).lower():
            contact_sections.append(alert.get_text(" ", strip=True))

    for text in contact_sections:
        for match in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I):
            emails.append(match)

    for link in soup.select('a[href^="mailto:"]'):
        href = link.get("href", "")
        address = href.replace("mailto:", "").split("?", 1)[0].strip()
        if address:
            emails.append(address)

    for text in (description, extract_text(soup.select_one(".entry-content")) or ""):
        for match in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I):
            emails.append(match)

    deduped = sorted({email.strip().lower() for email in emails if email.strip()})
    return ", ".join(deduped) if deduped else None


def extract_contact_details(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    details: Dict[str, Optional[str]] = {
        "contact_name": None,
        "contact_email": None,
        "contact_city": None,
        "contact_address": None,
        "contact_url": None,
    }
    section = None
    for alert in soup.select("div.alert"):
        heading = alert.find(["h1", "h2", "h3", "h4"])
        if heading and "contact details" in heading.get_text(" ", strip=True).lower():
            section = alert
            break

    if not section:
        return details

    link = section.find("a", href=True)
    if link and link["href"]:
        details["contact_url"] = link["href"].strip()

    # Parse label/value pairs inside the contact section
    for span in section.find_all("span", class_="meta"):
        label = span.get_text(" ", strip=True).strip(":").lower()
        value_parts: List[str] = []
        for sib in span.next_siblings:
            if isinstance(sib, Tag) and sib.name == "span" and "meta" in (sib.get("class") or []):
                break
            if isinstance(sib, Tag):
                text = sib.get_text(" ", strip=True)
            else:
                text = str(sib).strip()
            if text:
                value_parts.append(text)
        value = normalize_whitespace(" ".join(value_parts)) if value_parts else None
        if not value:
            continue
        if label == "contact":
            details["contact_name"] = value
        elif label == "email":
            details["contact_email"] = value
        elif label == "city":
            details["contact_city"] = value
        elif label == "address":
            details["contact_address"] = value
        elif label == "url":
            details["contact_url"] = value

    if details["contact_email"]:
        match = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", details["contact_email"], re.I)
        if match:
            details["contact_email"] = match[0].lower()
    else:
        match = re.findall(
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
            section.get_text(" ", strip=True),
            re.I,
        )
        if match:
            details["contact_email"] = match[0].lower()

    return details


SECTION_KEYWORDS = {
    "key_responsibilities": [
        "responsibilities",
        "duties",
        "what you will do",
        "role includes",
    ],
    "required_qualifications": [
        "requirements",
        "qualifications",
        "required",
        "experience",
    ],
    "preferred_certifications": [
        "preferred",
        "certification",
        "certifications",
        "uspta",
        "ptr",
    ],
    "compensation_benefits": [
        "compensation",
        "benefits",
        "salary",
        "pay",
    ],
    "work_schedule": [
        "schedule",
        "hours",
        "availability",
    ],
    "physical_requirements": [
        "physical requirement",
        "physical requirements",
        "physical",
    ],
    "how_to_apply": [
        "how to apply",
        "apply",
        "contact",
        "email",
        "phone",
    ],
    "position_overview": [
        "overview",
        "description",
        "position",
        "summary",
    ],
}

WINTER_FIT_CRITERIA = (
    "I want a club willing to take me in for the winter season, not only full time or for "
    "the summer season. I want to work from August 2026 to April/May 2027."
)


def match_section_key(heading_text: str) -> Optional[str]:
    text = heading_text.lower()
    for key, keywords in SECTION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return key
    return None


def extract_sections_from_description(description: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_key: Optional[str] = None
    current_parts: List[str] = []

    def flush():
        nonlocal current_key, current_parts
        if current_key and current_parts:
            sections[current_key] = normalize_whitespace(" ".join(current_parts))
        current_key = None
        current_parts = []

    lines = [line.strip() for line in description.splitlines()]
    for line in lines:
        if not line:
            continue
        key = match_section_key(line)
        is_header = key and (line.endswith(":") or len(line.split()) <= 6)
        if key and is_header:
            flush()
            current_key = key
            continue
        if current_key:
            current_parts.append(line)

    flush()

    if not sections:
        for line in lines:
            for key, keywords in SECTION_KEYWORDS.items():
                if any(keyword in line.lower() for keyword in keywords):
                    sections.setdefault(key, line)

    return sections


def load_fit_score_cache() -> Dict[str, Optional[int]]:
    if not os.path.exists(FIT_SCORE_CACHE_FILE):
        return {}
    with open(FIT_SCORE_CACHE_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_fit_score_cache(cache: Dict[str, Optional[int]]) -> None:
    with open(FIT_SCORE_CACHE_FILE, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2)


def build_fit_prompt(job: JobListing) -> str:
    parts = [
        f"Criteria: {WINTER_FIT_CRITERIA}",
        f"Job Title: {job.job_title}",
    ]
    location = job.location or {}
    city = location.get("city")
    state = location.get("state")
    loc_parts = [part for part in (city, state) if part]
    if loc_parts:
        parts.append(f"Location: {', '.join(loc_parts)}")
    if job.posted_date:
        parts.append(f"Posted Date: {job.posted_date}")
    if job.job_summary:
        parts.append(f"Summary: {job.job_summary}")
    if job.position_overview:
        parts.append(f"Overview: {job.position_overview}")
    if job.key_responsibilities:
        parts.append(f"Responsibilities: {job.key_responsibilities}")
    if job.work_schedule:
        parts.append(f"Schedule: {job.work_schedule}")
    if job.required_qualifications:
        parts.append(f"Requirements: {job.required_qualifications}")
    if job.how_to_apply:
        parts.append(f"How to apply: {job.how_to_apply}")

    prompt = "\n".join(parts)
    if len(prompt) > OPENAI_MAX_INPUT_CHARS:
        prompt = prompt[:OPENAI_MAX_INPUT_CHARS].rstrip() + "..."
    return prompt


def extract_openai_text(payload: Dict[str, object]) -> Optional[str]:
    output = payload.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content.get("text"))
    if payload.get("output_text"):
        return str(payload.get("output_text"))
    return None


def parse_score_from_text(text: str) -> Optional[int]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    score = data.get("score")
    if isinstance(score, (int, float)):
        score = int(round(score))
        return max(0, min(10, score))
    return None


def fetch_openai_score(prompt: str, api_key: str) -> Optional[int]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": "You score job fit based on criteria. Return JSON only.",
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n\n"
                    "Return JSON in this exact shape: "
                    '{"score": 0-10, "rationale": "short reason"}'
                ),
            },
        ],
        "temperature": 0.2,
        "max_output_tokens": 120,
    }
    response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    text = extract_openai_text(response.json()) or ""
    return parse_score_from_text(text)


def score_jobs_with_ai(jobs: List[JobListing]) -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY not set; skipping suitability scoring.")
        return

    cache = load_fit_score_cache()
    last_request = 0.0

    for job in jobs:
        cache_key = job.source_url
        if cache_key in cache:
            job.suitability_score = cache.get(cache_key)
            continue

        prompt = build_fit_prompt(job)
        elapsed = time.time() - last_request
        if elapsed < OPENAI_MIN_INTERVAL:
            time.sleep(OPENAI_MIN_INTERVAL - elapsed)
        last_request = time.time()

        try:
            score = fetch_openai_score(prompt, api_key)
        except requests.RequestException:
            score = None

        job.suitability_score = score
        cache[cache_key] = score

    save_fit_score_cache(cache)


LAST_GEOCODE_REQUEST = 0.0


def load_geocode_cache() -> Dict[str, Optional[Dict[str, float]]]:
    if not os.path.exists(GEOCODE_CACHE_FILE):
        return {}
    with open(GEOCODE_CACHE_FILE, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_geocode_cache(cache: Dict[str, Optional[Dict[str, float]]]) -> None:
    with open(GEOCODE_CACHE_FILE, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2)


def throttle_geocoding() -> None:
    global LAST_GEOCODE_REQUEST
    elapsed = time.time() - LAST_GEOCODE_REQUEST
    if elapsed < GEOCODE_MIN_INTERVAL:
        time.sleep(GEOCODE_MIN_INTERVAL - elapsed)
    LAST_GEOCODE_REQUEST = time.time()


def location_cache_key(city: Optional[str], state: Optional[str]) -> Optional[str]:
    parts = [part.strip().lower() for part in (city, state) if part and part.strip()]
    if not parts:
        return None
    return ", ".join(parts)


def geocode_city_state(
    city: Optional[str],
    state: Optional[str],
    cache: Dict[str, Optional[Dict[str, float]]],
) -> Optional[Tuple[float, float]]:
    key = location_cache_key(city, state)
    if not key:
        return None
    cached = cache.get(key)
    if cached is not None:
        return (cached["lat"], cached["lon"])
    if key in cache and cached is None:
        return None

    query = f"{city}, {state}, USA" if state else f"{city}, USA"
    params = {"q": query, "format": "json", "limit": 1}
    try:
        throttle_geocoding()
        response = GEOCODE_SESSION.get(GEOCODE_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return None

    if not payload:
        cache[key] = None
        return None

    coords = {
        "lat": float(payload[0]["lat"]),
        "lon": float(payload[0]["lon"]),
    }
    cache[key] = coords
    return (coords["lat"], coords["lon"])


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_miles * c


def populate_distance_to_harrogate(jobs: List[JobListing]) -> None:
    cache = load_geocode_cache()
    harrogate_coords = geocode_city_state("Harrogate", "TN", cache)
    for job in jobs:
        location = job.location or {}
        coords = geocode_city_state(location.get("city"), location.get("state"), cache)
        if coords and harrogate_coords:
            job.distance_to_harrogate_tn_miles = round(
                haversine_miles(coords[0], coords[1], harrogate_coords[0], harrogate_coords[1]),
                1,
            )
        else:
            job.distance_to_harrogate_tn_miles = None
    save_geocode_cache(cache)


def extract_job_details(
    job_url: str,
    summary: Optional[str],
    listing_title: Optional[str],
    listing_location: Optional[str],
    listing_date: Optional[str],
) -> JobListing:
    try:
        soup = fetch_html(job_url, referer=CATEGORY_URL)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            return JobListing(
                job_title=listing_title or "Unknown",
                location=parse_location(listing_location),
                posted_date=listing_date,
                job_summary=summary,
                position_overview=None,
                suitability_score=None,
                key_responsibilities=None,
                required_qualifications=None,
                preferred_certifications=None,
                compensation_benefits=None,
                work_schedule=None,
                physical_requirements=None,
                how_to_apply=None,
                contact_emails=None,
                contact_name=None,
                contact_city=None,
                contact_address=None,
                contact_url=None,
                distance_to_harrogate_tn_miles=None,
                source_url=job_url,
            )
        raise
    json_ld = extract_json_ld_text(soup) or ""

    description = extract_json_ld_string(json_ld, "description") or ""
    description = html.unescape(description)
    description = description.replace("\r\n", "\n").replace("\r", "\n")

    title = extract_json_ld_string(json_ld, "title") or listing_title or "Unknown"
    posted_date = extract_json_ld_string(json_ld, "datePosted") or listing_date
    location = extract_json_ld_location(json_ld)
    if not location.get("city") and listing_location:
        location = parse_location(listing_location)

    sections = extract_sections_from_description(description) if description else {}

    position_overview = sections.get("position_overview")
    if not position_overview and description:
        paragraphs = [line for line in description.splitlines() if line.strip()]
        position_overview = paragraphs[1] if len(paragraphs) > 1 else paragraphs[0]

    contact_details = extract_contact_details(soup)
    contact_emails = contact_details.get("contact_email") or extract_contact_emails(soup, description)

    return JobListing(
        job_title=title,
        location=location,
        posted_date=posted_date,
        job_summary=summary,
        position_overview=position_overview,
        suitability_score=None,
        key_responsibilities=sections.get("key_responsibilities"),
        required_qualifications=sections.get("required_qualifications"),
        preferred_certifications=sections.get("preferred_certifications"),
        compensation_benefits=sections.get("compensation_benefits"),
        work_schedule=sections.get("work_schedule"),
        physical_requirements=sections.get("physical_requirements"),
        how_to_apply=sections.get("how_to_apply"),
        contact_emails=contact_emails,
        contact_name=contact_details.get("contact_name"),
        contact_city=contact_details.get("contact_city"),
        contact_address=contact_details.get("contact_address"),
        contact_url=contact_details.get("contact_url"),
        distance_to_harrogate_tn_miles=None,
        source_url=job_url,
    )


def extract_listings_from_page(page_url: str) -> Tuple[List[Dict[str, Optional[str]]], Optional[str]]:
    soup = fetch_html(page_url)
    listings: List[Dict[str, Optional[str]]] = []

    for container in soup.select("div.classified"):
        title_link = container.select_one(".job-title a")
        href = title_link.get("href") if title_link else None
        if not href:
            continue
        job_url = urljoin(BASE_URL, href)

        summary = extract_text(container.select_one(".job-title p"))
        listing_title = extract_text(title_link)

        date_block = container.select_one(".job-date")
        date_parts = [normalize_whitespace(part) for part in date_block.stripped_strings] if date_block else []
        listing_location = date_parts[0] if date_parts else None
        listing_date = date_parts[-1] if len(date_parts) > 1 else None

        listings.append(
            {
                "url": job_url,
                "summary": summary,
                "listing_title": listing_title,
                "listing_location": listing_location,
                "listing_date": listing_date,
            }
        )

    next_link = soup.select_one("a.next, .nav-links .next, a.next.page-numbers")
    next_url = urljoin(BASE_URL, next_link.get("href")) if next_link and next_link.get("href") else None
    return listings, next_url


def scrape_all_listings() -> List[JobListing]:
    all_jobs: List[JobListing] = []
    seen_urls = set()
    next_url = CATEGORY_URL

    while next_url:
        listings, next_url = extract_listings_from_page(next_url)
        for listing in listings:
            job_url = listing["url"]
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)
            job = extract_job_details(
                job_url,
                listing.get("summary"),
                listing.get("listing_title"),
                listing.get("listing_location"),
                listing.get("listing_date"),
            )
            all_jobs.append(job)

    return all_jobs


def write_csv(path: str, jobs: List[JobListing]) -> None:
    fieldnames = [
        "job_title",
        "location_city",
        "location_state",
        "posted_date",
        "Distance to Harrogate, TN",
        "job_summary",
        "position_overview",
        "suitability_score",
        "key_responsibilities",
        "required_qualifications",
        "preferred_certifications",
        "compensation_benefits",
        "work_schedule",
        "physical_requirements",
        "how_to_apply",
        "contact_emails",
        "contact_name",
        "contact_city",
        "contact_address",
        "contact_url",
        "source_url",
    ]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for job in jobs:
            location = job.location or {}
            writer.writerow(
                {
                    "job_title": job.job_title,
                    "location_city": location.get("city"),
                    "location_state": location.get("state"),
                    "posted_date": job.posted_date,
                    "Distance to Harrogate, TN": job.distance_to_harrogate_tn_miles,
                    "job_summary": job.job_summary,
                    "position_overview": job.position_overview,
                    "suitability_score": job.suitability_score,
                    "key_responsibilities": job.key_responsibilities,
                    "required_qualifications": job.required_qualifications,
                    "preferred_certifications": job.preferred_certifications,
                    "compensation_benefits": job.compensation_benefits,
                    "work_schedule": job.work_schedule,
                    "physical_requirements": job.physical_requirements,
                    "how_to_apply": job.how_to_apply,
                    "contact_emails": job.contact_emails,
                    "contact_name": job.contact_name,
                    "contact_city": job.contact_city,
                    "contact_address": job.contact_address,
                    "contact_url": job.contact_url,
                    "source_url": job.source_url,
                }
            )


def main() -> None:
    load_cookies()
    jobs = scrape_all_listings()
    populate_distance_to_harrogate(jobs)
    score_jobs_with_ai(jobs)
    payload = [asdict(job) for job in jobs]
    json_path = os.path.join(DATA_DIR, "protennisjobs.json")
    csv_path = os.path.join(DATA_DIR, "protennisjobs.csv")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"Saved {len(payload)} job listings to {json_path}")
    write_csv(csv_path, jobs)


if __name__ == "__main__":
    main()
