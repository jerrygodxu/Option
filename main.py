import datetime as dt
import os
import sys

from config import REPORT_DIR, MASTER_REPORT_FILE
from data.errors import DataFetchError
from report.report_generator import generate_markdown_report
from scanner.scanner import run_scan_with_watchlist


def _merge_into_master_report(
    markdown: str,
    run_date: dt.date,
    existing: str,
) -> str:
    title = f"## Option Premium Selling Opportunities - {run_date.isoformat()}"
    sections = [
        section.strip()
        for section in existing.split("\n\n---\n\n")
        if section.strip() and not section.lstrip().startswith(title)
    ]
    if sections:
        return markdown.rstrip() + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
    return markdown


def main() -> None:
    today = dt.date.today()
    try:
        opportunities, watchlist = run_scan_with_watchlist(run_date=today)
    except DataFetchError as exc:
        print(f"Data fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    markdown = generate_markdown_report(
        opportunities,
        run_date=today,
        watchlist=watchlist,
    )

    os.makedirs(REPORT_DIR, exist_ok=True)

    # 1) Write per-day report (kept for archival/debugging)
    daily_filename = os.path.join(
        REPORT_DIR, f"options_premium_scan_{today.isoformat()}.md"
    )
    with open(daily_filename, "w", encoding="utf-8") as f:
        f.write(markdown)

    # 2) Maintain a single rolling master report, newest day on top
    master_path = os.path.join(REPORT_DIR, MASTER_REPORT_FILE)
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            existing = f.read().strip()
    else:
        existing = ""

    combined = _merge_into_master_report(markdown, today, existing)

    with open(master_path, "w", encoding="utf-8") as f:
        f.write(combined)

    print(markdown)


if __name__ == "__main__":
    main()
