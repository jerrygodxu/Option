#!/usr/bin/env python3

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional


DEFAULT_PROJECT_ROOT = Path("/Users/jerry/investment/Options")


def _detect_project_root() -> Path:
    env_root = os.environ.get("OPTIONS_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "main.py").exists() and (candidate / "config.py").exists():
            return candidate

    cwd = Path.cwd().resolve()
    if (cwd / "main.py").exists() and (cwd / "config.py").exists():
        return cwd

    if (DEFAULT_PROJECT_ROOT / "main.py").exists() and (DEFAULT_PROJECT_ROOT / "config.py").exists():
        return DEFAULT_PROJECT_ROOT

    raise RuntimeError("Could not locate the Options project root.")


PROJECT_ROOT = _detect_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import MASTER_REPORT_FILE, REPORT_DIR  # noqa: E402
from report.report_generator import generate_markdown_report  # noqa: E402
from scanner.scanner import run_scan_with_watchlist  # noqa: E402


def _parse_date(raw: Optional[str]) -> dt.date:
    if not raw:
        return dt.date.today()
    return dt.datetime.strptime(raw, "%Y-%m-%d").date()


def _write_reports(markdown: str, run_date: dt.date) -> None:
    report_dir = PROJECT_ROOT / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    daily_path = report_dir / f"options_premium_scan_{run_date.isoformat()}.md"
    daily_path.write_text(markdown, encoding="utf-8")

    master_path = report_dir / MASTER_REPORT_FILE
    existing = master_path.read_text(encoding="utf-8").strip() if master_path.exists() else ""
    combined = markdown.rstrip() if not existing else markdown.rstrip() + "\n\n---\n\n" + existing
    master_path.write_text(combined, encoding="utf-8")


def run_command(run_date: dt.date, write_reports: bool) -> int:
    opportunities, watchlist = run_scan_with_watchlist(run_date=run_date)
    markdown = generate_markdown_report(
        opportunities,
        run_date=run_date,
        watchlist=watchlist,
    )
    if write_reports:
        _write_reports(markdown, run_date)
    print(markdown)
    return 0


def latest_command(master: bool, date_str: Optional[str]) -> int:
    report_dir = PROJECT_ROOT / REPORT_DIR
    if master:
        path = report_dir / MASTER_REPORT_FILE
    elif date_str:
        run_date = _parse_date(date_str)
        path = report_dir / f"options_premium_scan_{run_date.isoformat()}.md"
    else:
        daily_reports = sorted(report_dir.glob("options_premium_scan_*.md"))
        path = daily_reports[-1] if daily_reports else report_dir / MASTER_REPORT_FILE

    if not path.exists():
        print(f"Report not found: {path}", file=sys.stderr)
        return 1

    print(path.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wrapper for the options premium scanner project."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a fresh scan.")
    run_parser.add_argument("--date", help="Run date in YYYY-MM-DD format.")
    run_parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not update daily/master report files.",
    )

    latest_parser = subparsers.add_parser("latest", help="Read a saved report.")
    latest_parser.add_argument(
        "--master",
        action="store_true",
        help="Read the rolling master report instead of a daily report.",
    )
    latest_parser.add_argument(
        "--date",
        help="Read a specific daily report in YYYY-MM-DD format.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return run_command(
            run_date=_parse_date(args.date),
            write_reports=not args.no_write,
        )
    if args.command == "latest":
        return latest_command(master=args.master, date_str=args.date)
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
