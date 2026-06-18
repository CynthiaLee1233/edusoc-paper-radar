"""Command line entry point for the paper radar."""

from __future__ import annotations

import argparse
import sys

try:
    from .utils import load_environment
except ImportError:
    from utils import load_environment

try:
    from .deduplicate import deduplicate_papers, save_deduplicated_papers
    from .fetch_crossref import fetch_crossref
    from .fetch_openalex import fetch_openalex
    from .notify_feishu import notify_feishu
    from .rank_papers import rank_papers, RANKED_FIELDS
    from .summarize import write_daily_digest
    from .utils import PROJECT_ROOT, load_topic_keywords, write_csv
except ImportError:
    from deduplicate import deduplicate_papers, save_deduplicated_papers
    from fetch_crossref import fetch_crossref
    from fetch_openalex import fetch_openalex
    from notify_feishu import notify_feishu
    from rank_papers import rank_papers, RANKED_FIELDS
    from summarize import write_daily_digest
    from utils import PROJECT_ROOT, load_topic_keywords, write_csv

try:
    from .zotero_client import (
        ZoteroAuthenticationError,
        ZoteroCollectionNotFoundError,
        fetch_zotero_collection_for_test,
        fetch_zotero_collections,
        format_collections_table,
        format_connection_test,
        import_ranked_papers_to_zotero,
    )
except ImportError:
    from zotero_client import (
        ZoteroAuthenticationError,
        ZoteroCollectionNotFoundError,
        fetch_zotero_collection_for_test,
        fetch_zotero_collections,
        format_collections_table,
        format_connection_test,
        import_ranked_papers_to_zotero,
    )


NO_COLLECTIONS_MESSAGE = (
    "\u6ca1\u6709\u627e\u5230 Zotero \u6536\u85cf\u5939\u3002"
    "\u8bf7\u786e\u8ba4\u8be5\u6587\u5e93\u4e2d\u5df2\u7ecf\u521b\u5efa collection\uff0c"
    "\u6216\u68c0\u67e5 ZOTERO_LIBRARY_TYPE \u548c\u7528\u6237/\u7fa4\u7ec4 ID\u3002"
)
RAW_FIELDS = [
    "title",
    "authors",
    "publication_date",
    "source_journal",
    "doi",
    "url",
    "abstract",
    "citation_count",
    "source_api",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Academic paper radar utilities.")
    parser.add_argument(
        "--zotero-list-collections",
        action="store_true",
        help="List Zotero collections using the Zotero Web API v3.",
    )
    parser.add_argument(
        "--zotero-test",
        action="store_true",
        help="Test Zotero credentials and one configured collection.",
    )
    parser.add_argument(
        "--fetch-papers",
        action="store_true",
        help="Fetch recent papers from OpenAlex and Crossref.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["openalex", "crossref"],
        default=None,
        help="Paper metadata sources to query.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Search papers from the last N days.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum results per source and keyword.",
    )
    parser.add_argument(
        "--rank",
        action="store_true",
        help="Rank deduplicated papers.",
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Generate the Chinese daily digest.",
    )
    parser.add_argument(
        "--zotero",
        action="store_true",
        help="Import high-scoring ranked papers into Zotero.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview write operations without creating Zotero items.",
    )
    parser.add_argument(
        "--notify",
        choices=["feishu"],
        help="Send the daily digest through a notification channel.",
    )
    return parser.parse_args()


def fetch_and_save_raw_papers(
    sources: list[str] | None = None,
    days: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    keywords = load_topic_keywords()
    if not keywords:
        raise RuntimeError("No keywords found in config/topics.yaml")

    selected_sources = sources or ["openalex", "crossref"]
    papers: list[dict[str, str]] = []
    if "openalex" in selected_sources:
        papers.extend(fetch_openalex(keywords, days_back=days, max_results=max_results))
    if "crossref" in selected_sources:
        papers.extend(fetch_crossref(keywords, days_back=days, max_results=max_results))
    output_path = PROJECT_ROOT / "outputs" / "papers_raw.csv"
    write_csv(output_path, papers, RAW_FIELDS)
    print(f"Wrote {len(papers)} raw papers to {output_path}")
    return papers


def deduplicate_rank_and_digest(
    papers: list[dict[str, str]],
    do_rank: bool = True,
    do_digest: bool = True,
) -> list[dict[str, str]]:
    deduplicated = deduplicate_papers(papers)
    deduplicated_path = save_deduplicated_papers(deduplicated)
    print(f"Wrote {len(deduplicated)} deduplicated papers to {deduplicated_path}")
    if not do_rank:
        return deduplicated

    ranked = rank_papers(deduplicated)
    ranked_path = PROJECT_ROOT / "outputs" / "papers_ranked.csv"
    write_csv(ranked_path, ranked, RANKED_FIELDS)
    print(f"Wrote {len(ranked)} ranked papers to {ranked_path}")
    if do_digest:
        digest_path = write_daily_digest(ranked_path, PROJECT_ROOT / "outputs" / "daily_digest.md")
        print(f"Wrote daily digest to {digest_path}")
    return ranked


def run_pipeline(args: argparse.Namespace) -> None:
    papers = fetch_and_save_raw_papers(
        sources=args.sources,
        days=args.days,
        max_results=args.max_results,
    )
    should_rank = args.rank or args.digest or args.zotero or args.notify
    should_digest = args.digest or args.notify
    deduplicate_rank_and_digest(papers, do_rank=should_rank, do_digest=should_digest)

    if args.zotero:
        import_ranked_papers_to_zotero(dry_run=args.dry_run)
    if args.notify == "feishu":
        notify_feishu(dry_run=args.dry_run)


def main() -> None:
    load_environment()
    args = parse_args()
    if args.zotero_list_collections:
        try:
            collections = fetch_zotero_collections()
        except ZoteroAuthenticationError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from error
        except RuntimeError as error:
            print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
            raise SystemExit(1) from error
        if not collections:
            print(NO_COLLECTIONS_MESSAGE)
            return
        print(format_collections_table(collections))
        return

    if args.zotero_test:
        try:
            library_type, collection = fetch_zotero_collection_for_test()
        except (ZoteroAuthenticationError, ZoteroCollectionNotFoundError) as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from error
        except RuntimeError as error:
            print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
            raise SystemExit(1) from error
        print(format_connection_test(library_type, collection))
        return

    if args.fetch_papers or args.sources or args.rank or args.digest:
        try:
            run_pipeline(args)
        except (ZoteroAuthenticationError, ZoteroCollectionNotFoundError) as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from error
        except RuntimeError as error:
            print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
            raise SystemExit(1) from error
        return

    if args.zotero:
        try:
            import_ranked_papers_to_zotero(dry_run=args.dry_run)
        except (ZoteroAuthenticationError, ZoteroCollectionNotFoundError) as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from error
        except RuntimeError as error:
            print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
            raise SystemExit(1) from error
        return

    if args.notify == "feishu":
        try:
            notify_feishu(dry_run=args.dry_run)
        except RuntimeError as error:
            print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
            raise SystemExit(1) from error
        return

    papers = fetch_and_save_raw_papers()
    deduplicate_rank_and_digest(papers)


if __name__ == "__main__":
    main()
