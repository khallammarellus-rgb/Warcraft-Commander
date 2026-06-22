"""Small HTTP helper for portal API scripts (avoids macOS Python SSL issues)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


def _curl_json(method: str, url: str, token: str, body: dict | None = None) -> dict[str, Any]:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")
    cmd = [curl, "-sS", "-X", method, url, "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/json"]
    if body is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(body)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"curl exit {proc.returncode}")
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(proc.stdout[:500]) from exc


def api_json(method: str, url: str, token: str, body: dict | None = None) -> dict[str, Any]:
    try:
        data = None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc) and shutil.which("curl"):
            return _curl_json(method, url, token, body)
        raise SystemExit(f"API {method} {url} failed: {exc}") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API {method} {url} failed ({exc.code}): {detail}") from exc