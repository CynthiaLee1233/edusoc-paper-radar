from src.summarize import build_daily_digest, trend_keywords, write_daily_digest


def test_build_daily_digest_includes_required_sections() -> None:
    digest = build_daily_digest(
        [
            {
                "title": "Career adaptability among vocational college students",
                "authors": "A. Scholar",
                "publication_date": "2026-06-18",
                "source_journal": "Journal of Vocational Behavior",
                "doi": "10.1/demo",
                "url": "https://example.org",
                "abstract": "",
                "relevance_score": "42",
                "matched_keywords": "career adaptability; vocational college students; SEM",
                "relevance_reason_cn": "\u76f8\u5173\u6027\uff1a\u547d\u4e2d\u6838\u5fc3\u4e3b\u9898\u3002",
            }
        ]
    )
    assert "\u4eca\u65e5\u6982\u89c8" in digest
    assert "\u4eca\u65e5\u6700\u503c\u5f97\u5173\u6ce8\u7684 5 \u7bc7\u8bba\u6587" in digest
    assert "\u6458\u8981\uff1a\u6458\u8981\u6682\u7f3a" in digest
    assert "Career adaptability among vocational college students" in digest
    assert "10.1/demo" in digest
    assert "\u4e0b\u4e00\u6b65\u5efa\u8bae" in digest


def test_trend_keywords_counts_matched_keywords() -> None:
    trends = trend_keywords(
        [
            {"matched_keywords": "SEM; higher education"},
            {"matched_keywords": "SEM; career adaptability"},
        ]
    )
    assert trends[0] == "SEM"


def test_write_daily_digest(tmp_path) -> None:
    input_path = tmp_path / "papers_ranked.csv"
    output_path = tmp_path / "daily_digest.md"
    input_path.write_text(
        "title,authors,publication_date,source_journal,doi,url,abstract,citation_count,source_api,"
        "relevance_score,topic_score,method_score,journal_score,recency_score,influence_score,"
        "matched_keywords,relevance_reason_cn\n"
        "Higher education transitions,A. Scholar,2026-06-18,Higher Education,10.1/demo,,,"
        ",OpenAlex,20,7,5,5,5,1,higher education,\u76f8\u5173\u6027\uff1a\u547d\u4e2d\u4e3b\u9898\u3002\n",
        encoding="utf-8",
    )
    saved = write_daily_digest(input_path, output_path)
    assert saved == output_path
    assert output_path.exists()
