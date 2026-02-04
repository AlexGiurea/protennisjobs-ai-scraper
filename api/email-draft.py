import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import server as app_server


def send_json(handler, payload, status=200):
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        source_url = query.get("source_url", [""])[0]
        if not source_url:
            send_json(self, {"error": "Missing source_url."}, status=400)
            return

        job = app_server.find_job_by_source_url(app_server.ALL_JOBS, source_url)
        if not job:
            send_json(self, {"error": "Job not found."}, status=404)
            return

        email = job.get("contact_emails") or ""
        if not email:
            send_json(self, {"error": "No contact email for this job."}, status=400)
            return

        try:
            draft = app_server.request_email_draft(job)
        except Exception as exc:
            send_json(self, {"error": str(exc)}, status=500)
            return

        payload = {"to": email, "subject": draft["subject"], "body": draft["body"]}
        send_json(self, payload)
