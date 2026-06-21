"""Generate the Chinese daily paper digest."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .utils import PROJECT_ROOT
except ImportError:
    from utils import PROJECT_ROOT


INPUT_PATH = PROJECT_ROOT / "outputs" / "papers_ranked.csv"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "daily_digest.md"


def read_ranked_papers(path: Path | None = None) -> list[dict[str, str]]:
    path = path or INPUT_PATH
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _score(paper: dict[str, Any]) -> int:
    try:
        return int(float(paper.get("relevance_score") or paper.get("score") or 0))
    except ValueError:
        return 0


def _sorted_papers(papers: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(papers, key=_score, reverse=True)


def _missing(value: str | None, fallback: str) -> str:
    value = (value or "").strip()
    return value if value else fallback


def _year_or_date(publication_date: str) -> str:
    publication_date = (publication_date or "").strip()
    return publication_date or "\u65e5\u671f\u6682\u7f3a"


def _chinese_title(paper: dict[str, str]) -> str:
    # Do not machine-translate titles here; that would risk fabricating meaning.
    return paper.get("title_cn") or "\u4e2d\u6587\u6807\u9898\u6682\u7f3a"


def _abstract_line(paper: dict[str, str]) -> str:
    abstract = (paper.get("abstract") or "").strip()
    if not abstract:
        return "\u6458\u8981\uff1a\u6458\u8981\u6682\u7f3a\u3002"
    return f"\u6458\u8981\uff1a{abstract}"


def _doi_url_line(paper: dict[str, str]) -> str:
    doi = (paper.get("doi") or "").strip()
    url = (paper.get("url") or "").strip()
    parts = []
    if doi:
        parts.append(f"DOI: {doi}")
    if url:
        parts.append(f"URL: {url}")
    return " / ".join(parts) if parts else "DOI / URL\uff1a\u6682\u7f3a"


def _research_use(paper: dict[str, str]) -> str:
    keywords = (paper.get("matched_keywords") or "").lower()
    title = (paper.get("title") or "").lower()
    text = f"{keywords} {title}"
    if "career adaptability" in text or "sustainable employability" in text:
        return "\u53ef\u7528\u4e8e\u6784\u5efa\u804c\u4e1a\u9002\u5e94\u529b\u3001\u53ef\u6301\u7eed\u5c31\u4e1a\u80fd\u529b\u4e0e\u5b66\u751f\u53d1\u5c55\u7684\u5b9e\u8bc1\u6a21\u578b\u3002"
    if "higher education" in text or "vocational" in text:
        return "\u53ef\u4e3a\u9ad8\u7b49\u6559\u80b2\u6216\u804c\u4e1a\u6559\u80b2\u573a\u666f\u4e2d\u7684\u5b66\u751f\u652f\u6301\u3001\u8f6c\u8854\u548c\u5dee\u5f02\u5316\u53d1\u5c55\u63d0\u4f9b\u53c2\u8003\u3002"
    if "sem" in text or "lpa" in text or "mixed methods" in text:
        return "\u53ef\u501f\u9274\u5176\u65b9\u6cd5\u8def\u5f84\uff0c\u5b8c\u5584 SEM\u3001LPA \u6216\u6df7\u5408\u65b9\u6cd5\u7814\u7a76\u8bbe\u8ba1\u3002"
    if "inequality" in text or "sociology of education" in text:
        return "\u53ef\u4e3a\u6559\u80b2\u4e0d\u5e73\u7b49\u3001\u793e\u4f1a\u5206\u5c42\u4e0e\u5b66\u6821\u5230\u5de5\u4f5c\u8f6c\u8854\u7814\u7a76\u63d0\u4f9b\u7406\u8bba\u7ebf\u7d22\u3002"
    return "\u53ef\u4f5c\u4e3a\u76f8\u5173\u6587\u732e\u7ebf\u7d22\uff0c\u5efa\u8bae\u7ed3\u5408\u6458\u8981\u548c\u5168\u6587\u8fdb\u4e00\u6b65\u5224\u65ad\u3002"


def _paper_block(index: int, paper: dict[str, str]) -> list[str]:
    year_or_date = paper.get("publication_date") or paper.get("year") or ""
    journal_or_source = paper.get("source_journal") or paper.get("journal") or paper.get("source") or ""
    score = paper.get("relevance_score") or paper.get("score") or "0"
    return [
        f"### {index}. {_chinese_title(paper)}",
        "",
        f"- Original title: {_missing(paper.get('title'), '\u6807\u9898\u6682\u7f3a')}",
        f"- Authors: {_missing(paper.get('authors'), '\u4f5c\u8005\u6682\u7f3a')}",
        f"- Year / publication date: {_year_or_date(year_or_date)}",
        f"- Journal / source: {_missing(journal_or_source, '\u671f\u520a/\u6765\u6e90\u6682\u7f3a')}",
        f"- DOI / URL: {_doi_url_line(paper)}",
        f"- Relevance score: {_missing(score, '0')}",
        f"- Matched keywords: {_missing(paper.get('matched_keywords'), '\u6682\u65e0')}",
        f"- Relevance reason: {_missing(paper.get('relevance_reason_cn'), '\u76f8\u5173\u6027\uff1a\u5efa\u8bae\u4eba\u5de5\u590d\u6838\u3002')}",
        f"- {_abstract_line(paper)}",
        f"- How it can inform my research: {_research_use(paper)}",
        "",
    ]


def trend_keywords(papers: list[dict[str, str]], limit: int = 10) -> list[str]:
    counter: Counter[str] = Counter()
    for paper in papers:
        for keyword in (paper.get("matched_keywords") or "").split(";"):
            keyword = keyword.strip()
            if keyword:
                counter[keyword] += 1
    return [keyword for keyword, _ in counter.most_common(limit)]


def build_daily_digest(papers: list[dict[str, str]], top_n: int = 5, empty_reason: str = "") -> str:
    ranked = _sorted_papers(papers)
    top = ranked[:top_n]
    trends = trend_keywords(ranked)
    lines: list[str] = [
        "# \u6bcf\u65e5\u6587\u732e\u96f7\u8fbe",
        "",
        "## 1. \u4eca\u65e5\u6982\u89c8",
        "",
        f"- \u5171\u6709 {len(ranked)} \u7bc7\u5019\u9009\u8bba\u6587\u8fdb\u5165\u6392\u5e8f\u7ed3\u679c\u3002",
        f"- \u672c\u6b21\u6458\u8981\u4f18\u5148\u5448\u73b0\u76f8\u5173\u6027\u5f97\u5206\u6700\u9ad8\u7684 {len(top)} \u7bc7\u3002",
        "- \u672a\u63d0\u4f9b\u6458\u8981\u7684\u8bb0\u5f55\u5747\u6807\u6ce8\u4e3a\u201c\u6458\u8981\u6682\u7f3a\u201d\uff0c\u4e0d\u7f16\u9020\u6458\u8981\u5185\u5bb9\u3002",
        "",
        "## 2. \u4eca\u65e5\u6700\u503c\u5f97\u5173\u6ce8\u7684 5 \u7bc7\u8bba\u6587",
        "",
    ]

    if not top:
        reason = empty_reason or "OpenAlex/Crossref 未返回可用论文，或检索结果在去重后为空。"
        lines.extend([f"本次未检索到可用论文。原因：{reason}", ""])
    else:
        for index, paper in enumerate(top, start=1):
            lines.extend(_paper_block(index, paper))

    lines.extend(
        [
            "## 3. \u672c\u5468\u8d8b\u52bf\u5173\u952e\u8bcd",
            "",
            "\u3001".join(trends) if trends else "\u6682\u65e0\u8db3\u591f\u5173\u952e\u8bcd\u4fe1\u53f7\u3002",
            "",
            "## 4. \u5bf9\u6211\u7684\u6559\u80b2\u793e\u4f1a\u5b66\u5b9e\u8bc1\u7814\u7a76\u7684\u542f\u53d1",
            "",
            "- \u4f18\u5148\u5173\u6ce8\u804c\u4e1a\u9002\u5e94\u529b\u3001\u53ef\u6301\u7eed\u5c31\u4e1a\u80fd\u529b\u3001\u6570\u5b57\u5316\u5b66\u751f\u652f\u6301\u4e0e\u6559\u80b2\u4e0d\u5e73\u7b49\u7684\u4ea4\u53c9\u4e3b\u9898\u3002",
            "- \u5bf9\u542b SEM\u3001LPA\u3001longitudinal \u6216 mixed methods \u7684\u8bba\u6587\u8fdb\u884c\u65b9\u6cd5\u7ec6\u8bfb\uff0c\u63d0\u53d6\u53ef\u590d\u7528\u7684\u53d8\u91cf\u8bbe\u8ba1\u4e0e\u6a21\u578b\u8def\u5f84\u3002",
            "- \u5bf9\u9ad8\u804c\u5b66\u751f\u3001\u5b66\u6821\u5230\u5de5\u4f5c\u8f6c\u8854\u548c\u793e\u4f1a\u652f\u6301\u76f8\u5173\u6587\u732e\u5efa\u7acb\u4e3b\u9898\u7b14\u8bb0\u3002",
            "",
            "## 5. \u4e0b\u4e00\u6b65\u5efa\u8bae",
            "",
            "- \u5148\u624b\u52a8\u590d\u6838\u4eca\u65e5 Top 5 \u8bba\u6587\u7684 DOI\u3001\u6765\u6e90\u548c\u6458\u8981\u5b8c\u6574\u6027\u3002",
            "- \u5c06\u9ad8\u76f8\u5173\u8bba\u6587\u5bfc\u5165 Zotero\uff0c\u5e76\u6309\u201c\u7406\u8bba\u201d\u201c\u65b9\u6cd5\u201d\u201c\u573a\u666f\u201d\u5efa\u7acb\u5b50\u6536\u85cf\u5939\u3002",
            "- \u5bf9\u4f4e\u5206\u4f46\u671f\u520a\u8d28\u91cf\u9ad8\u7684\u8bb0\u5f55\u8fdb\u884c\u4e8c\u6b21\u7b5b\u9009\uff0c\u907f\u514d\u9519\u8fc7\u8de8\u9886\u57df\u6587\u732e\u3002",
            "",
        ]
    )
    return "\n".join(lines)


def write_daily_digest(
    input_path: Path | None = None,
    output_path: Path | None = None,
    empty_reason: str = "",
) -> Path:
    input_path = input_path or INPUT_PATH
    output_path = output_path or OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_daily_digest(read_ranked_papers(input_path), empty_reason=empty_reason),
        encoding="utf-8-sig",
    )
    return output_path
