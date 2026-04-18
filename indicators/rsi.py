import pandas as pd
import numpy as np

from config import RSI_PERIOD


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Compute RSI for a price series."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

