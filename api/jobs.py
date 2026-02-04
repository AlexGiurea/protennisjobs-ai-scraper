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
        try:
            offset = int(query.get("offset", [0])[0])
            limit = int(query.get("limit", [6])[0])
        except ValueError:
            send_json(self, {"error": "Invalid offset or limit."}, status=400)
            return

        filtered_jobs = app_server.filter_jobs(app_server.ALL_JOBS, query)
        sliced = filtered_jobs[offset : offset + limit]
        payload = {
            "total": len(filtered_jobs),
            "offset": offset,
            "limit": limit,
            "jobs": sliced,
        }
        send_json(self, payload)
