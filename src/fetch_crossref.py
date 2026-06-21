"""Fetch paper metadata from the official Crossref REST API."""

from __future__ import annotations

import os
from typing import Any

try:
    from .utils import PROJECT_ROOT, cache_get_or_request, date_window, get_session, load_environment, load_settings
except ImportError:
    from utils import PROJECT_ROOT, cache_get_or_request, date_window, get_session, load_environment, load_settings


CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def _date_parts_to_iso(parts: list[list[int]] | None) -> str:
    if not parts or not parts[0]:
        return ""
    year = parts[0][0]
    month = parts[0][1] if len(parts[0]) > 1 else 1
    day = parts[0][2] if len(parts[0]) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _safe_params(params: dict[str, str]) -> dict[str, str]:
    safe = dict(params)
    if "mailto" in safe:
        safe["mailto"] = "***"
    return safe


def _normalize_item(item: dict[str, Any]) -> dict[str, str]:
    title = " ".join(item.get("title") or [])
    authors = [
        " ".join(part for part in [author.get("given"), author.get("family")] if part)
        for author in item.get("author", [])
    ]
    published = item.get("published-print") or item.get("published-online") or item.get("published")
    publication_date = _date_parts_to_iso((published or {}).get("date-parts"))
    journal = "; ".join(item.get("container-title") or [])
    return {
        "title": title,
        "year": publication_date[:4],
        "doi": item.get("DOI") or "",
        "source": "crossref",
        "journal": journal,
        "url": item.get("URL") or "",
        "abstract": item.get("abstract") or "",
        "score": "0",
        "authors": "; ".join(author for author in authors if author),
        "publication_date": publication_date,
        "source_journal": journal,
        "citation_count": str(item.get("is-referenced-by-count") or 0),
        "source_api": "Crossref",
    }


def fetch_crossref(
    keywords: list[str] | str,
    days_back: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    load_environment()
    settings = load_settings()
    from_date, today = date_window(days_back or settings["days_back"])
    max_results = max_results or settings["max_results_per_source"]
    sleep_seconds = settings["sleep_seconds_between_requests"]
    timeout = settings["timeout_seconds"]
    user_agent = settings["user_agent"]
    email = os.environ.get("USER_EMAIL", "")
    session = get_session()
    headers = {
        "User-Agent": f"{user_agent} (mailto:{email})" if email else user_agent,
    }
    cache_dir = PROJECT_ROOT / "data" / "cache" / "crossref"
    queries = [keywords] if isinstance(keywords, str) else keywords
    papers: list[dict[str, str]] = []

    for query in queries:
        params = {
            "query": query,
            "filter": (
                f"from-pub-date:{from_date},"
                f"until-pub-date:{today},"
                "type:journal-article"
            ),
            "rows": str(max_results),
            "sort": "published",
            "order": "desc",
        }
        if email:
            params["mailto"] = email
        cache_key = f"crossref:{params}"

        def request_fn(params=params) -> dict[str, Any]:
            print(
                f"[paper-radar] Crossref 请求：query={query}，filter={params['filter']}，rows={max_results}",
                flush=True,
            )
            response = session.get(CROSSREF_WORKS_URL, params=params, headers=headers, timeout=timeout)
            print(f"[paper-radar] Crossref HTTP 状态码：{response.status_code}", flush=True)
            if response.status_code == 400:
                print(f"[paper-radar] Crossref 安全请求参数：{_safe_params(params)}", flush=True)
                print(f"[paper-radar] Crossref HTTP 400 响应正文：{response.text[:1000]}", flush=True)
            response.raise_for_status()
            return response.json()

        payload = cache_get_or_request(cache_dir, cache_key, request_fn, sleep_seconds)
        items = payload.get("message", {}).get("items", [])
        print(f"[paper-radar] Crossref 实际返回结果数：{len(items)}", flush=True)
        papers.extend(_normalize_item(item) for item in items if item.get("title"))

    return papers
