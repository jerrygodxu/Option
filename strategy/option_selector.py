import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from config import (
    TARGET_DELTA,
    DELTA_TOLERANCE,
    FALLBACK_DELTA_TOLERANCE,
    MAX_ABS_DELTA,
    MAX_CANDIDATES_PER_SIDE,
    MIN_STRICT_CANDIDATES,
    MIN_DTE,
    MAX_DTE,
    MIN_OPEN_INTEREST,
    MIN_ANNUAL_RETURN,
    MIN_PREMIUM,
    MAX_SPREAD,
    MAX_SPREAD_PCT,
    RELAXED_OPEN_INTEREST_FACTOR,
    RELAXED_ANNUAL_RETURN_FACTOR,
    RELAXED_MAX_SPREAD_FACTOR,
    RELAXED_MAX_SPREAD_PCT_FACTOR,
    MIN_STRIKE_TO_SPOT_RATIO,
    MAX_STRIKE_TO_SPOT_RATIO,
    DELTA_CONSERVATIVE_MIN,
    DELTA_CONSERVATIVE_MAX,
    DELTA_AGGRESSIVE_MIN,
    DELTA_AGGRESSIVE_MAX,
    DELTA_CONSERVATIVE_WEIGHT,
)
from data.option_data import OptionContract


@dataclass
class EnrichedOption:
    contract: OptionContract
    dte: int
    delta: Optional[float]
    premium_yield: float
    annualized_return: float
    cycle: str = "core"
    delta_band: str = "target"


def _build_enriched_options(
    options: List[OptionContract],
    spot: float,
    valuation_date: dt.date,
) -> List[EnrichedOption]:
    def classify_cycle(dte: int) -> str:
        if dte <= 14:
            return "weekly"
        if dte <= 21:
            return "swing"
        return "core"

    enriched: List[EnrichedOption] = []
    for c in options:
        if spot <= 0:
            continue
        strike_to_spot = c.strike / spot
        if (
            strike_to_spot < MIN_STRIKE_TO_SPOT_RATIO
            or strike_to_spot > MAX_STRIKE_TO_SPOT_RATIO
        ):
            continue
        dte = (c.expiration - valuation_date).days
        if dte <= 0 or dte < MIN_DTE or dte > MAX_DTE:
            continue
        mid = c.mid
        if np.isnan(mid) or mid <= 0:
            continue
        spread = c.spread
        spread_pct = c.spread_pct
        if np.isnan(spread) or np.isnan(spread_pct):
            continue
        vol = c.implied_vol
        if vol is None or np.isnan(vol) or vol <= 0:
            continue
        t_years = dte / 365.0
        delta = _black_scholes_delta(
            spot=spot,
            strike=c.strike,
            t_years=t_years,
            vol=vol,
            option_type=c.option_type,
        )
        if delta is None:
            continue
        enriched.append(
            EnrichedOption(
                contract=c,
                dte=dte,
                delta=delta,
                premium_yield=mid / c.strike,
                annualized_return=(mid / c.strike) * (365.0 / dte),
                cycle=classify_cycle(dte),
            )
        )
    return enriched


def _black_scholes_delta(
    spot: float,
    strike: float,
    t_years: float,
    vol: float,
    option_type: str,
) -> Optional[float]:
    if spot <= 0 or strike <= 0 or t_years <= 0 or vol <= 0:
        return None
    try:
        from math import log, sqrt
        from math import erf

        def norm_cdf(x: float) -> float:
            return 0.5 * (1.0 + erf(x / np.sqrt(2.0)))

        d1 = (log(spot / strike) + 0.5 * vol ** 2 * t_years) / (vol * sqrt(t_years))
        if option_type == "call":
            return norm_cdf(d1)
        else:
            return norm_cdf(d1) - 1.0
    except Exception:
        return None


def enrich_options(
    options: List[OptionContract],
    spot: float,
    valuation_date: Optional[dt.date] = None,
) -> List[EnrichedOption]:
    """Compute delta, premium yield, and annualized return for each option."""
    if valuation_date is None:
        valuation_date = dt.date.today()

    relaxed_open_interest = max(int(MIN_OPEN_INTEREST * RELAXED_OPEN_INTEREST_FACTOR), 1)
    relaxed_annual_return = max(MIN_ANNUAL_RETURN * RELAXED_ANNUAL_RETURN_FACTOR, 0.0)
    relaxed_max_spread = max(MAX_SPREAD * RELAXED_MAX_SPREAD_FACTOR, 0.0)
    relaxed_max_spread_pct = max(MAX_SPREAD_PCT * RELAXED_MAX_SPREAD_PCT_FACTOR, 0.0)
    strict_matches: List[EnrichedOption] = []
    relaxed_matches: List[EnrichedOption] = []

    for enriched_option in _build_enriched_options(options, spot, valuation_date):
        c = enriched_option.contract
        mid = c.mid
        if mid < MIN_PREMIUM:
            continue
        spread = c.spread
        spread_pct = c.spread_pct
        if (
            c.open_interest >= MIN_OPEN_INTEREST
            and enriched_option.annualized_return >= MIN_ANNUAL_RETURN
            and spread <= MAX_SPREAD
            and spread_pct <= MAX_SPREAD_PCT
        ):
            strict_matches.append(enriched_option)
            continue
        if (
            c.open_interest >= relaxed_open_interest
            and enriched_option.annualized_return >= relaxed_annual_return
            and spread <= relaxed_max_spread
            and spread_pct <= relaxed_max_spread_pct
        ):
            relaxed_matches.append(enriched_option)

    if len(strict_matches) >= MIN_STRICT_CANDIDATES:
        return strict_matches
    return strict_matches + relaxed_matches


def enrich_options_watchlist(
    options: List[OptionContract],
    spot: float,
    valuation_date: Optional[dt.date] = None,
) -> List[EnrichedOption]:
    """Looser enrichment used for near-miss watchlist reporting."""
    if valuation_date is None:
        valuation_date = dt.date.today()

    watchlist_matches: List[EnrichedOption] = []
    for enriched_option in _build_enriched_options(options, spot, valuation_date):
        c = enriched_option.contract
        if c.mid < max(MIN_PREMIUM * 0.75, 0.5):
            continue
        if c.open_interest < max(int(MIN_OPEN_INTEREST * 0.3), 25):
            continue
        watchlist_matches.append(enriched_option)
    return watchlist_matches


def filter_by_delta(
    options: List[EnrichedOption],
    side: str,
    max_candidates: int = MAX_CANDIDATES_PER_SIDE,
) -> List[EnrichedOption]:
    """Blend conservative and aggressive delta buckets before wider fallback."""
    if side not in {"call", "put"}:
        return []
    target = TARGET_DELTA if side == "call" else -TARGET_DELTA

    def rank_key(o: EnrichedOption) -> tuple:
        cycle_rank = {"weekly": 0, "swing": 1, "core": 2}.get(o.cycle, 3)
        return (
            cycle_rank,
            abs(o.delta - target),
            -o.annualized_return,
            -o.contract.implied_vol,
            -o.contract.open_interest,
            -o.contract.volume,
        )

    ranked = sorted(
        (
            o
            for o in options
            if o.delta is not None and abs(o.delta) <= MAX_ABS_DELTA
        ),
        key=rank_key,
    )
    if not ranked:
        return []

    conservative_limit = max(int(round(max_candidates * DELTA_CONSERVATIVE_WEIGHT)), 1)
    aggressive_limit = max_candidates - conservative_limit
    if aggressive_limit <= 0 and max_candidates > 1:
        aggressive_limit = 1
        conservative_limit = max_candidates - aggressive_limit

    conservative: List[EnrichedOption] = []
    aggressive: List[EnrichedOption] = []
    for option in ranked:
        abs_delta = abs(option.delta)
        if DELTA_CONSERVATIVE_MIN <= abs_delta <= DELTA_CONSERVATIVE_MAX:
            conservative.append(
                EnrichedOption(
                    contract=option.contract,
                    dte=option.dte,
                    delta=option.delta,
                    premium_yield=option.premium_yield,
                    annualized_return=option.annualized_return,
                    cycle=option.cycle,
                    delta_band="conservative",
                )
            )
        if DELTA_AGGRESSIVE_MIN <= abs_delta <= DELTA_AGGRESSIVE_MAX:
            aggressive.append(
                EnrichedOption(
                    contract=option.contract,
                    dte=option.dte,
                    delta=option.delta,
                    premium_yield=option.premium_yield,
                    annualized_return=option.annualized_return,
                    cycle=option.cycle,
                    delta_band="aggressive",
                )
            )

    blended: List[EnrichedOption] = []
    blended.extend(conservative[:conservative_limit])
    blended.extend(aggressive[:aggressive_limit])
    if blended:
        deduped = []
        seen = set()
        for option in sorted(blended, key=rank_key):
            key = (option.contract.expiration, option.contract.strike, option.contract.option_type)
            if key in seen:
                continue
            deduped.append(option)
            seen.add(key)
        if deduped:
            return deduped[:max_candidates]

    strict = [o for o in ranked if abs(o.delta - target) <= DELTA_TOLERANCE]
    if strict:
        return strict[:max_candidates]
    relaxed = [o for o in ranked if abs(o.delta - target) <= FALLBACK_DELTA_TOLERANCE]
    if relaxed:
        return relaxed[:max_candidates]

    return ranked[:max_candidates]
