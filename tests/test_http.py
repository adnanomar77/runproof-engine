from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from runproof_engine import auto_run, load_run, verified


class JsonHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"ok": true, "source": "local-real-server"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_auto_run_urllib_adapter_records_boundary(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), JsonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with auto_run("auto_http_run", root=tmp_path / "runs", backend="trace") as run, urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/status") as response:
            assert response.read().startswith(b"{\"ok\": true")
        assert run.result.status == "verified_with_boundaries"
        assert load_run(run.result.artifact_dir).verify_integrity().status == "verified_with_boundaries"
        trace = json.loads((run.result.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
        assert any(event["event"] == "http_request_observed" for event in trace)
        assert any(event["event"] == "evidence_boundary" for event in trace)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_http_adapter_records_response_without_secret(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), JsonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with verified("http_run", root=tmp_path / "runs") as run:
            response = run.request(
                "local_status",
                f"http://127.0.0.1:{server.server_port}/status",
                headers={"Authorization": "Bearer private-value"},
                approved=True,
            )
            assert response["ok"] is True
        trace = json.loads((run.result.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
        call_events = [event for event in trace if event["event"] == "external_call"]
        assert call_events
        serialized = json.dumps(call_events)
        assert "private-value" not in serialized
        assert "Bearer private-value" not in serialized
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
