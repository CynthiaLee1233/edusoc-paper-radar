"""Command line entry point for the paper radar."""

from __future__ import annotations

import argparse
import csv
import sys

try:
    from .deduplicate import deduplicate_papers, save_deduplicated_papers
    from .fetch_crossref import fetch_crossref
    from .fetch_openalex import fetch_openalex
    from .notify_feishu import notify_feishu
    from .rank_papers import RANKED_FIELDS, rank_papers
    from .summarize import write_daily_digest
    from .utils import ensure_output_dir, load_environment, load_settings, project_path, write_csv
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
    from deduplicate import deduplicate_papers, save_deduplicated_papers
    from fetch_crossref import fetch_crossref
    from fetch_openalex import fetch_openalex
    from notify_feishu import notify_feishu
    from rank_papers import RANKED_FIELDS, rank_papers
    from summarize import write_daily_digest
    from utils import ensure_output_dir, load_environment, load_settings, project_path, write_csv
    from zotero_client import (
        ZoteroAuthenticationError,
        ZoteroCollectionNotFoundError,
        fetch_zotero_collection_for_test,
        fetch_zotero_collections,
        format_collections_table,
        format_connection_test,
        import_ranked_papers_to_zotero,
    )


RAW_FIELDS = [
    "title",
    "year",
    "doi",
    "source",
    "journal",
    "url",
    "abstract",
    "score",
]
NO_COLLECTIONS_MESSAGE = (
    "\u6ca1\u6709\u627e\u5230 Zotero \u6536\u85cf\u5939\u3002"
    "\u8bf7\u786e\u8ba4\u8be5\u6587\u5e93\u4e2d\u5df2\u7ecf\u521b\u5efa collection\uff0c"
    "\u6216\u68c0\u67e5 ZOTERO_LIBRARY_TYPE \u548c\u7528\u6237/\u7fa4\u7ec4 ID\u3002"
)


def log_step(message: str) -> None:
    print(f"[paper-radar] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="\u4e91\u7aef\u4f18\u5148\u7684\u6559\u80b2\u793e\u4f1a\u5b66\u6587\u732e\u96f7\u8fbe\u3002",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "\nExamples:\n"
            "  python src/main.py --help\n"
            "  python src/main.py --zotero-test\n"
            "  python src/main.py --zotero-list-collections\n"
            "  python src/main.py --dry-run\n"
            "  python -m src.main --diagnose\n"
            "  python src/main.py --run-once\n"
            "  python src/main.py --run-once --no-zotero\n"
            "  python src/main.py --run-once --no-feishu\n"
            "  python src/main.py --sources openalex crossref --days 7 --max-results 100 --rank --digest --zotero --notify feishu --dry-run\n"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="\u53ea\u641c\u7d22\u3001\u6392\u5e8f\u5e76\u751f\u6210\u6458\u8981\uff0c\u4e0d\u5199\u5165 Zotero\uff0c\u4e0d\u53d1\u9001\u98de\u4e66\u3002")
    parser.add_argument("--run-once", action="store_true", help="\u8fd0\u884c\u5b8c\u6574\u6587\u732e\u96f7\u8fbe\u6d41\u7a0b\u3002")
    parser.add_argument("--zotero-test", action="store_true", help="\u6d4b\u8bd5 Zotero API \u548c\u76ee\u6807 collection\u3002")
    parser.add_argument("--zotero-list-collections", action="store_true", help="\u5217\u51fa Zotero collection \u540d\u79f0\u548c key\u3002")
    parser.add_argument("--no-zotero", action="store_true", help="\u8fd0\u884c\u4e3b\u6d41\u7a0b\u65f6\u8df3\u8fc7 Zotero \u5bfc\u5165\u3002")
    parser.add_argument("--no-feishu", action="store_true", help="\u8fd0\u884c\u4e3b\u6d41\u7a0b\u65f6\u8df3\u8fc7\u98de\u4e66\u63a8\u9001\u3002")

    # Advanced options kept for GitHub Actions and manual tuning.
    parser.add_argument("--sources", nargs="+", choices=["openalex", "crossref"], default=None, help="\u9009\u62e9\u6570\u636e\u6e90\u3002")
    parser.add_argument("--days", type=int, default=None, help="\u641c\u7d22\u6700\u8fd1 N \u5929\u7684\u8bba\u6587\u3002")
    parser.add_argument("--max-results", type=int, default=None, help="\u6bcf\u4e2a\u6570\u636e\u6e90\u548c\u5173\u952e\u8bcd\u7684\u6700\u5927\u8fd4\u56de\u6570\u3002")
    parser.add_argument("--rank", action="store_true", help="\u5bf9\u53bb\u91cd\u540e\u7684\u8bba\u6587\u6392\u5e8f\u3002")
    parser.add_argument("--digest", action="store_true", help="\u751f\u6210\u4e2d\u6587\u6bcf\u65e5\u6458\u8981\u3002")
    parser.add_argument("--zotero", action="store_true", help="\u5c06\u9ad8\u76f8\u5173\u8bba\u6587\u5bfc\u5165 Zotero\u3002")
    parser.add_argument("--notify", choices=["feishu"], help="\u63a8\u9001\u6458\u8981\u5230\u901a\u77e5\u6e20\u9053\u3002")
    parser.add_argument("--fetch-papers", action="store_true", help="\u4ec5\u6293\u53d6\u8bba\u6587\u5e76\u751f\u6210 raw/deduplicated/ranked/digest \u6587\u4ef6\u3002")
    parser.add_argument("--diagnose", action="store_true", help="只执行 OpenAlex 检索、输出文件生成与路径检查。")
    return parser.parse_args()


def _effective_search_config(args: argparse.Namespace) -> tuple[str, int, int]:
    settings = load_settings()
    query = str(settings.get("query", "")).strip()
    if not query:
        raise RuntimeError("config/settings.yaml 中没有找到 search.query")
    days_back = args.days if args.days is not None else int(settings["days_back"])
    max_results = args.max_results if args.max_results is not None else int(settings["max_results_per_source"])
    return query, days_back, max_results


def fetch_raw_papers(
    sources: list[str] | None,
    days: int | None,
    max_results: int | None,
    query: str,
    output_path,
) -> list[dict[str, str]]:
    selected_sources = sources or ["openalex", "crossref"]
    papers: list[dict[str, str]] = []
    openalex_count = 0
    crossref_count = 0
    failure_reasons: list[str] = []

    log_step(f"本次检索 query：{query}")
    log_step(f"本次检索 days_back：{days}")
    log_step(f"本次检索 max_results_per_source：{max_results}")

    if "openalex" in selected_sources:
        log_step("\u6b63\u5728\u8fde\u63a5 OpenAlex\uff08\u4ec5\u4f7f\u7528\u5b98\u65b9 API\uff09\u3002")
        try:
            openalex_papers = fetch_openalex(query, days_back=days, max_results=max_results)
            openalex_count = len(openalex_papers)
            papers.extend(openalex_papers)
        except Exception as error:
            reason = f"OpenAlex 请求失败：{error}"
            failure_reasons.append(reason)
            log_step(f"{reason}。已跳过该来源，继续处理其他来源。")
    if "crossref" in selected_sources:
        log_step("\u6b63\u5728\u8fde\u63a5 Crossref\uff08\u4ec5\u4f7f\u7528\u5b98\u65b9 API\uff09\u3002")
        try:
            crossref_papers = fetch_crossref(query, days_back=days, max_results=max_results)
            crossref_count = len(crossref_papers)
            papers.extend(crossref_papers)
        except Exception as error:
            reason = f"Crossref 请求失败：{error}"
            failure_reasons.append(reason)
            log_step(f"{reason}。已跳过该来源，继续处理其他来源。")

    log_step(f"OpenAlex 返回结果数：{openalex_count}")
    log_step(f"Crossref 返回结果数：{crossref_count}")
    log_step(f"raw papers 总数：{len(papers)}")
    if not papers:
        if failure_reasons:
            log_step(
                "没有找到论文。确切原因：部分或全部 API 请求失败，成功请求的来源也没有返回可用论文；"
                "失败详情：" + "；".join(failure_reasons)
            )
        else:
            log_step(
                f"没有找到论文。确切原因：OpenAlex 和 Crossref 都成功返回了 0 条可用论文；"
                f"当前 query='{query}'，days_back={days}，max_results_per_source={max_results}。"
                "建议放宽 query，例如改为 career adaptability，或增大 days_back。"
            )

    log_step(f"raw CSV 输出路径：{output_path}")
    write_csv(output_path, papers, RAW_FIELDS)
    log_step(f"已写入 raw CSV 行数：{len(papers)}")
    return papers


def process_papers(
    papers: list[dict[str, str]],
    deduplicated_path,
    ranked_path,
    digest_path,
    make_digest: bool = True,
) -> list[dict[str, str]]:
    log_step("\u6b63\u5728\u6309 DOI \u548c\u6807\u9898\u53bb\u91cd\u3002")
    deduplicated = deduplicate_papers(papers)
    save_deduplicated_papers(deduplicated, deduplicated_path)
    log_step(f"去重后论文数：{len(deduplicated)}")
    log_step(f"deduplicated CSV 输出路径：{deduplicated_path}")
    log_step(f"\u5df2\u5199\u5165\u53bb\u91cd\u7ed3\u679c\uff1a{len(deduplicated)} \u6761 -> {deduplicated_path}")

    log_step("\u6b63\u5728\u8ba1\u7b97 0-100 \u76f8\u5173\u6027\u5f97\u5206\u3002")
    try:
        ranked = rank_papers(deduplicated)
    except Exception as error:
        log_step(f"ranking 失败，具体错误：{error}")
        write_csv(ranked_path, [], RANKED_FIELDS)
        log_step(f"ranked CSV 输出路径：{ranked_path}")
        log_step("ranked 写入行数：0")
        ranked = []
    else:
        write_csv(ranked_path, ranked, RANKED_FIELDS)
        log_step(f"ranking 后论文数：{len(ranked)}")
        log_step(f"ranked CSV 输出路径：{ranked_path}")
        log_step(f"ranked 写入行数：{len(ranked)}")

    if make_digest:
        log_step("\u6b63\u5728\u751f\u6210\u4e2d\u6587 daily digest\u3002")
        empty_reason = "本次检索、去重或排序后没有可用论文。" if not ranked else ""
        digest_path = write_daily_digest(ranked_path, digest_path, empty_reason=empty_reason)
        log_step(f"digest 输出路径：{digest_path}")
    return ranked


def run_workflow(args: argparse.Namespace, write_zotero: bool, send_feishu: bool) -> None:
    settings = load_settings()
    query, days_back, max_results = _effective_search_config(args)
    raw_path = project_path(settings["papers_raw"])
    deduplicated_path = project_path(settings["papers_deduplicated"])
    ranked_path = project_path(settings["papers_ranked"])
    digest_path = project_path(settings["daily_digest"])
    papers = fetch_raw_papers(args.sources, days_back, max_results, query, raw_path)
    process_papers(papers, deduplicated_path, ranked_path, digest_path, make_digest=True)

    if write_zotero:
        log_step("\u6b63\u5728\u5bfc\u5165 Zotero\uff08\u4e0d\u4e0a\u4f20 PDF\uff09\u3002")
        import_ranked_papers_to_zotero(dry_run=args.dry_run)
    else:
        log_step("\u5df2\u8df3\u8fc7 Zotero \u5199\u5165\u3002")

    if send_feishu:
        log_step("\u6b63\u5728\u63a8\u9001\u98de\u4e66\u6d88\u606f\u3002")
        notify_feishu(dry_run=args.dry_run)
    else:
        log_step("\u5df2\u8df3\u8fc7\u98de\u4e66\u63a8\u9001\u3002")


def _csv_data_row_count(path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return max(0, sum(1 for _ in csv.DictReader(file)))


def _print_output_check(path, is_csv: bool) -> None:
    exists = path.exists()
    if is_csv:
        log_step(f"诊断检查：{path} 是否存在：{'是' if exists else '否'}，CSV 数据行数：{_csv_data_row_count(path)}")
    else:
        log_step(f"诊断检查：{path} 是否存在：{'是' if exists else '否'}")


def run_diagnose(args: argparse.Namespace) -> None:
    settings = load_settings()
    query, days_back, max_results = _effective_search_config(args)
    raw_path = project_path(settings["papers_raw"])
    deduplicated_path = project_path(settings["papers_deduplicated"])
    ranked_path = project_path(settings["papers_ranked"])
    digest_path = project_path(settings["daily_digest"])

    log_step("开始诊断模式：只执行 OpenAlex 检索、输出文件生成与路径检查。")
    papers = fetch_raw_papers(["openalex"], days_back, max_results, query, raw_path)
    process_papers(papers, deduplicated_path, ranked_path, digest_path, make_digest=True)

    _print_output_check(raw_path, is_csv=True)
    _print_output_check(deduplicated_path, is_csv=True)
    _print_output_check(ranked_path, is_csv=True)
    _print_output_check(digest_path, is_csv=False)


def handle_zotero_list() -> None:
    log_step("\u6b63\u5728\u83b7\u53d6 Zotero collections\u3002")
    collections = fetch_zotero_collections()
    if not collections:
        print(NO_COLLECTIONS_MESSAGE)
        return
    print(format_collections_table(collections))


def handle_zotero_test() -> None:
    log_step("\u6b63\u5728\u6d4b\u8bd5 Zotero API \u548c\u76ee\u6807 collection\u3002")
    library_type, collection = fetch_zotero_collection_for_test()
    print(format_connection_test(library_type, collection))


def main() -> None:
    print("[paper-radar] 程序已启动，正在准备命令行参数和环境变量。", flush=True)
    print("[paper-radar] 准备加载 .env 文件。", flush=True)
    load_environment()
    print("[paper-radar] .env 加载完成。", flush=True)
    output_dir = ensure_output_dir()
    log_step(f"outputs 文件夹已准备：{output_dir}")
    args = parse_args()
    try:
        if args.diagnose:
            run_diagnose(args)
            return
        if args.zotero_list_collections:
            handle_zotero_list()
            return
        if args.zotero_test:
            handle_zotero_test()
            return
        if args.dry_run:
            log_step("\u8fd9\u662f dry-run\uff1a\u4f1a\u641c\u7d22\u3001\u6392\u5e8f\u5e76\u751f\u6210\u6458\u8981\uff0c\u4e0d\u5199 Zotero\uff0c\u4e0d\u53d1\u98de\u4e66\u3002")
            run_workflow(args, write_zotero=False, send_feishu=False)
            return
        if args.run_once:
            run_workflow(args, write_zotero=not args.no_zotero, send_feishu=not args.no_feishu)
            return
        if args.fetch_papers or args.sources or args.rank or args.digest:
            write_zotero = args.zotero and not args.no_zotero
            send_feishu = args.notify == "feishu" and not args.no_feishu
            run_workflow(args, write_zotero=write_zotero, send_feishu=send_feishu)
            return
        if args.zotero:
            import_ranked_papers_to_zotero(dry_run=False)
            return
        if args.notify == "feishu":
            notify_feishu(dry_run=False)
            return

        log_step("\u672a\u6307\u5b9a\u547d\u4ee4\uff0c\u9ed8\u8ba4\u6267\u884c --run-once\u3002")
        run_workflow(args, write_zotero=not args.no_zotero, send_feishu=not args.no_feishu)
    except (ZoteroAuthenticationError, ZoteroCollectionNotFoundError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    except RuntimeError as error:
        print(f"\u9519\u8bef\uff1a{error}", file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print(f"错误：流程执行失败，完整异常原因：{type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
