# Edusoc Paper Radar

Cloud-first academic paper radar for empirical sociology of education research. It searches OpenAlex and Crossref, caches API responses, normalizes metadata, deduplicates papers, ranks relevance from 0 to 100, imports high-relevance papers into Zotero, generates a Chinese digest, and pushes the digest to Feishu.

## Safety

- Does not scrape Google Scholar, CNKI, Web of Science, Scopus, or paywalled journal websites.
- Uses official APIs only.
- Does not print secrets.
- `.env` is ignored by Git.
- Does not upload PDFs.
- Does not fabricate missing metadata. Missing abstracts are shown as `摘要暂缺`.

## Commands

```powershell
python src/main.py --zotero-test
python src/main.py --zotero-list-collections
python src/main.py --sources openalex crossref --days 7 --max-results 100 --rank --digest --zotero --notify feishu --dry-run
python src/main.py --sources openalex crossref --days 7 --max-results 100 --rank --digest --zotero --notify feishu
```

## Environment

Copy `.env.example` to `.env` and fill in values locally. In GitHub Actions, use repository secrets with the same names.

```txt
OPENALEX_API_KEY=
USER_EMAIL=
ZOTERO_API_KEY=
ZOTERO_USER_ID=
ZOTERO_LIBRARY_TYPE=user
ZOTERO_COLLECTION_KEY=
FEISHU_WEBHOOK_URL=
FEISHU_SECRET=
```

## Outputs

- `outputs/papers_raw.csv`
- `outputs/papers_deduplicated.csv`
- `outputs/papers_ranked.csv`
- `outputs/daily_digest.md`
- `outputs/zotero_import_log.csv`
- `outputs/feishu_push_log.csv`
