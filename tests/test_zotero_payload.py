import requests

from src.zotero_client import (
    ZoteroClient,
    build_collection_url,
    build_collections_url,
    build_zotero_item_payload,
    filter_import_candidates,
    format_connection_test,
    import_ranked_papers_to_zotero,
)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FlakySession:
    def __init__(self):
        self.headers = {}
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        assert timeout == (10, 30)
        if self.calls == 1:
            raise requests.ConnectionError("reset")
        return FakeResponse(200, {"ok": True})


def test_build_urls() -> None:
    assert build_collections_url("123", "user") == "https://api.zotero.org/users/123/collections?format=json&limit=100"
    assert build_collection_url("123", "user", "ABC") == "https://api.zotero.org/users/123/collections/ABC"


def test_connection_output_omits_secret() -> None:
    output = format_connection_test("user", "Methods", "ABC")
    assert "Zotero connection OK" in output
    assert "Collection name: Methods" in output
    assert "ZOTERO_API_KEY" not in output


def test_zotero_client_retries_connection_error(monkeypatch) -> None:
    client = ZoteroClient("secret")
    fake_session = FlakySession()
    client.session = fake_session
    monkeypatch.setattr("src.zotero_client.time.sleep", lambda delay: None)
    assert client.get_json("https://api.zotero.org/example") == {"ok": True}
    assert fake_session.calls == 2


def test_build_zotero_item_payload_contains_collection_tags_and_extra() -> None:
    payload = build_zotero_item_payload(
        {
            "title": "Career adaptability in higher education",
            "authors": "A. Scholar; B. Writer",
            "publication_date": "2026-06-18",
            "source_journal": "Higher Education",
            "doi": "https://doi.org/10.1/DEMO",
            "url": "https://example.org",
            "abstract": "Abstract text",
            "matched_keywords": "career adaptability; higher education",
            "source_api": "OpenAlex",
            "relevance_score": "88",
            "relevance_reason_cn": "\u76f8\u5173\u6027\uff1a\u547d\u4e2d\u4e3b\u9898\u3002",
        },
        "COLL123",
    )
    assert payload["itemType"] == "journalArticle"
    assert payload["collections"] == ["COLL123"]
    assert payload["DOI"] == "10.1/demo"
    assert {"tag": "paper-radar"} in payload["tags"]
    assert {"tag": "education-sociology"} in payload["tags"]
    assert {"tag": "career adaptability"} in payload["tags"]
    assert {"tag": "OpenAlex"} in payload["tags"]
    assert "88" in payload["extra"]
    assert "PDF" not in str(payload)


def test_filter_import_candidates_uses_default_threshold() -> None:
    candidates = filter_import_candidates(
        [
            {"title": "Low", "relevance_score": "74"},
            {"title": "High", "relevance_score": "75"},
        ]
    )
    assert [paper["title"] for paper in candidates] == ["High"]


def test_import_ranked_papers_dry_run_logs_without_secret(monkeypatch, tmp_path) -> None:
    ranked_path = tmp_path / "papers_ranked.csv"
    log_path = tmp_path / "zotero_import_log.csv"
    ranked_path.write_text(
        "title,authors,publication_date,source_journal,doi,url,abstract,citation_count,source_api,"
        "relevance_score,topic_score,method_score,journal_score,recency_score,influence_score,"
        "matched_keywords,relevance_reason_cn\n"
        "Career adaptability,A. Scholar,2026-06-18,Higher Education,10.1/demo,https://example.org,,"
        "10,OpenAlex,90,8,5,5,5,2,career adaptability,\u76f8\u5173\u6027\uff1a\u547d\u4e2d\u4e3b\u9898\u3002\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZOTERO_API_KEY", "secret-key")
    monkeypatch.setenv("ZOTERO_USER_ID", "123")
    monkeypatch.setenv("ZOTERO_LIBRARY_TYPE", "user")
    monkeypatch.setenv("ZOTERO_COLLECTION_KEY", "COLL123")
    monkeypatch.setattr("src.zotero_client.find_duplicate", lambda *args, **kwargs: None)

    rows = import_ranked_papers_to_zotero(ranked_path, dry_run=True, log_path=log_path)

    assert rows[0]["status"] == "dry-run"
    log_text = log_path.read_text(encoding="utf-8")
    assert "secret-key" not in log_text
    assert "would-create" in log_text
