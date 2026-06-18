from src.notify_feishu import build_feishu_sign, build_message_payload, split_digest_sections


def test_build_message_payload_with_secret() -> None:
    payload = build_message_payload("hello", "secret")
    assert payload["msg_type"] == "text"
    assert payload["content"]["text"] == "hello"
    assert "timestamp" in payload
    assert "sign" in payload
    assert "secret" not in str(payload)


def test_build_feishu_sign_is_stable() -> None:
    assert build_feishu_sign("123", "secret") == build_feishu_sign("123", "secret")


def test_split_digest_sections() -> None:
    digest = "\n".join(
        [
            "# daily",
            "## 1. \u4eca\u65e5\u6982\u89c8",
            "overview",
            "## 2. \u4eca\u65e5\u6700\u503c\u5f97\u5173\u6ce8\u7684 5 \u7bc7\u8bba\u6587",
            "papers",
            "## 3. \u672c\u5468\u8d8b\u52bf\u5173\u952e\u8bcd",
            "trends",
            "## 4. \u5bf9\u6211\u7684\u6559\u80b2\u793e\u4f1a\u5b66\u5b9e\u8bc1\u7814\u7a76\u7684\u542f\u53d1",
            "ideas",
            "## 5. \u4e0b\u4e00\u6b65\u5efa\u8bae",
            "next",
        ]
    )
    sections = dict(split_digest_sections(digest, "Zotero import status: created: 1"))
    assert "overview" in sections["overview"]
    assert "papers" in sections["top_5_papers"]
    assert "created: 1" in sections["zotero_import_status"]
    assert "trends" in sections["trend_keywords_and_suggestions"]
