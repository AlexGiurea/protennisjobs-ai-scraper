import atexit
import csv
import json
import os
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
CSV_PATH = os.path.join(DATA_DIR, "protennisjobs.csv")
REFRESH_INTERVAL_DAYS = float(os.getenv("PTJ_REFRESH_DAYS", "3"))
REFRESH_ENABLED = REFRESH_INTERVAL_DAYS > 0
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
PID_PATH = os.path.join(PROJECT_ROOT, ".server.pid")


def load_dotenv(path):
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


load_dotenv(ENV_PATH)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_EMAIL_MODEL", "gpt-4o-mini")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")

PROFILE = {
    "preferred_name": "Alex",
    "full_name": "Alex Giurea",
    "location": "Tennessee (during school)",
    "school": "Lincoln Memorial University (LMU), Harrogate, Tennessee",
    "degree": "Business Analytics, graduating May 2026",
    "tennis_background": [
        "Playing since age 7",
        "College tennis athlete",
        "Leadership experience as a top lineup player",
    ],
    "target_role": "Tennis Professional at a country club",
    "duties": [
        "Private lessons",
        "Group clinics",
        "Hitting sessions",
        "Junior programs",
        "Beginner adult programs",
        "Member engagement",
        "Event support",
    ],
    "strengths": [
        "Clear, simple communication",
        "High energy, dependable, professional",
        "Good at building rapport with members and juniors",
        "Comfortable leading groups and structured sessions",
        "Strong work ethic and long practice background",
    ],
    "leadership": [
        "Experience leading in team and academic settings",
        "Reliable and organized",
    ],
    "availability": (
        "Main availability: August 2026 to April/May 2027. "
        "Summer 2026: Maine (June to August or early fall 2026)."
    ),
    "work_auth": (
        "International student pathway; can work legally under OPT after graduation in 2026."
    ),
    "tone": "Confident, friendly, professional. Simple sentences and vocabulary.",
    "must_include": [
        "Availability window",
        "Willingness to hop on a quick call",
        "Clear next step",
    ],
    "style_constraints": [
        "No bold text",
        "No em dashes",
    ],
    "sample_reference": (
        "Keep structure similar to a concise intro, short experience paragraph, "
        "availability paragraph, and polite close."
    ),
    "contact_phone": "423-801-3020",
}


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d %B %Y")
    except ValueError:
        return None


def parse_query_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def normalize_text(value):
    return value.strip().lower() if value else ""


def _pid_is_running(pid):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ensure_single_instance():
    existing_pid = None
    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH, "r", encoding="utf-8") as handle:
                existing_pid = int((handle.read() or "").strip() or "0")
        except (OSError, ValueError):
            existing_pid = None

    if existing_pid and existing_pid != os.getpid() and _pid_is_running(existing_pid):
        raise RuntimeError(
            f"Server already running (pid {existing_pid}). Stop it or delete {PID_PATH}."
        )

    try:
        with open(PID_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except OSError:
        pass

    def _cleanup_pid():
        try:
            if os.path.exists(PID_PATH):
                with open(PID_PATH, "r", encoding="utf-8") as handle:
                    pid = int((handle.read() or "").strip() or "0")
                if pid == os.getpid():
                    os.remove(PID_PATH)
        except (OSError, ValueError):
            pass

    atexit.register(_cleanup_pid)


def extract_org_name(job):
    summary = (job.get("job_summary") or "").strip()
    if summary and " is looking for" in summary:
        return summary.split(" is looking for", 1)[0].strip()
    contact_name = (job.get("contact_name") or "").strip()
    if contact_name and any(keyword in contact_name.lower() for keyword in ["club", "academy", "resort", "center", "centre"]):
        return contact_name
    return ""


def infer_contact_name(job_summary, contact_name, contact_url):
    if contact_name:
        return contact_name
    inferred = extract_org_name({"job_summary": job_summary, "contact_name": ""})
    if inferred:
        return inferred
    if contact_url:
        host = urlparse(contact_url).hostname or ""
        if host:
            host = host[4:] if host.startswith("www.") else host
            parts = host.split(".")
            base = parts[-2] if len(parts) >= 2 else parts[0]
            return base.replace("-", " ").title()
    return ""


def load_jobs():
    jobs = []
    with open(CSV_PATH, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            job = {
                "job_title": row.get("job_title") or "Tennis Role",
                "location": {
                    "city": row.get("location_city") or "Unknown City",
                    "state": row.get("location_state") or "Unknown",
                },
                "posted_date": row.get("posted_date") or "",
                "distance_to_harrogate_tn_miles": None,
                "job_summary": row.get("job_summary") or "",
                "position_overview": row.get("position_overview") or "",
                "suitability_score": None,
                "key_responsibilities": row.get("key_responsibilities") or "",
                "required_qualifications": row.get("required_qualifications") or "",
                "preferred_certifications": row.get("preferred_certifications") or "",
                "compensation_benefits": row.get("compensation_benefits") or "",
                "work_schedule": row.get("work_schedule") or "",
                "physical_requirements": row.get("physical_requirements") or "",
                "how_to_apply": row.get("how_to_apply") or "",
                "contact_emails": row.get("contact_emails") or "",
                "contact_name": infer_contact_name(
                    row.get("job_summary"),
                    row.get("contact_name"),
                    row.get("contact_url"),
                )
                or "Unknown org",
                "contact_city": row.get("contact_city") or "",
                "contact_address": row.get("contact_address") or "",
                "contact_url": row.get("contact_url") or "",
                "source_url": row.get("source_url") or "",
            }

            score = row.get("suitability_score")
            try:
                job["suitability_score"] = int(score) if score else None
            except ValueError:
                job["suitability_score"] = None

            distance = row.get("Distance to Harrogate, TN")
            if distance:
                try:
                    job["distance_to_harrogate_tn_miles"] = float(distance)
                except ValueError:
                    job["distance_to_harrogate_tn_miles"] = None

            jobs.append(job)
    return jobs


ALL_JOBS = load_jobs()
REFRESH_LOCK = threading.Lock()
LAST_REFRESH_TS = None


def compute_stats(jobs):
    total = len(jobs)
    scores = [j["suitability_score"] for j in jobs if isinstance(j["suitability_score"], int)]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    state_counts = {}
    for job in jobs:
        state = job["location"]["state"] or "Unknown"
        state_counts[state] = state_counts.get(state, 0) + 1
    top_state = max(state_counts, key=state_counts.get) if state_counts else "Unknown"

    latest_date = None
    for job in jobs:
        parsed = parse_date(job.get("posted_date"))
        if parsed and (latest_date is None or parsed > latest_date):
            latest_date = parsed

    return {
        "total": total,
        "avgScore": f"{avg_score:.1f}" if avg_score is not None else "No data",
        "topState": top_state,
        "latestDate": latest_date.strftime("%b %d, %Y") if latest_date else "No data",
    }


STATS = compute_stats(ALL_JOBS)


def filter_jobs(jobs, query):
    q = normalize_text(query.get("q", [""])[0])
    location_filter = normalize_text(query.get("location", [""])[0])
    posted_from = parse_query_date(query.get("posted_from", [""])[0])
    posted_to = parse_query_date(query.get("posted_to", [""])[0])
    min_score_raw = query.get("min_score", [""])[0].strip()
    min_score = None
    if min_score_raw:
        try:
            min_score = int(min_score_raw)
        except ValueError:
            min_score = None

    filtered = []
    for job in jobs:
        if q:
            haystack = " ".join(
                filter(
                    None,
                    [
                        job.get("job_title"),
                        job.get("job_summary"),
                        job.get("position_overview"),
                        job.get("how_to_apply"),
                        job.get("contact_name"),
                        job.get("location", {}).get("city"),
                        job.get("location", {}).get("state"),
                    ],
                )
            )
            if q not in normalize_text(haystack):
                continue

        if location_filter:
            location = " ".join(
                filter(
                    None,
                    [
                        job.get("location", {}).get("city"),
                        job.get("location", {}).get("state"),
                    ],
                )
            )
            if location_filter not in normalize_text(location):
                continue

        if posted_from or posted_to:
            posted_date = parse_date(job.get("posted_date") or "")
            if not posted_date:
                continue
            if posted_from and posted_date < posted_from:
                continue
            if posted_to and posted_date > posted_to:
                continue

        if min_score is not None:
            score = job.get("suitability_score")
            if not isinstance(score, int) or score < min_score:
                continue

        filtered.append(job)

    return filtered


def find_job_by_source_url(jobs, source_url):
    if not source_url:
        return None
    source_url = source_url.strip()
    for job in jobs:
        if job.get("source_url") == source_url:
            return job
    return None


def refresh_dataset():
    global ALL_JOBS, STATS, LAST_REFRESH_TS
    if not REFRESH_LOCK.acquire(blocking=False):
        return False
    try:
        import scrape_protennisjobs as scraper

        print("Refreshing job listings from protennisjobs.com...")
        scraper.main()
        ALL_JOBS = load_jobs()
        STATS = compute_stats(ALL_JOBS)
        LAST_REFRESH_TS = time.time()
        print("Refresh complete.")
        return True
    except Exception as exc:
        print(f"Refresh failed: {exc}")
        return False
    finally:
        REFRESH_LOCK.release()


def refresh_loop():
    if not REFRESH_ENABLED:
        print("Auto refresh disabled (PTJ_REFRESH_DAYS <= 0).")
        return
    interval_seconds = max(0.5, REFRESH_INTERVAL_DAYS * 86400)
    refresh_dataset()
    while True:
        time.sleep(interval_seconds)
        refresh_dataset()


def extract_openai_text(payload):
    if isinstance(payload, dict):
        if payload.get("output_text"):
            return str(payload.get("output_text"))
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content.get("text"))
    return None


def parse_json_from_text(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    # Try to extract the first JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


EMAIL_TEMPLATE = """Use a short, clean structure:
1) Greeting.
2) Intro sentence stating interest in the role.
3) One paragraph summarizing relevant experience.
4) One paragraph with availability/fit + call to action.
5) Friendly close with name and contact info."""


def format_profile(profile):
    def _join(value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join([str(item) for item in value if item])
        return str(value)

    fields = [
        ("Name", profile.get("full_name")),
        ("Preferred name", profile.get("preferred_name")),
        ("Location", profile.get("location")),
        ("School", profile.get("school")),
        ("Degree", profile.get("degree")),
        ("Tennis background", _join(profile.get("tennis_background"))),
        ("Target role", profile.get("target_role")),
        ("Duties", _join(profile.get("duties"))),
        ("Strengths", _join(profile.get("strengths"))),
        ("Leadership", _join(profile.get("leadership"))),
        ("Availability", profile.get("availability")),
        ("Work authorization", profile.get("work_auth")),
        ("Tone", profile.get("tone")),
        ("Must include", _join(profile.get("must_include"))),
        ("Style constraints", _join(profile.get("style_constraints"))),
        ("Phone", profile.get("contact_phone")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if value]
    return "\n".join(lines)


def guess_last_name(contact_name):
    if not contact_name:
        return ""
    parts = [p for p in contact_name.replace(",", " ").split() if p]
    return parts[-1] if len(parts) >= 2 else ""


def build_email_prompt(job, user_context):
    contact_name = job.get("contact_name") or ""
    contact_last_name = guess_last_name(contact_name)
    org_name = extract_org_name(job) or contact_name or "your club"
    location = " ".join(
        filter(None, [job.get("location", {}).get("city"), job.get("location", {}).get("state")])
    )
    job_title = job.get("job_title") or "tennis role"
    job_summary = job.get("job_summary") or job.get("position_overview") or ""
    user_context = (user_context or "").strip()
    fallback_profile = format_profile(PROFILE)

    instructions = [
        "Write a concise job application email (120-180 words).",
        f"Address the contact as Coach {contact_last_name or 'there'}.",
        f"Role: {job_title} at {org_name}.",
        f"Location: {location or 'not provided'}.",
        "Use the user context below as the primary source for the candidate info.",
        "If user context is empty, use the fallback profile instead.",
        "Reference relevant job details from the job summary when possible.",
        "Do not invent credentials or experiences not stated.",
        "Keep the tone professional, warm, and direct.",
        "Output JSON with keys: subject, body. Body should be plain text.",
        f"Subject format: Application for {job_title} at {org_name}.",
        "Follow this structure:",
        EMAIL_TEMPLATE,
    ]

    content = "\n".join(
        [
            "User context:",
            user_context or "(none provided)",
            "",
            "Fallback profile (use only if user context is empty):",
            fallback_profile or "(none provided)",
            "",
            "Job summary:",
            job_summary or "(not provided)",
            "",
            "Instructions:",
            *instructions,
        ]
    )
    return content


def request_email_draft(job, user_context=""):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    prompt = build_email_prompt(job, user_context)
    debug_prompt_path = os.path.join(DATA_DIR, "last_email_prompt.txt")
    try:
        with open(debug_prompt_path, "w", encoding="utf-8") as file:
            file.write(prompt)
    except OSError:
        pass
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "system",
        "content": (
                    "You write concise tennis job application emails. "
                    "Use the provided user context and job details. "
                    "Do not fabricate details. Return JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_output_tokens": 400,
    }
    try:
        response = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=40,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        message = str(exc)
        if hasattr(exc, "response") and exc.response is not None:
            message = f"OpenAI request failed: {exc.response.status_code} {exc.response.text}"
        raise RuntimeError(message) from exc

    data = response.json()
    text = extract_openai_text(data)
    if not text:
        raise RuntimeError("Empty response from OpenAI.")
    parsed = parse_json_from_text(text)
    if not parsed:
        raise RuntimeError("Invalid JSON from OpenAI.")
    subject = parsed.get("subject", "").strip()
    body = parsed.get("body", "").strip()
    if not subject or not body:
        if not subject:
            fallback_title = job.get("job_title") or "Tennis role"
            subject = f"Application for {fallback_title}"
        if not body:
            raise RuntimeError("Incomplete draft from OpenAI.")
    return {"subject": subject, "body": body}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/job":
            query = parse_qs(parsed.query)
            source_url = query.get("source_url", [""])[0]
            job = find_job_by_source_url(ALL_JOBS, source_url)
            if not job:
                self._send_json({"error": "Job not found."}, status=404)
                return
            self._send_json(job)
            return
        if parsed.path == "/api/email-draft":
            query = parse_qs(parsed.query)
            source_url = query.get("source_url", [""])[0]
            user_context = query.get("user_context", [""])[0]
            job = find_job_by_source_url(ALL_JOBS, source_url)
            if not job:
                self._send_json({"error": "Job not found."}, status=404)
                return
            email = job.get("contact_emails") or ""
            if not email:
                self._send_json({"error": "No contact email for this job."}, status=400)
                return
            try:
                draft = request_email_draft(job, user_context=user_context)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
                return
            payload = {
                "to": email,
                "subject": draft["subject"],
                "body": draft["body"],
            }
            self._send_json(payload)
            return
        if parsed.path == "/api/jobs":
            query = parse_qs(parsed.query)
            offset = int(query.get("offset", [0])[0])
            limit = int(query.get("limit", [6])[0])
            filtered_jobs = filter_jobs(ALL_JOBS, query)
            sliced = filtered_jobs[offset : offset + limit]
            payload = {
                "total": len(filtered_jobs),
                "offset": offset,
                "limit": limit,
                "jobs": sliced,
            }
            self._send_json(payload)
            return
        if parsed.path == "/api/stats":
            self._send_json(STATS)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/email-draft":
            self._send_json({"error": "Not found."}, status=404)
            return
        print(f"[email-draft] POST {self.path}")
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            print("[email-draft] Invalid JSON body.")
            self._send_json({"error": "Invalid JSON body."}, status=400)
            return
        source_url = (payload.get("source_url") or "").strip()
        user_context = (payload.get("user_context") or "").strip()
        print(
            "[email-draft] source_url=%s user_context_len=%s",
            source_url or "(empty)",
            len(user_context),
        )
        job = find_job_by_source_url(ALL_JOBS, source_url)
        if not job:
            print("[email-draft] Job not found.")
            self._send_json({"error": "Job not found."}, status=404)
            return
        email = job.get("contact_emails") or ""
        if not email:
            print("[email-draft] No contact email for this job.")
            self._send_json({"error": "No contact email for this job."}, status=400)
            return
        try:
            draft = request_email_draft(job, user_context=user_context)
        except Exception as exc:
            print(f"[email-draft] Draft error: {exc}")
            self._send_json({"error": str(exc)}, status=500)
            return
        response_payload = {
            "to": email,
            "subject": draft["subject"],
            "body": draft["body"],
        }
        self._send_json(response_payload)

    def _send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ensure_single_instance()
    os.chdir(WEB_DIR)
    if REFRESH_ENABLED:
        threading.Thread(target=refresh_loop, daemon=True).start()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    print(f"Open in browser: http://localhost:{port}/")
    server.serve_forever()
