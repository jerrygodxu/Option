Options Premium Scanner
This repository is built to help identify better option-selling opportunities for earning premium income. It scans a defined universe of liquid US stocks and ETFs, looks for overbought or oversold setups, and highlights contracts that may offer attractive premium relative to risk, liquidity, and time to expiration.

The main goal is not to predict direction perfectly, but to support a systematic workflow for selling options with better odds of collecting premium. In practice, the scanner looks for names where market conditions, technical signals, and option pricing are aligned well enough to make short calls or short puts more attractive.

What This Project Does
Scans a basket of liquid US stocks and ETFs
Pulls market data and option chains with yfinance
Evaluates technical conditions using RSI and Bollinger Bands
Applies volatility and event filters such as VIX regime and earnings blackout
Selects contracts around the target delta range
Ranks opportunities by premium quality, liquidity, and signal strength
Writes a markdown report with the top candidates and a watchlist
Typical Use Case
This project is useful if you want to:

find good covered call candidates when a stock looks stretched to the upside
find good cash-secured put candidates when a stock looks stretched to the downside
compare option premium across a watchlist instead of checking tickers one by one
build a repeatable process for seeking premium-selling opportunities before the US market opens
How To Run
Install dependencies:
pip install -r requirements.txt
Run the scanner:
python main.py
Output
After a run, the project generates markdown reports in reports/:

a daily report such as options_premium_scan_YYYY-MM-DD.md
a rolling combined report in options_premium_scan_all.md
These reports summarize the best current opportunities for selling calls or puts to earn premium, along with contract details, returns, liquidity, and ranking score.

Notes
This is a research and workflow tool, not financial advice.
The output is intended to help narrow the search for higher-quality premium-selling setups.
Final trade decisions should still consider assignment risk, position sizing, portfolio exposure, and your own risk tolerance.
