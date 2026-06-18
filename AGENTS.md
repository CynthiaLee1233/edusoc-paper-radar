# AGENTS.md

## Project Goal

Build a cloud-first academic paper radar system for empirical sociology of education research, integrated with Zotero and Feishu.

## Research Focus

- sociology of education
- higher education
- vocational education
- vocational college students
- student development
- career adaptability
- sustainable employability
- career self-efficacy
- professional identity
- perceived social support
- job preparation behavior
- digital student support
- one-stop student community
- school-to-work transition
- SEM, LPA, mixed methods, mediation model, moderated mediation

## Rules

- Do not fabricate papers, DOIs, citations, journals, abstracts, or URLs.
- Do not scrape Google Scholar, CNKI, Web of Science, Scopus, or paywalled journal pages unless legal API access is provided.
- Use official APIs, RSS feeds, or exported bibliographic files.
- Cache API responses.
- Respect rate limits.
- Store raw API responses in `data/cache/`.
- Store cleaned metadata in `data/processed/`.
- Deduplicate by DOI first, then title similarity.
- Output both CSV and Markdown.
- Use concise Chinese summaries for final digests.
