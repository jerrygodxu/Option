import datetime as dt
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

import numpy as np

from config import (
    FINAL_SELECTION_LIMIT,
    MAX_OPPS_PER_TICKER,
    MIN_OPPS_PER_DIRECTION,
    VIX_MIN_LEVEL,
    VIX_MAX_LEVEL,
    MAX_OTM_BUFFER_FOR_SCORING,
    SCAN_MAX_WORKERS,
)
from data.errors import DataFetchError
from data.market_data import fetch_vix_level
from scanner.universe import get_universe
from strategy.premium_strategy import (
    PremiumOpportunity,
    WatchlistCandidate,
    evaluate_ticker,
    evaluate_ticker_watchlist,
)


def _compute_liquidity(opp: PremiumOpportunity) -> float:
    c = opp.enriched_option.contract
    # Simple liquidity proxy: log-scaled combination of OI and volume
    oi = max(c.open_interest, 0)
    vol = max(c.volume, 0)
    return float(np.log1p(oi) + np.log1p(vol))


def _normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    v_min = min(values)
    v_max = max(values)
    if v_max <= v_min:
        return [0.5 for _ in values]
    return [(v - v_min) / (v_max - v_min) for v in values]


def _compute_otm_buffer(opp: PremiumOpportunity) -> float:
    """How far OTM the strike is as a fraction of spot price (always >= 0)."""
    spot = opp.underlying_price
    strike = opp.enriched_option.contract.strike
    if spot <= 0:
        return 0.0
    if opp.direction == "call":
        raw = max((strike - spot) / spot, 0.0)
    else:
        raw = max((spot - strike) / spot, 0.0)
    return min(raw, MAX_OTM_BUFFER_FOR_SCORING)


def _compute_scores(opportunities: List[PremiumOpportunity]) -> List[PremiumOpportunity]:
    if not opportunities:
        return opportunities

    # Precompute raw metrics
    ann = [opp.enriched_option.annualized_return for opp in opportunities]
    liq = [_compute_liquidity(opp) for opp in opportunities]
    rsi_ext = [min(abs(opp.rsi - 50.0) / 50.0, 1.0) for opp in opportunities]
    otm_buf = [_compute_otm_buffer(opp) for opp in opportunities]
    iv_abs = [
        max(float(opp.enriched_option.contract.implied_vol or 0.0), 0.0)
        for opp in opportunities
    ]
    short_cycle = [1.0 / max(opp.enriched_option.dte, 1) for opp in opportunities]
    style_bonus = [
        1.0 if opp.strategy_style == "earnings" else 0.7 if opp.strategy_style == "weekly" else 0.3
        for opp in opportunities
    ]

    # IV/RV preference: only reward ratios above 1.3
    ivrv_raw: List[float] = []
    for opp in opportunities:
        ratio = opp.iv_rv_ratio
        if ratio is None or np.isnan(ratio) or ratio <= 1.3:
            ivrv_raw.append(0.0)
        else:
            ivrv_raw.append(ratio - 1.3)

    ann_norm = _normalize(ann)
    liq_norm = _normalize(liq)
    otm_norm = _normalize(otm_buf)
    iv_abs_norm = _normalize(iv_abs)
    short_cycle_norm = _normalize(short_cycle)
    style_norm = _normalize(style_bonus)
    ivrv_norm = _normalize(ivrv_raw) if any(v > 0 for v in ivrv_raw) else [0.0 for _ in opportunities]

    for i, opp in enumerate(opportunities):
        opp.annual_return = ann[i]
        opp.liquidity = liq[i]
        # Scoring aligned with "premium efficiency with guardrails":
        # 22% annual return  – still need meaningful carry
        # 18% IV/RV ratio    – prefer expensive volatility
        # 15% absolute IV    – richer contracts pay more
        # 15% liquidity      – ease of exit / roll
        # 12% short cycle    – weeklies / short DTE harvest theta faster
        # 10% OTM buffer     – keep assignment risk in check
        #  5% style bonus    – weekly / earnings structures
        #  3% RSI extremeness
        score = (
            0.22 * ann_norm[i]
            + 0.18 * ivrv_norm[i]
            + 0.15 * iv_abs_norm[i]
            + 0.15 * liq_norm[i]
            + 0.12 * short_cycle_norm[i]
            + 0.10 * otm_norm[i]
            + 0.05 * style_norm[i]
            + 0.03 * rsi_ext[i]
        )
        opp.score = score
    return opportunities


def _can_add_ticker(
    ticker_counts: Counter,
    opp: PremiumOpportunity,
    max_per_ticker: int,
) -> bool:
    return ticker_counts[opp.ticker] < max_per_ticker


def _select_diversified(opportunities: List[PremiumOpportunity]) -> List[PremiumOpportunity]:
    if not opportunities:
        return []

    ordered = sorted(opportunities, key=lambda o: o.score, reverse=True)
    ticker_counts: Counter = Counter()
    selected: List[PremiumOpportunity] = []
    seen_keys = set()

    def contract_key(opp: PremiumOpportunity) -> tuple:
        c = opp.enriched_option.contract
        return (opp.ticker, opp.direction, c.expiration, c.strike)

    def try_add(
        pool: List[PremiumOpportunity],
        direction: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        nonlocal selected
        for opp in pool:
            if len(selected) >= FINAL_SELECTION_LIMIT:
                return
            if limit is not None and limit <= 0:
                return
            if direction is not None and opp.direction != direction:
                continue
            key = contract_key(opp)
            if key in seen_keys:
                continue
            if not _can_add_ticker(ticker_counts, opp, MAX_OPPS_PER_TICKER):
                continue
            selected.append(opp)
            seen_keys.add(key)
            ticker_counts[opp.ticker] += 1
            if limit is not None:
                limit -= 1

    for direction in ("call", "put"):
        direction_pool = [opp for opp in ordered if opp.direction == direction]
        current_count = sum(1 for opp in selected if opp.direction == direction)
        needed = max(MIN_OPPS_PER_DIRECTION - current_count, 0)
        try_add(direction_pool, limit=needed)

    if len(selected) < FINAL_SELECTION_LIMIT:
        try_add(ordered)

    return selected[:FINAL_SELECTION_LIMIT]


def run_scan(run_date: Optional[dt.date] = None) -> List[PremiumOpportunity]:
    opportunities, _ = run_scan_with_watchlist(run_date=run_date)
    return opportunities


def run_scan_with_watchlist(
    run_date: Optional[dt.date] = None,
) -> Tuple[List[PremiumOpportunity], List[WatchlistCandidate]]:
    """Scan the universe and return the top premium-selling opportunities."""
    if run_date is None:
        run_date = dt.date.today()

    # VIX regime filter
    vix = fetch_vix_level(as_of_date=run_date)
    if vix < VIX_MIN_LEVEL:
        # Premium too thin in ultra-low vol
        return [], []
    if vix > VIX_MAX_LEVEL:
        # Excessive volatility; assignment risk too high
        return [], []

    universe = get_universe()

    def _evaluate_one(ticker: str) -> List[PremiumOpportunity]:
        try:
            return evaluate_ticker(ticker, today=run_date)
        except DataFetchError as exc:
            raise DataFetchError(f"Scan aborted while evaluating {ticker}: {exc}") from exc

    opportunities: List[PremiumOpportunity] = []
    max_workers = min(SCAN_MAX_WORKERS, len(universe)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for opps in executor.map(_evaluate_one, universe):
            opportunities.extend(opps)

    opportunities = _compute_scores(opportunities)
    selected = _select_diversified(opportunities)
    if selected:
        return selected, []

    def _evaluate_watchlist_one(ticker: str) -> List[WatchlistCandidate]:
        try:
            return evaluate_ticker_watchlist(ticker, today=run_date)
        except DataFetchError as exc:
            raise DataFetchError(
                f"Watchlist scan aborted while evaluating {ticker}: {exc}"
            ) from exc

    watchlist: List[WatchlistCandidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for candidates in executor.map(_evaluate_watchlist_one, universe):
            watchlist.extend(candidates)

    watchlist.sort(
        key=lambda c: (
            c.setup_score,
            c.enriched_option.annualized_return,
            c.enriched_option.contract.open_interest,
            c.enriched_option.contract.volume,
        ),
        reverse=True,
    )
    return selected, watchlist[:FINAL_SELECTION_LIMIT]
