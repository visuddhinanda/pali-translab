"""Shared wikipali HTTP client: cache + envelope unwrap.

Future migration: replace with MCP calls; CLI of fetch_*.py keeps the same.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = os.environ.get("WIKIPALI_URL", "https://www.wikipali.org")
DEFAULT_CACHE = Path(os.environ.get("WIKIPALI_CACHE", ".cache/wikipali"))
USER_AGENT = "pali-translab-skill/0.1"


def _cache_path(path: str, params: dict[str, Any]) -> Path:
    key = path + "?" + urllib.parse.urlencode(sorted(params.items()))
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    slug = path.strip("/").replace("/", "_")
    return DEFAULT_CACHE / slug / f"{h}.json"


def get(path: str, params: dict[str, Any] | None = None,
        *, base: str = DEFAULT_BASE, refresh: bool = False,
        unwrap: bool = True) -> Any:
    """GET <base><path>?<params>.

    Returns `data` (envelope unwrapped) if `unwrap`, else full envelope.
    Caches successful responses to .cache/wikipali/.
    """
    params = params or {}
    cache_file = _cache_path(path, params)
    if not refresh and cache_file.exists():
        env = json.loads(cache_file.read_text("utf-8"))
    else:
        qs = urllib.parse.urlencode(params)
        url = f"{base}{path}" + (f"?{qs}" if qs else "")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        # Server uses HTTP 4xx alongside `{"ok":false}` body; read body either way.
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            if not body:
                raise
        env = json.loads(body)
        if env.get("ok"):
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(env, ensure_ascii=False), "utf-8")
    if not env.get("ok"):
        raise RuntimeError(f"wikipali error: {env.get('message') or env}")
    return env["data"] if unwrap else env


def emit_jsonl(rows: list[dict], *, source: str = "wikipali") -> None:
    """Write rows to stdout as jsonl with `_source` / `_fetched_at`."""
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for r in rows:
        r = {**r, "_source": source, "_fetched_at": fetched_at}
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
