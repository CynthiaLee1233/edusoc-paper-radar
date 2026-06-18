"""Robust Zotero Web API client and payload helpers."""

from __future__ import annotations

import csv
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

try:
    from .utils import PROJECT_ROOT, load_environment
except ImportError:
    from utils import PROJECT_ROOT, load_environment


ZOTERO_API_VERSION = "3"
RETRY_DELAYS_SECONDS = [2, 5, 10]
NETWORK_ERROR_HINT = (
    "\u5982\u679c\u4ecd\u7136\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5 VPN\u3001"
    "\u4ee3\u7406\u3001\u9632\u706b\u5899\u6216\u5f53\u524d\u7f51\u7edc\u8fde\u63a5\u3002"
)
AUTH_FAILURE_MESSAGE = (
    "Zotero \u8ba4\u8bc1\u5931\u8d25\uff1aAPI key \u6216 user ID \u53ef\u80fd\u4e0d\u6b63\u786e\u3002"
    "\u8bf7\u68c0\u67e5 .env \u4e2d\u7684 ZOTERO_API_KEY\u3001ZOTERO_USER_ID \u548c ZOTERO_LIBRARY_TYPE\uff0c"
    "\u5e76\u786e\u8ba4 API key \u6709\u8bfb\u53d6\u6587\u5e93\u7684\u6743\u9650\u3002"
)
COLLECTION_NOT_FOUND_MESSAGE = (
    "Zotero collection key \u53ef\u80fd\u4e0d\u6b63\u786e\uff1a\u627e\u4e0d\u5230\u8fd9\u4e2a collection\u3002"
    "\u8bf7\u8fd0\u884c python src/main.py --zotero-list-collections\uff0c"
    "\u7136\u540e\u628a\u6b63\u786e\u7684 Collection Key \u586b\u5230 .env \u91cc\u7684 ZOTERO_COLLECTION_KEY\u3002"
)
DEFAULT_IMPORT_THRESHOLD = 75
RANKED_PAPERS_PATH = PROJECT_ROOT / "outputs" / "papers_ranked.csv"
ZOTERO_IMPORT_LOG_PATH = PROJECT_ROOT / "outputs" / "zotero_import_log.csv"
IMPORT_LOG_FIELDS = [
    "timestamp",
    "status",
    "action",
    "title",
    "doi",
    "relevance_score",
    "message",
    "zotero_key",
]


@dataclass
class ZoteroCollection:
    name: str
    key: str
    parent: str = ""


class ZoteroTemporaryNetworkError(RuntimeError):
    """Raised after retryable Zotero network errors are exhausted."""


class ZoteroAuthenticationError(RuntimeError):
    """Raised when Zotero rejects the API credentials."""


class ZoteroCollectionNotFoundError(RuntimeError):
    """Raised when the configured Zotero collection key is not found."""


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _is_temporary_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


def build_collections_url(user_id: str, library_type: str) -> str:
    normalized = library_type.strip().lower()
    query = urlencode({"format": "json", "limit": "100"})
    if normalized == "user":
        return f"https://api.zotero.org/users/{user_id}/collections?{query}"
    if normalized == "group":
        return f"https://api.zotero.org/groups/{user_id}/collections?{query}"
    raise RuntimeError("ZOTERO_LIBRARY_TYPE must be either 'user' or 'group'")


def build_collection_url(user_id: str, library_type: str, collection_key: str) -> str:
    normalized = library_type.strip().lower()
    if normalized == "user":
        return f"https://api.zotero.org/users/{user_id}/collections/{collection_key}"
    if normalized == "group":
        return f"https://api.zotero.org/groups/{user_id}/collections/{collection_key}"
    raise RuntimeError("ZOTERO_LIBRARY_TYPE must be either 'user' or 'group'")


def build_items_url(user_id: str, library_type: str) -> str:
    normalized = library_type.strip().lower()
    if normalized == "user":
        return f"https://api.zotero.org/users/{user_id}/items"
    if normalized == "group":
        return f"https://api.zotero.org/groups/{user_id}/items"
    raise RuntimeError("ZOTERO_LIBRARY_TYPE must be either 'user' or 'group'")


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    cleaned = doi.strip().lower()
    cleaned = cleaned.removeprefix("https://doi.org/")
    cleaned = cleaned.removeprefix("http://dx.doi.org/")
    cleaned = cleaned.removeprefix("doi:")
    return cleaned.strip()


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    title = title.lower().replace("&", " and ")
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


class ZoteroClient:
    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Zotero-API-Key": api_key,
                "Zotero-API-Version": ZOTERO_API_VERSION,
                "User-Agent": "edusoc-paper-radar/0.1",
            }
        )

    def get_json(self, url: str) -> Any:
        print("\u6b63\u5728\u8fde\u63a5 Zotero API")
        last_error: Exception | None = None

        for attempt in range(1, len(RETRY_DELAYS_SECONDS) + 2):
            try:
                response = self.session.get(url, timeout=(10, 30))
                if _is_temporary_status(response.status_code):
                    last_error = requests.HTTPError(
                        f"Zotero API returned temporary HTTP {response.status_code}",
                        response=response,
                    )
                    if attempt <= len(RETRY_DELAYS_SECONDS):
                        self._wait_before_retry(attempt)
                        continue
                    break
                response.raise_for_status()
                return response.json()
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as error:
                last_error = error
                if attempt <= len(RETRY_DELAYS_SECONDS):
                    self._wait_before_retry(attempt)
                    continue
                break

        raise ZoteroTemporaryNetworkError(
            f"Zotero API \u8fde\u63a5\u5931\u8d25\uff1a{last_error}\n{NETWORK_ERROR_HINT}"
        )

    def post_json(self, url: str, payload: Any) -> Any:
        print("\u6b63\u5728\u8fde\u63a5 Zotero API")
        last_error: Exception | None = None

        for attempt in range(1, len(RETRY_DELAYS_SECONDS) + 2):
            try:
                response = self.session.post(url, json=payload, timeout=(10, 30))
                if _is_temporary_status(response.status_code):
                    last_error = requests.HTTPError(
                        f"Zotero API returned temporary HTTP {response.status_code}",
                        response=response,
                    )
                    if attempt <= len(RETRY_DELAYS_SECONDS):
                        self._wait_before_retry(attempt)
                        continue
                    break
                response.raise_for_status()
                return response.json() if response.content else {}
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as error:
                last_error = error
                if attempt <= len(RETRY_DELAYS_SECONDS):
                    self._wait_before_retry(attempt)
                    continue
                break

        raise ZoteroTemporaryNetworkError(
            f"Zotero API \u8fde\u63a5\u5931\u8d25\uff1a{last_error}\n{NETWORK_ERROR_HINT}"
        )

    @staticmethod
    def _wait_before_retry(attempt: int) -> None:
        delay = RETRY_DELAYS_SECONDS[attempt - 1]
        print(f"\u7b2c{attempt}\u6b21\u91cd\u8bd5\uff0c{delay}\u79d2\u540e\u518d\u8bd5...")
        time.sleep(delay)


def _client_from_env() -> tuple[ZoteroClient, str, str]:
    load_environment()
    api_key = _required_env("ZOTERO_API_KEY")
    user_id = _required_env("ZOTERO_USER_ID")
    library_type = _required_env("ZOTERO_LIBRARY_TYPE")
    return ZoteroClient(api_key), user_id, library_type


def fetch_zotero_collections() -> list[ZoteroCollection]:
    client, user_id, library_type = _client_from_env()
    url = build_collections_url(user_id, library_type)
    try:
        payload: list[dict[str, Any]] = client.get_json(url)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        if status_code in {401, 403}:
            raise ZoteroAuthenticationError(AUTH_FAILURE_MESSAGE) from error
        raise RuntimeError(f"Zotero API request failed with HTTP {status_code}") from error

    collections: list[ZoteroCollection] = []
    for item in payload:
        data = item.get("data", {})
        collections.append(
            ZoteroCollection(
                name=data.get("name", ""),
                key=data.get("key") or item.get("key", ""),
                parent=data.get("parentCollection") or "",
            )
        )
    return collections


def fetch_zotero_collection_for_test() -> tuple[str, ZoteroCollection]:
    client, user_id, library_type = _client_from_env()
    collection_key = _required_env("ZOTERO_COLLECTION_KEY")
    url = build_collection_url(user_id, library_type, collection_key)
    try:
        payload: dict[str, Any] = client.get_json(url)
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        if status_code == 403:
            raise ZoteroAuthenticationError(AUTH_FAILURE_MESSAGE) from error
        if status_code == 404:
            raise ZoteroCollectionNotFoundError(COLLECTION_NOT_FOUND_MESSAGE) from error
        raise RuntimeError(f"Zotero API request failed with HTTP {status_code}") from error

    data = payload.get("data", {})
    return library_type, ZoteroCollection(
        name=data.get("name", ""),
        key=data.get("key") or payload.get("key", collection_key),
        parent=data.get("parentCollection") or "",
    )


def _raise_friendly_http_error(error: requests.HTTPError) -> None:
    status_code = error.response.status_code if error.response is not None else None
    if status_code == 403:
        raise ZoteroAuthenticationError(AUTH_FAILURE_MESSAGE) from error
    if status_code == 404:
        raise ZoteroCollectionNotFoundError(COLLECTION_NOT_FOUND_MESSAGE) from error
    raise RuntimeError(f"Zotero API request failed with HTTP {status_code}") from error


def format_connection_test(library_type: str, collection_name: str | ZoteroCollection, collection_key: str | None = None) -> str:
    if isinstance(collection_name, ZoteroCollection):
        collection = collection_name
    else:
        collection = ZoteroCollection(name=collection_name, key=collection_key or "")
    return "\n".join(
        [
            "Zotero connection OK",
            f"Library type: {library_type}",
            f"Collection name: {collection.name}",
            f"Collection key: {collection.key}",
        ]
    )


def format_collections_table(collections: list[ZoteroCollection]) -> str:
    headers = ["Collection Name", "Collection Key", "Parent Collection"]
    rows = [[collection.name, collection.key, collection.parent] for collection in collections]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]

    def format_row(row: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join([format_row(headers), separator, *[format_row(row) for row in rows]])


def read_ranked_papers(path: Path | None = None) -> list[dict[str, str]]:
    path = path or RANKED_PAPERS_PATH
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _score_value(paper: dict[str, str]) -> int:
    try:
        return int(float(paper.get("relevance_score") or 0))
    except ValueError:
        return 0


def filter_import_candidates(
    papers: list[dict[str, str]],
    threshold: int = DEFAULT_IMPORT_THRESHOLD,
) -> list[dict[str, str]]:
    return [paper for paper in papers if _score_value(paper) >= threshold]


def _split_authors(authors: str) -> list[dict[str, str]]:
    creators: list[dict[str, str]] = []
    for raw_author in re.split(r";|\band\b", authors or ""):
        name = raw_author.strip()
        if name:
            creators.append({"creatorType": "author", "name": name})
    return creators


def _tags_from_paper(paper: dict[str, str]) -> list[dict[str, str]]:
    tags = ["paper-radar", "education-sociology"]
    for keyword in (paper.get("matched_keywords") or "").split(";"):
        keyword = keyword.strip()
        if keyword:
            tags.append(keyword)
    source_api = (paper.get("source_api") or "").strip()
    if source_api:
        tags.append(source_api)
    deduped = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return [{"tag": tag} for tag in deduped]


def build_zotero_item_payload(paper: dict[str, str], collection_key: str) -> dict[str, Any]:
    extra_lines = [
        f"Paper Radar relevance_score: {paper.get('relevance_score', '')}",
        f"Paper Radar relevance_reason_cn: {paper.get('relevance_reason_cn', '')}",
    ]
    doi = normalize_doi(paper.get("doi"))
    return {
        "itemType": "journalArticle",
        "title": paper.get("title") or "",
        "creators": _split_authors(paper.get("authors", "")),
        "date": paper.get("publication_date") or "",
        "publicationTitle": paper.get("source_journal") or "",
        "DOI": doi,
        "url": paper.get("url") or "",
        "abstractNote": paper.get("abstract") or "",
        "collections": [collection_key],
        "tags": _tags_from_paper(paper),
        "extra": "\n".join(extra_lines),
    }


def _query_items(client: ZoteroClient, user_id: str, library_type: str, query: str) -> list[dict[str, Any]]:
    params = urlencode({"format": "json", "limit": "25", "q": query})
    url = f"{build_items_url(user_id, library_type)}?{params}"
    return client.get_json(url)


def find_duplicate(
    client: ZoteroClient,
    user_id: str,
    library_type: str,
    paper: dict[str, str],
) -> dict[str, Any] | None:
    doi = normalize_doi(paper.get("doi"))
    if doi:
        for item in _query_items(client, user_id, library_type, doi):
            data = item.get("data", {})
            if normalize_doi(data.get("DOI")) == doi:
                return item
        return None

    title = normalize_title(paper.get("title"))
    if not title:
        return None
    for item in _query_items(client, user_id, library_type, paper.get("title", "")):
        data = item.get("data", {})
        if normalize_title(data.get("title")) == title:
            return item
    return None


def _append_import_log(rows: list[dict[str, Any]], log_path: Path | None = None) -> None:
    log_path = log_path or ZOTERO_IMPORT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=IMPORT_LOG_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _created_key(response_payload: Any) -> str:
    successful = response_payload.get("successful", {}) if isinstance(response_payload, dict) else {}
    if not successful:
        return ""
    first = next(iter(successful.values()))
    return first.get("key", "") if isinstance(first, dict) else ""


def import_ranked_papers_to_zotero(
    ranked_path: Path | None = None,
    dry_run: bool = False,
    threshold: int = DEFAULT_IMPORT_THRESHOLD,
    log_path: Path | None = None,
) -> list[dict[str, Any]]:
    client, user_id, library_type = _client_from_env()
    collection_key = _required_env("ZOTERO_COLLECTION_KEY")
    papers = filter_import_candidates(read_ranked_papers(ranked_path), threshold)
    items_url = build_items_url(user_id, library_type)
    log_rows: list[dict[str, Any]] = []

    for paper in papers:
        timestamp = datetime.now().isoformat(timespec="seconds")
        title = paper.get("title", "")
        doi = normalize_doi(paper.get("doi"))
        score = paper.get("relevance_score", "")
        try:
            duplicate = find_duplicate(client, user_id, library_type, paper)
        except requests.HTTPError as error:
            _raise_friendly_http_error(error)
        if duplicate:
            log_rows.append(
                {
                    "timestamp": timestamp,
                    "status": "skipped",
                    "action": "duplicate",
                    "title": title,
                    "doi": doi,
                    "relevance_score": score,
                    "message": "Duplicate exists in Zotero; skipped.",
                    "zotero_key": duplicate.get("key", ""),
                }
            )
            continue

        payload = build_zotero_item_payload(paper, collection_key)
        if dry_run:
            log_rows.append(
                {
                    "timestamp": timestamp,
                    "status": "dry-run",
                    "action": "would-create",
                    "title": title,
                    "doi": doi,
                    "relevance_score": score,
                    "message": "Dry run only; Zotero item was not created.",
                    "zotero_key": "",
                }
            )
            continue

        try:
            response_payload = client.post_json(items_url, [payload])
        except requests.HTTPError as error:
            _raise_friendly_http_error(error)
        log_rows.append(
            {
                "timestamp": timestamp,
                "status": "created",
                "action": "create",
                "title": title,
                "doi": doi,
                "relevance_score": score,
                "message": "Created journalArticle item in Zotero.",
                "zotero_key": _created_key(response_payload),
            }
        )

    _append_import_log(log_rows, log_path)
    print(f"Zotero import finished: {len(log_rows)} records logged.")
    return log_rows
