import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from config import (
    MAX_CANDIDATES_PER_SIDE,
    ALLOW_EARNINGS_PLAYS,
    EARNINGS_PLAY_WINDOW_DAYS,
    EARNINGS_PLAY_TICKERS,
    WEEKLY_PRIORITY_TICKERS,
    ROLL_PROFIT_CAPTURE_PCT,
    ROLL_DTE_THRESHOLD,
)
from data.option_data import OptionContract, fetch_option_chain
from data.market_data import (
    fetch_price_history,
    has_upcoming_earnings,
    fetch_next_earnings_date,
    get_days_to_earnings,
)
from indicators.rsi import compute_rsi
from indicators.bollinger import compute_bollinger_bands
from indicators.realized_vol import compute_realized_vol
from strategy.option_selector import (
    EnrichedOption,
    enrich_options,
    enrich_options_watchlist,
    filter_by_delta,
)


@dataclass
class PremiumOpportunity:
    ticker: str
    direction: str  # "call" or "put"
    underlying_price: float
    rsi: float
    iv_rank: Optional[float]
    enriched_option: EnrichedOption
    annual_return: float = 0.0
    liquidity: float = 0.0
    rv: float = float("nan")
    iv_rv_ratio: float = float("nan")
    score: float = 0.0
    strategy_style: str = "core"
    delta_band: str = "target"
    earnings_date: Optional[dt.date] = None
    days_to_earnings: Optional[int] = None
    take_profit_pct: float = ROLL_PROFIT_CAPTURE_PCT
    roll_dte_threshold: int = ROLL_DTE_THRESHOLD


@dataclass
class WatchlistCandidate:
    ticker: str
    direction: str
    underlying_price: float
    rsi: float
    enriched_option: EnrichedOption
    setup_score: float
    note: str


def _as_close_series(close_data: pd.Series) -> pd.Series:
    """Normalize yfinance Close output to a 1-D Series."""
    if isinstance(close_data, pd.DataFrame):
        if close_data.empty:
            return pd.Series(dtype=float)
        return close_data.iloc[:, 0]
    return close_data


def _price_near_band(
    price: float, band: float, other_band: float, tol_frac: float = 0.15
) -> bool:
    if any(np.isnan(x) for x in (price, band, other_band)):
        return False
    band_range = abs(band - other_band)
    if band_range <= 0:
        return False
    dist = abs(price - band)
    return dist / band_range <= tol_frac


def _passes_side_setup(
    side: str,
    price: float,
    rsi: float,
    upper: float,
    middle: float,
    lower: float,
) -> bool:
    if side == "call":
        strong_signal = rsi >= 63 and _price_near_band(price, upper, lower, tol_frac=0.22)
        fallback_signal = rsi >= 58 and price >= middle and _price_near_band(price, upper, lower, tol_frac=0.35)
        return strong_signal or fallback_signal

    strong_signal = rsi <= 37 and _price_near_band(price, lower, upper, tol_frac=0.22)
    fallback_signal = rsi <= 42 and price <= middle and _price_near_band(price, lower, upper, tol_frac=0.35)
    return strong_signal or fallback_signal


def _closeness_to_setup(
    side: str,
    price: float,
    rsi: float,
    upper: float,
    middle: float,
    lower: float,
) -> float:
    band_range = abs(upper - lower)
    if band_range <= 0 or any(np.isnan(x) for x in (price, rsi, upper, middle, lower)):
        return 0.0

    if side == "call":
        rsi_score = np.clip((rsi - 50.0) / 15.0, 0.0, 1.0)
        location_score = 1.0 if price >= middle else 0.0
        band_score = np.clip(1.0 - abs(price - upper) / band_range, 0.0, 1.0)
    else:
        rsi_score = np.clip((50.0 - rsi) / 15.0, 0.0, 1.0)
        location_score = 1.0 if price <= middle else 0.0
        band_score = np.clip(1.0 - abs(price - lower) / band_range, 0.0, 1.0)

    return float(0.45 * rsi_score + 0.20 * location_score + 0.35 * band_score)


def evaluate_ticker(ticker: str, today: Optional[dt.date] = None) -> List[PremiumOpportunity]:
    """Run premium-selling logic for a single ticker."""
    if today is None:
        today = dt.date.today()

    hist = fetch_price_history(ticker, end_date=today)
    if hist is None or hist.empty:
        return []

    # Earnings blackout filter
    days_to_earnings = get_days_to_earnings(ticker, today=today)
    earnings_date = None
    if days_to_earnings is not None:
        try:
            earnings_date = fetch_next_earnings_date(ticker)
        except Exception:
            earnings_date = None

    earnings_play = (
        ALLOW_EARNINGS_PLAYS
        and ticker in EARNINGS_PLAY_TICKERS
        and days_to_earnings is not None
        and 0 <= days_to_earnings <= EARNINGS_PLAY_WINDOW_DAYS
    )
    if has_upcoming_earnings(ticker, today=today) and not earnings_play:
        return []

    close = _as_close_series(hist["Close"])
    if close.empty:
        return []
    rsi_series = compute_rsi(close)
    bb = compute_bollinger_bands(close)
    rv = compute_realized_vol(close)

    # Use .iloc[...] and .item() to avoid pandas FutureWarning on float(Series)
    latest_rsi = rsi_series.iloc[-1].item() if hasattr(rsi_series.iloc[-1], "item") else float(rsi_series.iloc[-1])
    bb_row = bb.iloc[-1]
    price = float(close.iloc[-1])
    upper = float(bb_row["upper"])
    middle = float(bb_row["middle"])
    lower = float(bb_row["lower"])

    call_setup = _passes_side_setup("call", price, latest_rsi, upper, middle, lower)
    put_setup = _passes_side_setup("put", price, latest_rsi, upper, middle, lower)
    if earnings_play:
        call_setup = True
        put_setup = True
    if not call_setup and not put_setup:
        return []

    weekly_preferred = ticker in WEEKLY_PRIORITY_TICKERS or earnings_play
    calls, puts = fetch_option_chain(
        ticker,
        valuation_date=today,
        include_weeklies=weekly_preferred,
        include_earnings_cycle=earnings_play,
    )
    if not calls and not puts:
        return []

    opps: List[PremiumOpportunity] = []

    def _process_side(
        side: str,
        option_list: List[OptionContract],
        rsi: float,
    ) -> None:
        nonlocal opps
        if not option_list:
            return
        if side == "call" and not call_setup:
            return
        if side == "put" and not put_setup:
            return

        enriched = enrich_options(option_list, spot=price, valuation_date=today)
        enriched = filter_by_delta(
            enriched,
            side=side,
            max_candidates=MAX_CANDIDATES_PER_SIDE,
        )
        if not enriched:
            return

        shortlisted = sorted(
            enriched,
            key=lambda e: (
                1 if earnings_play and e.cycle == "weekly" else 0,
                1 if e.delta_band == "aggressive" else 0,
                e.annualized_return,
                e.contract.implied_vol,
                e.contract.open_interest,
                e.contract.volume,
            ),
            reverse=True,
        )[:MAX_CANDIDATES_PER_SIDE]

        for candidate in shortlisted:
            # Compute IV / RV ratio using the selected contract's implied volatility
            if rv is not None and not np.isnan(rv) and rv > 0 and candidate.contract.implied_vol:
                iv_rv_ratio = float(candidate.contract.implied_vol) / rv
            else:
                iv_rv_ratio = float("nan")

            opps.append(
                PremiumOpportunity(
                    ticker=ticker,
                    direction=side,
                    underlying_price=price,
                    rsi=rsi,
                    iv_rank=None,
                    enriched_option=candidate,
                    annual_return=candidate.annualized_return,
                    rv=rv,
                    iv_rv_ratio=iv_rv_ratio,
                    strategy_style="earnings" if earnings_play else candidate.cycle,
                    delta_band=candidate.delta_band,
                    earnings_date=earnings_date,
                    days_to_earnings=days_to_earnings,
                )
            )

    _process_side("call", calls, latest_rsi)
    _process_side("put", puts, latest_rsi)

    return opps


def evaluate_ticker_watchlist(
    ticker: str,
    today: Optional[dt.date] = None,
) -> List[WatchlistCandidate]:
    """Return near-miss watchlist candidates when strict opportunities are absent."""
    if today is None:
        today = dt.date.today()

    hist = fetch_price_history(ticker, end_date=today)
    if hist is None or hist.empty:
        return []

    if has_upcoming_earnings(ticker, today=today):
        return []

    close = _as_close_series(hist["Close"])
    if close.empty:
        return []
    rsi_series = compute_rsi(close)
    bb = compute_bollinger_bands(close)

    latest_rsi = rsi_series.iloc[-1].item() if hasattr(rsi_series.iloc[-1], "item") else float(rsi_series.iloc[-1])
    bb_row = bb.iloc[-1]
    price = float(close.iloc[-1])
    upper = float(bb_row["upper"])
    middle = float(bb_row["middle"])
    lower = float(bb_row["lower"])

    call_setup_score = _closeness_to_setup("call", price, latest_rsi, upper, middle, lower)
    put_setup_score = _closeness_to_setup("put", price, latest_rsi, upper, middle, lower)
    if call_setup_score < 0.35 and put_setup_score < 0.35:
        return []

    calls, puts = fetch_option_chain(ticker, valuation_date=today)
    if not calls and not puts:
        return []

    watchlist: List[WatchlistCandidate] = []

    def _build_watch(side: str, option_list: List[OptionContract]) -> None:
        nonlocal watchlist
        if not option_list:
            return

        setup_score = call_setup_score if side == "call" else put_setup_score
        if setup_score < 0.35:
            return

        enriched = enrich_options_watchlist(option_list, spot=price, valuation_date=today)
        enriched = filter_by_delta(enriched, side=side, max_candidates=1)
        if not enriched:
            return

        best = max(
            enriched,
            key=lambda e: (
                setup_score,
                e.annualized_return,
                e.contract.open_interest,
                e.contract.volume,
            ),
        )
        note = (
            "Passed setup but missed strict quality filters"
            if _passes_side_setup(side, price, latest_rsi, upper, middle, lower)
            else "Near technical trigger; worth monitoring"
        )
        watchlist.append(
            WatchlistCandidate(
                ticker=ticker,
                direction=side,
                underlying_price=price,
                rsi=latest_rsi,
                enriched_option=best,
                setup_score=setup_score,
                note=note,
            )
        )

    _build_watch("call", calls)
    _build_watch("put", puts)

    watchlist.sort(
        key=lambda c: (
            c.setup_score,
            c.enriched_option.annualized_return,
            c.enriched_option.contract.open_interest,
            c.enriched_option.contract.volume,
        ),
        reverse=True,
    )
    return watchlist[:1]
