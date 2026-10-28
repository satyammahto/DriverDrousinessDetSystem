"""Loopback-only web adapter for the existing OpenCV detector loop."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


UI_DIR = Path(__file__).resolve().parent / "dashboard_ui"
SESSION_DIR = UI_DIR.parent / "session_data"


def read_session_history() -> dict[str, Any]:
    """Read completed local session summaries for the analytics view."""
    sessions: list[dict[str, Any]] = []
    try:
        for path in SESSION_DIR.glob("session_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(record, dict):
                    continue
                sessions.append({
                    "id": str(record.get("id") or path.stem),
                    "started_at": record.get("started_at"),
                    "ended_at": record.get("ended_at"),
                    "duration_seconds": max(0.0, float(record.get("duration_seconds") or 0)),
                    "closed_eye_seconds": max(0.0, float(record.get("closed_eye_seconds") or 0)),
                    "alert_count": max(0, int(record.get("alert_count") or 0)),
                    "longest_closure_seconds": max(0.0, float(record.get("longest_closure_seconds") or 0)),
                    "status": str(record.get("status") or "unknown"),
                })
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        pass
    sessions.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
    total_duration = sum(item["duration_seconds"] for item in sessions)
    total_closed = sum(item["closed_eye_seconds"] for item in sessions)
    total_alerts = sum(item["alert_count"] for item in sessions)
    return {
        "sessions": sessions,
        "summary": {
            "session_count": len(sessions),
            "total_duration_seconds": round(total_duration, 1),
            "closed_eye_seconds": round(total_closed, 1),
            "alert_count": total_alerts,
            "average_fatigue_percent": round(100 * total_closed / total_duration, 1) if total_duration else 0,
        },
    }


class LocalDashboard:
    """Serve UI assets and the detector's latest real frame and status."""

    def __init__(self, port: int = 8000) -> None:
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._status: dict[str, Any] = {
            "running": True,
            "camera_connected": False,
            "frame_available": False,
            "serial_port_open": False,
            "driver": "STARTING",
            "eyes": "UNKNOWN",
            "closed_duration": 0.0,
            "alert_active": False,
            "buzzer_remaining": 0.0,
            "last_command": None,
            "uptime_seconds": 0.0,
        }
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                path = urlparse(self.path).path
                if path == "/api/status":
                    payload = json.dumps(dashboard.snapshot()[1]).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                elif path == "/api/analytics":
                    payload = json.dumps(read_session_history()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                elif path == "/api/stream":
                    self.send_response(200)
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.end_headers()
                    try:
                        while True:
                            frame, _ = dashboard.snapshot()
                            if frame is not None:
                                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                                self.wfile.write(frame + b"\r\n")
                                self.wfile.flush()
                            time.sleep(0.08)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                elif path in ("/", "/index.html"):
                    self._send_asset("index.html", "text/html; charset=utf-8")
                elif path == "/styles.css":
                    self._send_asset("styles.css", "text/css; charset=utf-8")
                elif path == "/app.js":
                    self._send_asset("app.js", "text/javascript; charset=utf-8")
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_error(404)

            def _send_asset(self, name: str, content_type: str) -> None:
                try:
                    payload = (UI_DIR / name).read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="local-dashboard-http",
            daemon=True,
        )
        self._thread.start()

    def publish(self, frame: bytes, status: dict[str, Any]) -> None:
        with self._lock:
            self._frame = frame
            self._status = dict(status)

    def snapshot(self) -> tuple[bytes | None, dict[str, Any]]:
        with self._lock:
            return self._frame, dict(self._status)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1.0)


def start_dashboard(port: int = 8000) -> LocalDashboard:
    return LocalDashboard(port)
