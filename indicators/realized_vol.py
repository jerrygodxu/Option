import numpy as np
import pandas as pd


def compute_realized_vol(close: pd.Series, lookback: int = 20) -> float:
    """Compute annualized realized volatility from daily close prices.

    Uses log returns over the specified lookback window and scales by sqrt(252).
    Returns NaN if there is insufficient data.
    """
    if close is None or len(close) < lookback + 1:
        return float("nan")

    log_ret = np.log(close / close.shift(1)).dropna()
    window = log_ret.iloc[-lookback:]
    if window.empty:
        return float("nan")
    rv_daily = window.std()
    val = rv_daily.iloc[0] if hasattr(rv_daily, "iloc") else rv_daily
    return float(val * np.sqrt(252.0))

