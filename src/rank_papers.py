"""Rank deduplicated papers for the education sociology radar."""

from __future__ import annotations

import csv
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .utils import PROJECT_ROOT, write_csv
except ImportError:
    from utils import PROJECT_ROOT, write_csv


TOPIC_KEYWORDS = {
    "sociology of education": 8,
    "educational inequality": 7,
    "higher education": 7,
    "vocational education": 7,
    "vocational college students": 8,
    "tvet students": 7,
    "technical and vocational education": 7,
    "career adaptability": 8,
    "career adapt-abilities": 7,
    "career construction": 6,
    "sustainable employability": 8,
    "graduate employability": 6,
    "digital student support": 7,
    "student support system": 5,
    "learning analytics student support": 6,
    "school-to-work transition": 8,
    "social capital education": 5,
    "career self-efficacy": 5,
    "professional identity": 5,
    "perceived social support": 5,
}

METHOD_KEYWORDS = {
    "structural equation modeling": 5,
    "sem": 5,
    "latent profile analysis": 5,
    "lpa": 5,
    "mixed methods": 4,
    "explanatory sequential design": 4,
    "longitudinal": 3,
    "mediation model": 3,
    "person-centered approach": 3,
}

HIGH_PRIORITY_JOURNALS = {
    "sociology of education": 6,
    "british journal of sociology of education": 5,
    "higher education": 5,
    "studies in higher education": 5,
    "research in higher education": 5,
    "journal of vocational behavior": 5,
    "educational researcher": 4,
    "review of educational research": 4,
    "educational research review": 4,
}

PENALTY_KEYWORDS = {
    "clinical medicine": 8,
    "molecular biology": 8,
    "engineering materials": 8,
    "materials engineering": 8,
    "unrelated computer science": 6,
    "computer vision": 5,
    "deep learning": 4,
    "k-12 mathematics teaching": 5,
    "mathematics teaching": 4,
}

K12_ALLOWED_CONTEXT = [
    "inequality",
    "transition",
    "career",
    "employability",
    "sociology",
    "stratification",
]

RANKED_FIELDS = [
    "title",
    "authors",
    "publication_date",
    "source_journal",
    "doi",
    "url",
    "abstract",
    "citation_count",
    "source_api",
    "relevance_score",
    "topic_score",
    "method_score",
    "journal_score",
    "recency_score",
    "influence_score",
    "matched_keywords",
    "relevance_reason_cn",
]


def _text_for_matching(paper: dict[str, Any]) -> str:
    return " ".join(
        str(paper.get(key, ""))
        for key in ["title", "abstract", "source_journal", "venue", "journal"]
    ).lower()


def _keyword_matches(text: str, keyword: str) -> bool:
    keyword_lower = keyword.lower()
    if re.fullmatch(r"[a-z0-9 -]+", keyword_lower):
        return re.search(rf"\b{re.escape(keyword_lower)}\b", text) is not None
    return keyword_lower in text


def _score_keywords(text: str, weights: dict[str, int]) -> tuple[int, list[str]]:
    matched = [keyword for keyword in weights if _keyword_matches(text, keyword)]
    return sum(weights[keyword] for keyword in matched), matched


def _journal_score(paper: dict[str, Any]) -> int:
    journal = str(paper.get("source_journal") or paper.get("venue") or "").lower()
    return max((weight for name, weight in HIGH_PRIORITY_JOURNALS.items() if name in journal), default=0)


def _recency_score(publication_date: str) -> int:
    if not publication_date:
        return 0
    try:
        published = date.fromisoformat(publication_date[:10])
    except ValueError:
        return 0
    age_days = max((date.today() - published).days, 0)
    if age_days <= 30:
        return 5
    if age_days <= 180:
        return 3
    if age_days <= 365:
        return 1
    return 0


def _influence_score(citation_count: str | int | None) -> int:
    try:
        count = int(float(citation_count or 0))
    except ValueError:
        count = 0
    if count <= 0:
        return 0
    return min(5, int(math.log10(count + 1) * 2))


def _penalty_score(text: str) -> tuple[int, list[str]]:
    penalty, matched = _score_keywords(text, PENALTY_KEYWORDS)
    if ("k-12" in text or "mathematics teaching" in text) and any(term in text for term in K12_ALLOWED_CONTEXT):
        penalty = max(0, penalty - 4)
    return penalty, matched


def _reason_cn(matched: list[str], penalty_matches: list[str]) -> str:
    if matched:
        terms = "\u3001".join(matched[:6])
        reason = f"\u76f8\u5173\u6027\uff1a\u547d\u4e2d\u201c{terms}\u201d\u7b49\u6838\u5fc3\u4e3b\u9898\u6216\u65b9\u6cd5\u3002"
    else:
        reason = "\u76f8\u5173\u6027\uff1a\u4e3b\u9898\u4fe1\u53f7\u8f83\u5f31\uff0c\u5efa\u8bae\u4eba\u5de5\u590d\u6838\u3002"
    if penalty_matches:
        penalties = "\u3001".join(penalty_matches[:3])
        reason += f"\u6ce8\u610f\uff1a\u51fa\u73b0\u201c{penalties}\u201d\u7b49\u53ef\u80fd\u4e0d\u76f8\u5173\u9886\u57df\u4fe1\u53f7\u3002"
    return reason


def rank_paper(paper: dict[str, Any]) -> dict[str, Any]:
    text = _text_for_matching(paper)
    topic_score, topic_matches = _score_keywords(text, TOPIC_KEYWORDS)
    method_score, method_matches = _score_keywords(text, METHOD_KEYWORDS)
    journal_score = _journal_score(paper)
    recency_score = _recency_score(str(paper.get("publication_date", "")))
    influence_score = _influence_score(paper.get("citation_count"))
    penalty_score, penalty_matches = _penalty_score(text)
    matched = topic_matches + method_matches
    raw_relevance_score = topic_score + method_score + journal_score + recency_score + influence_score - penalty_score
    relevance_score = max(0, min(100, raw_relevance_score))

    ranked = dict(paper)
    ranked.update(
        {
            "relevance_score": str(relevance_score),
            "topic_score": str(topic_score),
            "method_score": str(method_score),
            "journal_score": str(journal_score),
            "recency_score": str(recency_score),
            "influence_score": str(influence_score),
            "matched_keywords": "; ".join(matched),
            "relevance_reason_cn": _reason_cn(matched, penalty_matches),
        }
    )
    return ranked


def rank_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [rank_paper(paper) for paper in papers]
    return sorted(ranked, key=lambda paper: int(paper.get("relevance_score", "0")), reverse=True)


def read_papers_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def rank_papers_csv(
    input_path: Path | None = None,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    input_path = input_path or PROJECT_ROOT / "outputs" / "papers_deduplicated.csv"
    output_path = output_path or PROJECT_ROOT / "outputs" / "papers_ranked.csv"
    ranked = rank_papers(read_papers_csv(input_path))
    write_csv(output_path, ranked, RANKED_FIELDS)
    return ranked
