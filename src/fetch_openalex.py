"""Fetch paper metadata from the official OpenAlex API."""

from __future__ import annotations

import os
from typing import Any

try:
    from .utils import PROJECT_ROOT, cache_get_or_request, date_window, get_session, load_environment, load_settings
except ImportError:
    from utils import PROJECT_ROOT, cache_get_or_request, date_window, get_session, load_environment, load_settings


OPENALEX_WORKS_URL = "https://api.openalex.org/works"


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))


def _normalize_work(item: dict[str, Any]) -> dict[str, str]:
    venue = (item.get("primary_location") or {}).get("source") or {}
    authors = [
        (authorship.get("author") or {}).get("display_name", "")
        for authorship in item.get("authorships", [])
        if (authorship.get("author") or {}).get("display_name")
    ]
    doi = (item.get("doi") or "").replace("https://doi.org/", "")
    return {
        "title": item.get("title") or "",
        "authors": "; ".join(authors),
        "publication_date": item.get("publication_date") or "",
        "source_journal": venue.get("display_name") or "",
        "doi": doi,
        "url": item.get("id") or item.get("doi") or "",
        "abstract": _abstract_from_inverted_index(item.get("abstract_inverted_index")),
        "citation_count": str(item.get("cited_by_count") or 0),
        "source_api": "OpenAlex",
    }


def fetch_openalex(
    keywords: list[str],
    days_back: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    load_environment()
    settings = load_settings()
    from_date, to_date = date_window(days_back or settings["days_back"])
    max_results = max_results or settings["max_results_per_source"]
    sleep_seconds = settings["sleep_seconds_between_requests"]
    timeout = settings["timeout_seconds"]
    user_agent = settings["user_agent"]
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    session = get_session()
    headers = {"User-Agent": user_agent}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    papers: list[dict[str, str]] = []
    cache_dir = PROJECT_ROOT / "data" / "cache" / "openalex"

    for keyword in keywords:
        params = {
            "search": keyword,
            "filter": f"from_publication_date:{from_date},to_publication_date:{to_date}",
            "per-page": str(max_results),
        }
        if api_key:
            params["api_key"] = api_key
        cache_key = f"openalex:{params}"

        def request_fn(params=params) -> dict[str, Any]:
            response = session.get(OPENALEX_WORKS_URL, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()

        payload = cache_get_or_request(cache_dir, cache_key, request_fn, sleep_seconds)
        papers.extend(_normalize_work(item) for item in payload.get("results", []) if item.get("title"))

    return papers
