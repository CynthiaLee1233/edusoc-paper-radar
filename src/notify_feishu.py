"""Feishu custom bot notification support."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

try:
    from .utils import PROJECT_ROOT, load_environment
except ImportError:
    from utils import PROJECT_ROOT, load_environment


DIGEST_PATH = PROJECT_ROOT / "outputs" / "daily_digest.md"
ZOTERO_LOG_PATH = PROJECT_ROOT / "outputs" / "zotero_import_log.csv"
FEISHU_LOG_PATH = PROJECT_ROOT / "outputs" / "feishu_push_log.csv"
LOG_FIELDS = ["timestamp", "status", "section", "message"]
MAX_MESSAGE_CHARS = 3500


def build_feishu_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def read_digest(path: Path | None = None) -> str:
    path = path or DIGEST_PATH
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_zotero_status(path: Path | None = None) -> str:
    path = path or ZOTERO_LOG_PATH
    if not path.exists():
        return "Zotero import status: \u6682\u65e0\u5bfc\u5165\u65e5\u5fd7\u3002"
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return "Zotero import status: \u6682\u65e0\u5bfc\u5165\u8bb0\u5f55\u3002"
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    summary = "\uff1b".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    return f"Zotero import status: {summary}"


def _extract_between(text: str, start_marker: str, end_markers: list[str]) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    end = len(text)
    for marker in end_markers:
        marker_index = text.find(marker, start + len(start_marker))
        if marker_index != -1:
            end = min(end, marker_index)
    return text[start:end].strip()


def split_digest_sections(digest: str, zotero_status: str) -> list[tuple[str, str]]:
    overview = _extract_between(digest, "## 1.", ["## 2.", "## 3.", "## 4.", "## 5."])
    top_papers = _extract_between(digest, "## 2.", ["## 3.", "## 4.", "## 5."])
    trends = "\n\n".join(
        part
        for part in [
            _extract_between(digest, "## 3.", ["## 4.", "## 5."]),
            _extract_between(digest, "## 4.", ["## 5."]),
            _extract_between(digest, "## 5.", []),
        ]
        if part
    )
    sections = [
        ("overview", overview or digest[:MAX_MESSAGE_CHARS]),
        ("top_5_papers", top_papers or "\u6682\u65e0 Top 5 \u8bba\u6587\u5185\u5bb9\u3002"),
        ("zotero_import_status", zotero_status),
        ("trend_keywords_and_suggestions", trends or "\u6682\u65e0\u8d8b\u52bf\u5173\u952e\u8bcd\u548c\u5efa\u8bae\u3002"),
    ]
    return [(name, content[:MAX_MESSAGE_CHARS]) for name, content in sections]


def build_message_payload(content: str, secret: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": content},
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = build_feishu_sign(timestamp, secret)
    return payload


def _append_log(rows: list[dict[str, str]], log_path: Path | None = None) -> None:
    log_path = log_path or FEISHU_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def notify_feishu(dry_run: bool = False) -> list[dict[str, str]]:
    load_environment()
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    secret = os.environ.get("FEISHU_SECRET", "")
    digest = read_digest()
    sections = split_digest_sections(digest, read_zotero_status())
    log_rows: list[dict[str, str]] = []

    if not dry_run and not webhook_url:
        raise RuntimeError("Missing required environment variable: FEISHU_WEBHOOK_URL")

    for section_name, content in sections:
        timestamp = datetime.now().isoformat(timespec="seconds")
        if dry_run:
            log_rows.append(
                {
                    "timestamp": timestamp,
                    "status": "dry-run",
                    "section": section_name,
                    "message": "Dry run only; Feishu message was not sent.",
                }
            )
            print(f"Feishu dry-run: {section_name}")
            continue

        payload = build_message_payload(content, secret or None)
        response = requests.post(webhook_url, json=payload, timeout=(10, 30))
        if response.status_code >= 400:
            log_rows.append(
                {
                    "timestamp": timestamp,
                    "status": "failed",
                    "section": section_name,
                    "message": f"HTTP {response.status_code}",
                }
            )
            response.raise_for_status()
        log_rows.append(
            {
                "timestamp": timestamp,
                "status": "sent",
                "section": section_name,
                "message": "Message sent to Feishu.",
            }
        )

    _append_log(log_rows)
    return log_rows


def push_to_feishu(message: str) -> bool:
    """Backward-compatible simple push helper."""
    load_environment()
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not webhook_url:
        return False
    payload = build_message_payload(message, os.environ.get("FEISHU_SECRET") or None)
    response = requests.post(webhook_url, json=payload, timeout=(10, 30))
    response.raise_for_status()
    return True
