"""Fetch paper metadata from the official OpenAlex API."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import requests

try:
    from .utils import PROJECT_ROOT, date_window, load_environment, load_settings
except ImportError:
    from utils import PROJECT_ROOT, date_window, load_environment, load_settings


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_SELECT_FIELDS = "id,doi,display_name,publication_year,primary_location"
REQUEST_TIMEOUT = (5, 30)
REQUEST_HEADERS = {
    "User-Agent": "edusoc-paper-radar/0.1",
    "Accept": "application/json",
}


def _safe_text(message: str) -> str:
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    if api_key:
        message = message.replace(api_key, "***")
    return message


def _safe_error(error: Exception) -> str:
    return _safe_text(str(error))


def _cache_openalex_payload(cache_key: str, payload: dict[str, Any]) -> None:
    cache_dir = PROJECT_ROOT / "data" / "cache" / "openalex"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    path = cache_dir / f"{digest}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_work(item: dict[str, Any]) -> dict[str, str]:
    primary_location = item.get("primary_location") or {}
    venue = primary_location.get("source") or {}
    doi = (item.get("doi") or "").replace("https://doi.org/", "")
    year = str(item.get("publication_year") or "")
    journal = venue.get("display_name") or ""
    url = (
        item.get("doi")
        or primary_location.get("landing_page_url")
        or item.get("id")
        or ""
    )
    return {
        "title": item.get("display_name") or "",
        "year": year,
        "authors": "",
        "publication_date": year,
        "journal": journal,
        "source_journal": journal,
        "doi": doi,
        "url": url,
        "abstract": "",
        "citation_count": "",
        "source": "openalex",
        "source_api": "OpenAlex",
        "score": "0",
    }


def _request_openalex(session: requests.Session, params: dict[str, str], attempt_label: str) -> dict[str, Any]:
    print(f"[paper-radar] OpenAlex 请求即将开始：{attempt_label}", flush=True)
    response = session.get(
        OPENALEX_WORKS_URL,
        params=params,
        headers=REQUEST_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    print(f"[paper-radar] OpenAlex 请求已返回：HTTP {response.status_code}", flush=True)
    if response.status_code == 400:
        print(f"[paper-radar] OpenAlex HTTP 400 响应正文：{_safe_text(response.text[:1000])}", flush=True)
    response.raise_for_status()
    return response.json()


def fetch_openalex(
    keywords: list[str] | str,
    days_back: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    """Search OpenAlex with compact fields and robust requests behavior."""
    load_environment()
    settings = load_settings()
    from_date, _to_date = date_window(days_back or int(settings["days_back"]))
    per_page = max_results or int(settings["max_results_per_source"])
    sleep_seconds = int(settings["sleep_seconds_between_requests"])
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    queries = [keywords] if isinstance(keywords, str) else keywords
    papers: list[dict[str, str]] = []
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    for query in queries:
        params = {
            "search": query,
            "per_page": str(per_page),
            "filter": f"from_publication_date:{from_date}",
            "select": OPENALEX_SELECT_FIELDS,
        }
        if api_key:
            params["api_key"] = api_key

        print(f"[paper-radar] OpenAlex query：{query}", flush=True)
        print(f"[paper-radar] OpenAlex from_publication_date：{from_date}", flush=True)
        print(f"[paper-radar] OpenAlex per_page：{per_page}", flush=True)
        print(f"[paper-radar] OPENALEX_API_KEY 是否已加载：{'是' if api_key else '否'}", flush=True)

        try:
            time.sleep(sleep_seconds)
            payload = _request_openalex(session, params, "首次请求")
        except Exception as error:
            print(f"[paper-radar] OpenAlex 首次请求失败或超时，具体错误：{_safe_error(error)}", flush=True)
            print("[paper-radar] 将忽略系统代理环境变量，重试 1 次。", flush=True)
            session.trust_env = False
            try:
                payload = _request_openalex(session, params, "关闭系统代理后的重试")
            except Exception as retry_error:
                print(f"[paper-radar] OpenAlex 重试仍然失败，具体错误：{_safe_error(retry_error)}", flush=True)
                raise

        meta = payload.get("meta", {})
        results = payload.get("results", [])
        print(f"[paper-radar] OpenAlex meta.count：{meta.get('count', 0)}", flush=True)
        print(f"[paper-radar] OpenAlex 实际返回结果数：{len(results)}", flush=True)
        _cache_openalex_payload(f"openalex:{params}", payload)
        papers.extend(_normalize_work(item) for item in results if item.get("display_name"))

    return papers
