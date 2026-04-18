import datetime as dt
import os
import time

import schedule

from config import REPORT_DIR
from report.report_generator import generate_markdown_report
from scanner.scanner import run_scan


def job() -> None:
    today = dt.date.today()
    opportunities = run_scan(run_date=today)
    markdown = generate_markdown_report(opportunities, run_date=today)

    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = os.path.join(
        REPORT_DIR, f"options_premium_scan_{today.isoformat()}.md"
    )
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(markdown)


def start_scheduler() -> None:
    """Run the scanner every weekday at 07:30 US/Eastern-equivalent local time.

    Note: `schedule` uses local system time. Make sure your system timezone is set
    appropriately or adjust the scheduled time below.
    """
    schedule.every().monday.at("07:30").do(job)
    schedule.every().tuesday.at("07:30").do(job)
    schedule.every().wednesday.at("07:30").do(job)
    schedule.every().thursday.at("07:30").do(job)
    schedule.every().friday.at("07:30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    start_scheduler()

