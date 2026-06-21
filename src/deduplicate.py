"""Paper deduplication helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from .utils import PROJECT_ROOT, write_csv
except ImportError:
    from utils import PROJECT_ROOT, write_csv


DEDUPLICATED_FIELDS = [
    "title",
    "year",
    "authors",
    "publication_date",
    "journal",
    "source_journal",
    "doi",
    "url",
    "abstract",
    "citation_count",
    "source",
    "source_api",
    "score",
]


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


def _has_value(paper: dict[str, Any], *keys: str) -> bool:
    return any(str(paper.get(key, "")).strip() for key in keys)


def record_richness_score(paper: dict[str, Any]) -> int:
    """Score a record by metadata completeness.

    The fields mirror the requested priority: DOI, abstract, journal/source,
    URL, and citation count.
    """
    score = 0
    if normalize_doi(str(paper.get("doi", ""))):
        score += 1
    if _has_value(paper, "abstract"):
        score += 1
    if _has_value(paper, "source_journal", "venue", "journal", "source"):
        score += 1
    if _has_value(paper, "url"):
        score += 1
    if _has_value(paper, "citation_count", "cited_by_count"):
        score += 1
    return score


def choose_richer_record(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_score = record_richness_score(left)
    right_score = record_richness_score(right)
    richer, poorer = (right, left) if right_score > left_score else (left, right)

    merged = dict(richer)
    for key, value in poorer.items():
        if not str(merged.get(key, "")).strip() and str(value).strip():
            merged[key] = value
    merged["doi"] = normalize_doi(str(merged.get("doi", ""))) or str(merged.get("doi", ""))
    merged["journal"] = merged.get("journal") or merged.get("source_journal", "")
    merged["source_journal"] = merged.get("source_journal") or merged.get("journal", "")
    merged["source"] = merged.get("source") or merged.get("source_api", "")
    merged["source_api"] = merged.get("source_api") or merged.get("source", "")
    merged["year"] = str(merged.get("year") or str(merged.get("publication_date", ""))[:4])
    return merged


def _dedupe_key(paper: dict[str, Any]) -> str:
    doi = normalize_doi(str(paper.get("doi", "")))
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_title(str(paper.get('title', '')))}"


def deduplicate_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by DOI first, then normalized title when DOI is missing."""
    by_key: dict[str, dict[str, Any]] = {}

    for paper in papers:
        normalized = dict(paper)
        normalized["doi"] = normalize_doi(str(normalized.get("doi", ""))) or normalized.get("doi", "")
        normalized["journal"] = normalized.get("journal") or normalized.get("source_journal", "")
        normalized["source_journal"] = normalized.get("source_journal") or normalized.get("journal", "")
        normalized["source"] = normalized.get("source") or normalized.get("source_api", "")
        normalized["source_api"] = normalized.get("source_api") or normalized.get("source", "")
        normalized["year"] = str(normalized.get("year") or str(normalized.get("publication_date", ""))[:4])
        key = _dedupe_key(normalized)
        if key in by_key:
            by_key[key] = choose_richer_record(by_key[key], normalized)
        else:
            by_key[key] = normalized

    return list(by_key.values())


def save_deduplicated_papers(
    papers: list[dict[str, Any]],
    output_path: Path | None = None,
) -> Path:
    output_path = output_path or PROJECT_ROOT / "outputs" / "papers_deduplicated.csv"
    write_csv(output_path, papers, DEDUPLICATED_FIELDS)
    return output_path
