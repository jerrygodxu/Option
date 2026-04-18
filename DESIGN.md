## Option Premium Selling Scanner Design (v2)

### 1. Goal & Scope

- **Goal**: Scan a fixed universe of liquid US stocks/ETFs and identify the best opportunities to **sell options (calls or puts)** for premium income before US market open.
- **Frequency**: Once per trading day (via manual run or scheduler).
- **Key idea**: Combine **technical signals** (RSI, Bollinger Bands), **volatility regime** (VIX, IV Rank), **earnings risk filter**, and **micro liquidity** to rank trades and output a **Top 10** list.

### 2. High-Level Architecture

Top-level modules in `/Users/jerry/Options`:

- `config.py` – universe and global parameters.
- `data/market_data.py` – equity prices, VIX, and earnings calendar.
- `data/option_data.py` – option chains and contract model.
- `indicators/rsi.py` – RSI(14).
- `indicators/bollinger.py` – Bollinger Bands(20, 2).
- `indicators/iv_rank.py` – local ATM IV history and IV Rank.
- `strategy/option_selector.py` – Delta, yield, annualized return enrichment and Delta filtering.
- `strategy/premium_strategy.py` – per-ticker SELL CALL / SELL PUT evaluation and opportunity construction.
- `scanner/universe.py` – static universe definition (config-driven).
- `scanner/scanner.py` – cross-sectional scan, VIX filter, scoring, and Top 10 selection.
- `report/report_generator.py` – Markdown Top 10 report.
- `main.py` – entry point for a single daily run.

Data flow for a run:

`main.py` → `scanner.run_scan()` → `strategy.evaluate_ticker()` → `data.*`, `indicators.*`, `strategy.option_selector` → `scanner._compute_scores()` → `report.generate_markdown_report()`.

### 3. Universe & Data

#### Universe

- `config.UNIVERSE`: static list of liquid US stocks/ETFs (SPY, QQQ, IWM, DIA, TLT, GLD, XLE, XLF, XLK, SMH, AAPL, MSFT, NVDA, META, AMZN, GOOGL, TSLA, AMD, NFLX, COIN, PLTR, UBER, CRWD, SHOP).
- `scanner.universe.get_universe()` simply returns this list.

#### Market Data (`data/market_data.py`)

- `fetch_price_history(ticker, lookback_days=PRICE_LOOKBACK_DAYS)`:
  - Daily OHLCV history via `yfinance.download`.
  - 6 months+ of data (configurable).
- `fetch_current_price(ticker)`:
  - Latest close from `yfinance.Ticker(ticker).history(period="1d")`.
- **VIX**:
  - `fetch_vix_level()`:
    - Uses `config.VIX_TICKER` (default `^VIX`) and reads latest close.
- **Earnings**:
  - `fetch_next_earnings_date(ticker)`:
    - Uses `yfinance.Ticker(ticker).get_earnings_dates(limit=1)` and extracts the next date, if any.
  - `has_upcoming_earnings(ticker, today)`:
    - Returns `True` if `0 <= days_to_earnings <= config.EARNINGS_BLACKOUT_DAYS` (default 7).

#### Option Data (`data/option_data.py`)

- `OptionContract`:
  - `ticker`, `expiration`, `option_type` (`"call"` / `"put"`), `strike`, `bid`, `ask`, `last_price`, `volume`, `open_interest`, `implied_vol`, `in_the_money`.
  - `mid` property = `(bid + ask) / 2` with sanity checks.
- `fetch_option_chain(ticker)`:
  - Retrieves all expirations via `yfinance.Ticker.options`.
  - `_select_expiration()` chooses an expiry with **30–45 DTE** closest to midrange (config `MIN_DTE`, `MAX_DTE`).
  - Builds `OptionContract` lists for calls and puts.

### 4. Indicators

#### RSI (indicators/rsi.py)

- `compute_rsi(close, period=RSI_PERIOD)`:
  - Standard RSI(14):
    - Price diff → gains/losses → rolling mean → RS → RSI.

#### Bollinger Bands (indicators/bollinger.py)

- `compute_bollinger_bands(close, period=BB_PERIOD, num_std=BB_STD)`:
  - Rolling mean and std over closing prices (default 20, 2).
  - Returns DataFrame with:
    - `middle` (MA), `upper` (MA + 2σ), `lower` (MA - 2σ).
  - Explicitly aligns results with `close.index` to avoid scalar construction issues.

#### IV Rank (indicators/iv_rank.py)

- Local storage:
  - CSV file `config.IV_HISTORY_FILE` with columns: `ticker`, `date`, `iv`.
  - `update_iv_history(ticker, date, atm_iv)`:
    - Inserts or updates today’s ATM IV for the ticker.
    - Keeps only a rolling window (about `2 * IVR_LOOKBACK_DAYS` days).
  - `_load_iv_history()` / `_save_iv_history()` handle file I/O.
- IV Rank:
  - `compute_iv_rank(ticker, date, current_iv)`:
    - Subset IV history for the last `IVR_LOOKBACK_DAYS` (default 252).
    - Require at least `IVR_MIN_HISTORY_DAYS` samples (default 30).
    - Compute:
      - `IV_rank = (current_IV - IV_min) / (IV_max - IV_min)` clipped \[0, 1\].
  - ATM IV extraction:
    - `extract_atm_iv(contracts, spot)`:
      - Selects contract with strike closest to spot and returns its `implied_vol`.

### 5. Strategy Logic

All per-ticker logic lives in `strategy/premium_strategy.py`.

#### 5.1 PremiumOpportunity Model

- `PremiumOpportunity` fields:
  - `ticker`: underlying symbol.
  - `direction`: `"call"` or `"put"`.
  - `underlying_price`: latest close.
  - `rsi`: latest RSI(14).
  - `iv_rank`: float in \[0, 1\] (or `None` if insufficient history).
  - `enriched_option`: selected `EnrichedOption` (see below).
  - `annual_return`: raw annualized return (for ranking).
  - `liquidity`: scalar liquidity proxy.
  - `score`: composite score used for final ranking.

#### 5.2 Option Enrichment & Delta Targeting (strategy/option_selector.py)

- `EnrichedOption`:
  - Wraps `OptionContract` with:
    - `dte`, `delta`, `premium_yield`, `annualized_return`.
- `_black_scholes_delta(spot, strike, t_years, vol, option_type)`:
  - Computes option delta from Black–Scholes (risk-free rate implicit in vol term for simplicity).
- `enrich_options(options, spot, expiration)`:
  - Filters out contracts with invalid mid-price or IV.
  - For remaining contracts:
    - Computes delta.
    - `premium_yield = mid / strike`.
    - `annualized_return = premium_yield * 365 / DTE`.
- `filter_by_delta(options, side)`:
  - For `side == "call"`:
    - Keep `delta` near `+config.TARGET_DELTA` (default 0.2) within `config.DELTA_TOLERANCE`.
  - For `side == "put"`:
    - Keep `delta` near `-config.TARGET_DELTA`.

#### 5.3 Earnings Blackout

- In `evaluate_ticker(ticker, today)`:
  - After fetching price history:
    - Calls `has_upcoming_earnings(ticker, today)`.
    - If `True` (earnings within next `EARNINGS_BLACKOUT_DAYS`, default 7), **immediately skip** the ticker and return `[]`.

#### 5.4 Technical & IV Conditions (Direction Selection)

- Compute RSI and Bollinger from latest close:
  - `latest_rsi`, `upper`, `lower`.
- Helper `_price_near_band(price, band, other_band, tol_frac=0.15)`:
  - Uses `abs(price - band) / abs(upper - lower) <= tol_frac` to define “near band”.
- Fetch option chain and compute ATM IV:
  - `calls, puts, exp = fetch_option_chain(ticker)`.
  - `atm_iv = extract_atm_iv(calls + puts, spot=price)`.
  - If valid:
    - `update_iv_history` + `compute_iv_rank`.
- Per side (`"call"` / `"put"`), gate conditions:
  - **SELL CALL**:
    - `RSI >= 70`.
    - Price near **upper** Bollinger band.
    - If `iv_rank` available: must be ≥ `config.MIN_IVR` (default 0.5 = 50%).
  - **SELL PUT**:
    - `RSI <= 30`.
    - Price near **lower** Bollinger band.
    - Same IV Rank condition as above.
- If a side passes:
  - Enrich that side’s contracts (`enrich_options` → `filter_by_delta`).
  - If any remain, select the **single best** contract:
    - `max(enriched, key=lambda e: e.annualized_return)`.
  - Wrap into `PremiumOpportunity`.

### 6. Cross-Sectional Scan & Scoring

Implemented in `scanner/scanner.py`.

#### 6.1 VIX Filter (Global Vol Regime)

- `config.VIX_TICKER = "^VIX"`, `config.VIX_MIN_LEVEL = 15.0`.
- At the start of `run_scan(run_date)`:
  - `vix = fetch_vix_level()`.
  - If `vix` is available and `< VIX_MIN_LEVEL`, return `[]`:
    - **No premium-selling trades in low-volatility regimes.**

#### 6.2 Scanning the Universe

- `run_scan(run_date)`:
  - If `run_date` is `None`, uses today’s date.
  - For each ticker in `get_universe()`:
    - Calls `evaluate_ticker(ticker, today=run_date)`.
    - Aggregates all resulting `PremiumOpportunity` objects.

#### 6.3 Scoring Model

- `_compute_liquidity(opp)`:
  - Uses the selected contract’s `open_interest` and `volume`:
    - `liquidity = log1p(OI) + log1p(volume)`.
- `_normalize(values)`:
  - Min–max scaling to \[0, 1\], or `0.5` constant if all equal.
- `_compute_scores(opportunities)`:
  - For each `PremiumOpportunity`:
    - `iv_norm`:
      - `opp.iv_rank` if not `None` (already in \[0, 1\]); otherwise `0.0`.
    - `ann_norm`:
      - Min–max normalized annualized returns from `opp.enriched_option.annualized_return`.
    - `liq_norm`:
      - Min–max normalized liquidity metric.
    - `rsi_ext`:
      - RSI extremeness measure:
        - `rsi_ext = min(|RSI - 50| / 50, 1.0)`, where 0 ≈ neutral, 1 ≈ very overbought/oversold.
    - **Composite score**:
      - `score = 0.4 * iv_norm + 0.3 * ann_norm + 0.2 * liq_norm + 0.1 * rsi_ext`.
    - Persisted into:
      - `opp.annual_return`, `opp.liquidity`, `opp.score`.
- After scoring:
  - `run_scan` sorts by `opp.score` descending and **keeps only the top 10**:
    - `return opportunities[:10]`.

### 7. Reporting (Top 10)

`report/report_generator.py`:

- `generate_markdown_report(opportunities, run_date)`:
  - If empty: output a simple “no opportunities” message.
  - Otherwise:
    - Builds a table with columns:
      - `Rank`, `Ticker`, `Direction`, `Underlying`, `RSI(14)`, `IV Rank`, `DTE`, `Strike`, `Premium`, `Premium Yield`, `Annualized Return`, `Liquidity`, `Score`, `OI`, `Volume`, `Expiration`.
    - Opportunities are again sorted by `score` (defensive, though already sorted in scanner) and numbered 1–N (N ≤ 10).
    - Footnote documents:
      - IV Rank as local ATM IV-based metric.
      - Score composition: **40% IV Rank, 30% annualized return, 20% liquidity, 10% RSI extremeness**.

### 8. Entry Point & Scheduling

- `main.py`:
  - `run_scan()` for the current date.
  - Generates Markdown via `generate_markdown_report`.
  - Writes to `config.REPORT_DIR` as `options_premium_scan_YYYY-MM-DD.md` and prints to stdout.
- Scheduler (not detailed here, but in separate module or external cron/systemd) should call `python main.py` **before US market open**.

---

**Version History**

- **v1**: Initial design – RSI/Bollinger/IV Rank, 30–45 DTE, Delta≈0.2, basic filters, Markdown report.
- **v2**: Added VIX low-vol filter (no trades when VIX < 15), earnings blackout window (7 days), composite scoring model (IV Rank, annual return, liquidity, RSI extremeness), and Top 10 ranking in report. Updated Bollinger implementation for robustness.

