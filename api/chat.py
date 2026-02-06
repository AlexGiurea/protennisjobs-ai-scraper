import json
import os
import sys
from http.server import BaseHTTPRequestHandler

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
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            send_json(self, {"error": "Invalid JSON body."}, status=400)
            return

        messages = payload.get("messages", [])
        if not messages:
            send_json(self, {"error": "No messages provided."}, status=400)
            return

        # Ensure vector store is ready (may set up on first Vercel cold start)
        if not app_server.VS_READY.is_set():
            app_server.setup_vector_store()

        try:
            response_text = app_server.chat_with_data(messages)
        except Exception as exc:
            send_json(self, {"error": str(exc)}, status=500)
            return

        send_json(self, {"response": response_text})
