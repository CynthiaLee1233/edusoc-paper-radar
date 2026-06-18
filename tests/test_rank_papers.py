from datetime import date

from src.rank_papers import rank_paper, rank_papers, rank_papers_csv


def test_rank_paper_scores_priority_topics_and_methods() -> None:
    paper = {
        "title": "Career adaptability and sustainable employability among vocational college students",
        "abstract": "A structural equation modeling SEM study in higher education.",
        "source_journal": "Journal of Vocational Behavior",
        "publication_date": date.today().isoformat(),
        "citation_count": "25",
    }
    ranked = rank_paper(paper)
    assert int(ranked["topic_score"]) >= 20
    assert int(ranked["method_score"]) >= 5
    assert int(ranked["journal_score"]) > 0
    assert int(ranked["recency_score"]) == 5
    assert "career adaptability" in ranked["matched_keywords"]
    assert "structural equation modeling" in ranked["matched_keywords"]


def test_rank_paper_penalizes_irrelevant_fields() -> None:
    paper = {
        "title": "Clinical medicine and molecular biology materials engineering",
        "abstract": "Unrelated computer science and computer vision.",
        "source_journal": "",
        "publication_date": "",
        "citation_count": "0",
    }
    ranked = rank_paper(paper)
    assert int(ranked["relevance_score"]) == 0
    assert "\u53ef\u80fd\u4e0d\u76f8\u5173\u9886\u57df" in ranked["relevance_reason_cn"]


def test_k12_penalty_reduced_when_related_to_inequality() -> None:
    paper = {
        "title": "K-12 mathematics teaching and educational inequality",
        "abstract": "A sociology study of transition and career development.",
        "source_journal": "",
        "publication_date": "",
        "citation_count": "0",
    }
    ranked = rank_paper(paper)
    assert int(ranked["relevance_score"]) > 0


def test_rank_papers_orders_by_relevance() -> None:
    papers = [
        {"title": "Clinical medicine", "abstract": "", "source_journal": ""},
        {"title": "Sociology of education and higher education inequality", "abstract": "", "source_journal": ""},
    ]
    ranked = rank_papers(papers)
    assert ranked[0]["title"].startswith("Sociology")


def test_rank_papers_csv(tmp_path) -> None:
    input_path = tmp_path / "papers_deduplicated.csv"
    output_path = tmp_path / "papers_ranked.csv"
    input_path.write_text(
        "title,authors,publication_date,source_journal,doi,url,abstract,citation_count,source_api\n"
        "Higher education career adaptability,,,,,,SEM study,10,OpenAlex\n",
        encoding="utf-8",
    )
    ranked = rank_papers_csv(input_path, output_path)
    assert ranked
    content = output_path.read_text(encoding="utf-8")
    assert "relevance_score" in content
    assert "matched_keywords" in content
