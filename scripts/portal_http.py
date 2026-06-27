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
    cmd = [curl, "-fsS", "-X", method, url, "-H", f"Authorization: Bearer {token}", "-H", "Accept: application/json"]
    if body is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(body)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    raw = proc.stdout or ""
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or raw or f"curl exit {proc.returncode}")
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(raw[:500]) from exc


def api_json(method: str, url: str, token: str, body: dict | None = None) -> dict[str, Any]:
    curl = shutil.which("curl")
    if curl:
        try:
            return _curl_json(method, url, token, body)
        except RuntimeError as exc:
            raise SystemExit(f"API {method} {url} failed: {exc}") from exc

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
        raise SystemExit(f"API {method} {url} failed: {exc}") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API {method} {url} failed ({exc.code}): {detail}") from exc