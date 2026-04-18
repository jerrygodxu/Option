import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from config import IVR_LOOKBACK_DAYS, IVR_MIN_HISTORY_DAYS, IV_HISTORY_FILE
from data.option_data import OptionContract


def _load_iv_history() -> pd.DataFrame:
    try:
        df = pd.read_csv(IV_HISTORY_FILE, parse_dates=["date"])
        df["ticker"] = df["ticker"].astype(str)
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=["ticker", "date", "iv"])


def _save_iv_history(df: pd.DataFrame) -> None:
    df = df.sort_values(["ticker", "date"])
    df.to_csv(IV_HISTORY_FILE, index=False)


def update_iv_history(ticker: str, date: dt.date, atm_iv: float) -> None:
    """Update stored IV history with today's ATM IV for the ticker."""
    if np.isnan(atm_iv) or atm_iv <= 0:
        return
    hist = _load_iv_history()
    date_ts = pd.Timestamp(date)
    mask = (hist["ticker"] == ticker) & (hist["date"] == date_ts)
    if mask.any():
        hist.loc[mask, "iv"] = atm_iv
    else:
        hist = pd.concat(
            [
                hist,
                pd.DataFrame({"ticker": [ticker], "date": [date_ts], "iv": [atm_iv]}),
            ],
            ignore_index=True,
        )
    cutoff = date_ts - pd.Timedelta(days=IVR_LOOKBACK_DAYS * 2)
    hist = hist[hist["date"] >= cutoff]
    _save_iv_history(hist)


def compute_iv_rank(ticker: str, date: dt.date, current_iv: float) -> Optional[float]:
    """Compute IV Rank for the ticker using stored IV history."""
    if np.isnan(current_iv) or current_iv <= 0:
        return None
    hist = _load_iv_history()
    if hist.empty:
        return None
    date_ts = pd.Timestamp(date)
    start = date_ts - pd.Timedelta(days=IVR_LOOKBACK_DAYS)
    sub = hist[
        (hist["ticker"] == ticker)
        & (hist["date"] >= start)
        & (hist["date"] <= date_ts)
    ]
    if len(sub) < IVR_MIN_HISTORY_DAYS:
        return None
    iv_min = sub["iv"].min()
    iv_max = sub["iv"].max()
    if iv_max <= iv_min:
        return None
    iv_rank = (current_iv - iv_min) / (iv_max - iv_min)
    return float(np.clip(iv_rank, 0.0, 1.0))


def extract_atm_iv(contracts: list[OptionContract], spot: float) -> float:
    """Approximate ATM IV by selecting the contract with strike closest to spot."""
    if not contracts:
        return np.nan
    best = min(contracts, key=lambda c: abs(c.strike - spot))
    iv = getattr(best, "implied_vol", np.nan)
    if iv is None:
        return np.nan
    return float(iv)

