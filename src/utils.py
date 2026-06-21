"""Shared utility helpers."""

from __future__ import annotations

import os
import csv
import hashlib
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _fallback_load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_environment() -> None:
    """Load .env values at program startup.

    Uses python-dotenv when available, with a small fallback parser so local
    development still works before dependencies are installed.
    """
    env_paths = [
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ]

    try:
        from dotenv import load_dotenv
    except ImportError:
        for path in env_paths:
            _fallback_load_env(path)
        return

    for path in env_paths:
        if path.exists():
            load_dotenv(path, override=False)


def load_settings() -> dict[str, Any]:
    """Load simple key settings without requiring a YAML dependency."""
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    text = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""

    def find_int(name: str, default: int) -> int:
        match = re.search(rf"^\s*{re.escape(name)}:\s*(\d+)\s*$", text, re.MULTILINE)
        return int(match.group(1)) if match else default

    def find_str(name: str, default: str) -> str:
        match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", text, re.MULTILINE)
        return match.group(1).strip().strip("'\"") if match else default

    def find_section_str(section: str, name: str, default: str) -> str:
        section_match = re.search(
            rf"^{re.escape(section)}:\s*$([\s\S]*?)(?=^[A-Za-z_][\w-]*:\s*$|\Z)",
            text,
            re.MULTILINE,
        )
        if not section_match:
            return default
        section_text = section_match.group(1)
        match = re.search(rf"^\s*{re.escape(name)}:\s*(.+?)\s*$", section_text, re.MULTILINE)
        return match.group(1).strip().strip("'\"") if match else default

    def find_section_int(section: str, name: str, default: int) -> int:
        value = find_section_str(section, name, "")
        return int(value) if value.isdigit() else default

    return {
        "days_back": find_section_int("search", "days_back", find_int("days_back", 14)),
        "max_results_per_source": find_section_int(
            "search", "max_results_per_source", find_int("max_results_per_source", 50)
        ),
        "sleep_seconds_between_requests": find_section_int(
            "api", "sleep_seconds_between_requests", find_int("sleep_seconds_between_requests", 1)
        ),
        "timeout_seconds": find_section_int("api", "timeout_seconds", find_int("timeout_seconds", 30)),
        "user_agent": find_section_str("api", "user_agent", find_str("user_agent", "edusoc-paper-radar/0.1")),
        "query": find_section_str(
            "search", "query", find_str("query", "sociology of education higher education vocational education")
        ),
        "papers_raw": find_section_str("outputs", "papers_raw", "outputs/papers_raw.csv"),
        "papers_deduplicated": find_section_str(
            "outputs", "papers_deduplicated", "outputs/papers_deduplicated.csv"
        ),
        "papers_ranked": find_section_str("outputs", "papers_ranked", "outputs/papers_ranked.csv"),
        "daily_digest": find_section_str("outputs", "daily_digest", "outputs/daily_digest.md"),
    }


def project_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_topic_keywords() -> list[str]:
    """Read keywords from config/topics.yaml.

    The parser is intentionally small and only looks for list entries inside
    `keywords:` blocks, so malformed display labels do not break fetching.
    """
    topics_path = PROJECT_ROOT / "config" / "topics.yaml"
    if not topics_path.exists():
        return []

    keywords: list[str] = []
    in_keywords = False
    keyword_indent = 0
    for raw_line in topics_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if stripped.startswith("keywords:"):
            in_keywords = True
            keyword_indent = indent
            continue
        if in_keywords and stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            if value and value not in keywords:
                keywords.append(value)
            continue
        if in_keywords and stripped and indent <= keyword_indent:
            in_keywords = False
    return keywords


def date_window(days_back: int) -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=days_back)).isoformat(), today.isoformat()


def cache_get_or_request(
    cache_dir: Path,
    cache_key: str,
    request_fn,
    sleep_seconds: int = 1,
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    path = cache_dir / f"{digest}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    time.sleep(sleep_seconds)
    payload = request_fn()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ensure_output_dir() -> Path:
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_session():
    import requests

    return requests.Session()
