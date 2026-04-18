---
name: options-premium-scanner
description: Use this skill when the user wants to run or explain the US options premium-selling scanner in this repository, fetch today's call/put candidates, read the latest markdown report, or summarize the strategy logic for Telegram/OpenClaw conversations.
---

# Options Premium Scanner

Use this skill for this repository's options premium scan workflow.

## When To Use

- The user asks for today's premium-selling opportunities.
- The user wants to rerun the scanner and summarize the result.
- The user wants the latest saved report instead of a fresh scan.
- The user asks how the strategy ranks call and put candidates.

## Workflow

1. Read `references/project-summary.md` if you need the strategy logic without reopening the full codebase.
2. For a fresh run, execute:
   `python3 /Users/jerry/.openclaw/skills/options-premium-scanner/scripts/option_scan_tool.py run`
3. For a specific date, execute:
   `python3 /Users/jerry/.openclaw/skills/options-premium-scanner/scripts/option_scan_tool.py run --date YYYY-MM-DD`
4. For the latest saved rolling report, execute:
   `python3 /Users/jerry/.openclaw/skills/options-premium-scanner/scripts/option_scan_tool.py latest --master`
5. If the user only wants the most recent daily report, execute:
   `python3 /Users/jerry/.openclaw/skills/options-premium-scanner/scripts/option_scan_tool.py latest`
6. Summarize the result in compact trading language:
   - overall opportunity count
   - best call ideas
   - best put ideas
   - any watchlist names if no strict opportunities passed
   - the main filters that drove the result

## Output Expectations

- Keep the answer concise and action oriented.
- Mention that data comes from `yfinance` and may be delayed or incomplete.
- Treat results as research support, not personalized investment advice.
- If a fresh run fails because market data is unavailable, fall back to the latest saved report.

## Files

- Scanner wrapper: `/Users/jerry/.openclaw/skills/options-premium-scanner/scripts/option_scan_tool.py`
- Logic summary: `openclaw-skills/options-premium-scanner/references/project-summary.md`
- Entry point in repo: `main.py`
- Latest reports: `reports/options_premium_scan_all.md`
