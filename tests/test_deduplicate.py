from src.deduplicate import (
    choose_richer_record,
    deduplicate_papers,
    normalize_doi,
    normalize_title,
    record_richness_score,
    save_deduplicated_papers,
)


def test_normalize_doi() -> None:
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalize_doi("doi:10.1234/ABC") == "10.1234/abc"


def test_normalize_title() -> None:
    assert normalize_title("School Choice & Inequality!") == "school choice and inequality"


def test_record_richness_score() -> None:
    paper = {
        "doi": "10.1/demo",
        "abstract": "Abstract",
        "source_journal": "Journal",
        "url": "https://example.org",
        "citation_count": "12",
    }
    assert record_richness_score(paper) == 5


def test_choose_richer_record_keeps_more_complete_record() -> None:
    sparse = {"title": "A Study", "doi": "10.1/demo"}
    rich = {
        "title": "A Study",
        "doi": "https://doi.org/10.1/DEMO",
        "abstract": "Abstract",
        "source_journal": "Journal",
        "url": "https://example.org",
        "citation_count": "3",
    }
    chosen = choose_richer_record(sparse, rich)
    assert chosen["abstract"] == "Abstract"
    assert chosen["source_journal"] == "Journal"
    assert chosen["doi"] == "10.1/demo"


def test_deduplicate_by_doi_first() -> None:
    papers = [
        {"title": "A", "doi": "10.1/demo", "source_journal": ""},
        {"title": "A again", "doi": "https://doi.org/10.1/DEMO", "source_journal": "Journal"},
    ]
    deduped = deduplicate_papers(papers)
    assert len(deduped) == 1
    assert deduped[0]["source_journal"] == "Journal"


def test_deduplicate_by_title_when_doi_missing() -> None:
    papers = [
        {"title": "Career Adaptability among Students", "doi": "", "abstract": ""},
        {"title": "Career adaptability among students", "doi": "", "abstract": "Abstract"},
    ]
    deduped = deduplicate_papers(papers)
    assert len(deduped) == 1
    assert deduped[0]["abstract"] == "Abstract"


def test_different_dois_are_not_deduplicated_by_title() -> None:
    papers = [
        {"title": "Same Title", "doi": "10.1/one"},
        {"title": "Same Title", "doi": "10.1/two"},
    ]
    assert len(deduplicate_papers(papers)) == 2


def test_save_deduplicated_papers(tmp_path) -> None:
    output_path = tmp_path / "papers_deduplicated.csv"
    saved_path = save_deduplicated_papers(
        [{"title": "A", "doi": "10.1/demo", "source_journal": "Journal"}],
        output_path,
    )
    assert saved_path == output_path
    assert "papers_deduplicated" in output_path.name
    assert "10.1/demo" in output_path.read_text(encoding="utf-8")
