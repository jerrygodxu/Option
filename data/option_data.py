import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    MIN_DTE,
    MAX_DTE,
    MAX_EXPIRATIONS_PER_TICKER,
    CORE_MIN_DTE,
    CORE_MAX_DTE,
    WEEKLY_MIN_DTE,
    WEEKLY_MAX_DTE,
    EARNINGS_MIN_DTE,
    EARNINGS_MAX_DTE,
    MAX_CORE_EXPIRATIONS_PER_TICKER,
    MAX_WEEKLY_EXPIRATIONS_PER_TICKER,
    MAX_EARNINGS_EXPIRATIONS_PER_TICKER,
)
from data.errors import DataFetchError


@dataclass
class OptionContract:
    ticker: str
    expiration: dt.date
    option_type: str  # "call" or "put"
    strike: float
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_vol: float
    in_the_money: bool

    @property
    def mid(self) -> float:
        if self.bid is None or self.ask is None:
            return np.nan
        if self.bid < 0 or self.ask < 0:
            return np.nan
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        if self.bid is None or self.ask is None:
            return np.nan
        if self.bid < 0 or self.ask < 0:
            return np.nan
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        mid = self.mid
        spread = self.spread
        if np.isnan(mid) or np.isnan(spread) or mid <= 0:
            return np.nan
        return spread / mid


def _select_expirations(
    expirations: List[str],
    valuation_date: Optional[dt.date] = None,
    include_weeklies: bool = False,
    include_earnings_cycle: bool = False,
) -> List[dt.date]:
    today = valuation_date or dt.date.today()
    parsed: List[Tuple[int, dt.date]] = []
    for exp_str in expirations:
        exp = dt.datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = (exp - today).days
        if MIN_DTE <= dte <= MAX_DTE:
            parsed.append((dte, exp))

    windows = [
        (CORE_MIN_DTE, CORE_MAX_DTE, MAX_CORE_EXPIRATIONS_PER_TICKER),
    ]
    if include_weeklies:
        windows.insert(0, (WEEKLY_MIN_DTE, WEEKLY_MAX_DTE, MAX_WEEKLY_EXPIRATIONS_PER_TICKER))
    if include_earnings_cycle:
        windows.insert(0, (EARNINGS_MIN_DTE, EARNINGS_MAX_DTE, MAX_EARNINGS_EXPIRATIONS_PER_TICKER))

    selected: List[dt.date] = []
    seen = set()
    for min_dte, max_dte, limit in windows:
        target_dte = (min_dte + max_dte) / 2.0
        ranked = [
            (abs(dte - target_dte), dte, exp)
            for dte, exp in parsed
            if min_dte <= dte <= max_dte
        ]
        ranked.sort(key=lambda item: (item[0], item[1]))
        for _, _, exp in ranked:
            if exp in seen:
                continue
            selected.append(exp)
            seen.add(exp)
            if sum(1 for chosen in selected if min_dte <= (chosen - today).days <= max_dte) >= limit:
                break

    if len(selected) < MAX_EXPIRATIONS_PER_TICKER:
        ranked_all = sorted(parsed, key=lambda item: (abs(item[0] - ((MIN_DTE + MAX_DTE) / 2.0)), item[0]))
        for _, exp in ranked_all:
            if exp in seen:
                continue
            selected.append(exp)
            seen.add(exp)
            if len(selected) >= MAX_EXPIRATIONS_PER_TICKER:
                break

    return selected[:MAX_EXPIRATIONS_PER_TICKER]


def fetch_option_chain(
    ticker: str,
    valuation_date: Optional[dt.date] = None,
    include_weeklies: bool = False,
    include_earnings_cycle: bool = False,
) -> Tuple[List[OptionContract], List[OptionContract]]:
    """Fetch option chains for nearby expirations within the configured DTE window."""
    tk = yf.Ticker(ticker)
    try:
        expirations = tk.options
    except Exception as exc:
        raise DataFetchError(f"Failed to fetch option expirations for {ticker}: {exc}") from exc

    if not expirations:
        return [], []

    selected_expirations = _select_expirations(
        expirations,
        valuation_date=valuation_date,
        include_weeklies=include_weeklies,
        include_earnings_cycle=include_earnings_cycle,
    )
    if not selected_expirations:
        return [], []

    def _build(
        df: Optional[pd.DataFrame],
        opt_type: str,
        expiration: dt.date,
    ) -> List[OptionContract]:
        if df is None or df.empty:
            return []
        contracts: List[OptionContract] = []
        for _, row in df.iterrows():
            bid = float(row.get("bid", np.nan))
            ask = float(row.get("ask", np.nan))
            if np.isnan(bid) or np.isnan(ask):
                continue

            last_price_val = row.get("lastPrice", np.nan)
            last_price = float(last_price_val) if not np.isnan(last_price_val) else np.nan

            vol_val = row.get("volume", 0)
            vol = 0 if vol_val is None or (isinstance(vol_val, float) and np.isnan(vol_val)) else int(vol_val)

            oi_val = row.get("openInterest", 0)
            oi = 0 if oi_val is None or (isinstance(oi_val, float) and np.isnan(oi_val)) else int(oi_val)

            iv_val = row.get("impliedVolatility", np.nan)
            iv = float(iv_val) if iv_val is not None and not np.isnan(iv_val) else np.nan

            contracts.append(
                OptionContract(
                    ticker=ticker,
                    expiration=expiration,
                    option_type=opt_type,
                    strike=float(row["strike"]),
                    bid=bid,
                    ask=ask,
                    last_price=last_price,
                    volume=vol,
                    open_interest=oi,
                    implied_vol=iv,
                    in_the_money=bool(row.get("inTheMoney", False)),
                )
            )
        return contracts

    calls: List[OptionContract] = []
    puts: List[OptionContract] = []
    for expiration in selected_expirations:
        try:
            chain = tk.option_chain(expiration.strftime("%Y-%m-%d"))
        except Exception as exc:
            raise DataFetchError(
                f"Failed to fetch option chain for {ticker} {expiration.isoformat()}: {exc}"
            ) from exc
        calls.extend(_build(chain.calls, "call", expiration))
        puts.extend(_build(chain.puts, "put", expiration))

    return calls, puts
