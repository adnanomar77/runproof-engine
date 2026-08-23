from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from runproof_engine import auto_run, load_run


class JsonHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_pandas_adapter_records_real_file_boundaries(tmp_path: Path) -> None:
    pandas = pytest.importorskip("pandas")
    source = tmp_path / "data.csv"
    target = tmp_path / "written.csv"
    source.write_text("value\n1\n2\n", encoding="utf-8")

    with auto_run("pandas-real", root=tmp_path / "runs", backend="trace", include_paths=[Path(__file__).parent]) as run:
        frame = pandas.read_csv(source)
        frame.to_csv(target, index=False)

    loaded = load_run(run.result.artifact_dir)
    events = json.loads((loaded.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    assert any(event["event"] == "dataframe_read" for event in events)
    assert any(event["event"] == "dataframe_written" for event in events)
    assert (run.result.artifact_dir / "outputs" / "auto" / "pandas.to_csv").is_file()
    assert loaded.verify_integrity().status == "verified"


def test_sqlite_adapter_records_real_queries_and_boundary(tmp_path: Path) -> None:
    database = tmp_path / "records.sqlite3"
    with auto_run("sqlite-real", root=tmp_path / "runs", backend="trace", include_paths=[Path(__file__).parent]) as run:
        connection = sqlite3.connect(database)
        connection.execute("create table records (value integer)")
        connection.execute("insert into records values (?)", (7,))
        connection.commit()
        assert connection.execute("select value from records").fetchone()[0] == 7
        connection.close()

    loaded = load_run(run.result.artifact_dir)
    events = json.loads((loaded.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    assert any(event["event"] == "sql_query" for event in events)
    assert any(boundary["kind"] == "database_state" for boundary in loaded.manifest["boundaries"])
    assert loaded.verify_integrity().status == "non_reproducible"


def test_subprocess_adapter_records_real_process_boundary(tmp_path: Path) -> None:
    with auto_run("subprocess-real", root=tmp_path / "runs", backend="trace", include_paths=[Path(__file__).parent]) as run:
        result = subprocess.run(
            [sys.executable, "-c", "print('runproof subprocess')"],
            capture_output=True,
            text=True,
            check=True,
        )

    assert result.stdout.strip() == "runproof subprocess"
    loaded = load_run(run.result.artifact_dir)
    events = json.loads((loaded.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    assert any(event["event"] == "subprocess_completed" for event in events)
    assert any(boundary["kind"] == "subprocess_state" for boundary in loaded.manifest["boundaries"])


def test_requests_adapter_records_real_local_http(tmp_path: Path) -> None:
    requests = pytest.importorskip("requests")
    server = ThreadingHTTPServer(("127.0.0.1", 0), JsonHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with auto_run("requests-real", root=tmp_path / "runs", backend="trace", include_paths=[Path(__file__).parent]) as run:
            response = requests.get(f"http://127.0.0.1:{server.server_port}/status", timeout=5)
            assert response.status_code == 200
    finally:
        server.shutdown()
        thread.join(timeout=5)

    loaded = load_run(run.result.artifact_dir)
    events = json.loads((loaded.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    assert any(event["event"] == "http_request_observed" and event["payload"].get("adapter") == "requests" for event in events)
    assert loaded.verify_integrity().status == "verified_with_boundaries"


def test_httpx_adapter_records_real_local_http(tmp_path: Path) -> None:
    httpx = pytest.importorskip("httpx")
    server = ThreadingHTTPServer(("127.0.0.1", 0), JsonHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with auto_run("httpx-real", root=tmp_path / "runs", backend="trace", include_paths=[Path(__file__).parent]) as run:
            response = httpx.get(f"http://127.0.0.1:{server.server_port}/status", timeout=5)
            assert response.status_code == 200
    finally:
        server.shutdown()
        thread.join(timeout=5)

    loaded = load_run(run.result.artifact_dir)
    events = json.loads((loaded.artifact_dir / "execution" / "trace.json").read_text(encoding="utf-8"))
    assert any(event["event"] == "http_request_prepared" and event["payload"].get("adapter") == "httpx" for event in events)
    assert loaded.verify_integrity().status == "verified_with_boundaries"
