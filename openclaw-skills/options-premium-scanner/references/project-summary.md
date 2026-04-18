# Project Summary

This repository scans a fixed universe of liquid US ETFs and stocks, then ranks short-option premium opportunities before the US session.

## Universe

- ETFs: `SPY QQQ IWM DIA TLT GLD XLE XLF XLK SMH`
- Stocks: `AAPL MSFT NVDA META AMZN GOOGL TSLA AMD NFLX COIN PLTR UBER CRWD SHOP`

## Data Sources

- Price history, option chains, VIX, and earnings dates come from `yfinance`.
- The scanner uses daily history, not intraday data.

## Global Filters

- Skip all trades when VIX is below `15`.
- Skip single-stock names with earnings in the next `7` days.
- ETFs are exempt from the earnings filter.

## Technical Setup Logic

Per ticker, the scanner computes:

- `RSI(14)`
- `Bollinger Bands(20, 2)`
- realized volatility

Setup checks:

- `CALL`: prefer overbought names near the upper band.
  - strong trigger: `RSI >= 63` and near upper band
  - fallback trigger: `RSI >= 58`, price above middle band, and still reasonably close to upper band
- `PUT`: prefer oversold names near the lower band.
  - strong trigger: `RSI <= 37` and near lower band
  - fallback trigger: `RSI <= 42`, price below middle band, and still reasonably close to lower band

## Option Selection Logic

- Pull up to `4` expirations closest to the configured `20-60 DTE` window.
- Enrich each contract with:
  - DTE
  - Black-Scholes delta
  - premium yield
  - annualized return
- Delta targeting:
  - calls: around `+0.20`
  - puts: around `-0.20`
  - strict tolerance first, then wider fallback tolerance
- Quality filters:
  - minimum premium about `1.2`
  - minimum open interest about `150`
  - minimum annualized return about `5%`
  - spread and spread-percent limits
- If too few strict matches exist, relaxed filters are allowed.

## Ranking Logic

Each candidate gets a composite score:

- `40%` normalized annualized return
- `30%` normalized liquidity using `log1p(open_interest) + log1p(volume)`
- `20%` IV-to-realized-volatility preference, but only when `IV/RV > 1.3`
- `10%` RSI extremeness

## Final Selection

- Keep diversity by limiting each ticker to at most `2` final ideas.
- Try to keep at least `3` calls and `3` puts when available.
- Final output limit is `10` names.
- If no strict opportunities survive, generate a looser watchlist of near-miss setups instead.

## Outputs

- Fresh runs write a daily markdown report in `reports/`.
- The main workflow also prepends the newest run to `reports/options_premium_scan_all.md`.
- Reports separate `CALL` and `PUT` sections and include contract, premium, return, liquidity, signal, and score.
