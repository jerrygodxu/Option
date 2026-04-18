import pandas as pd

from config import BB_PERIOD, BB_STD


def compute_bollinger_bands(
    close: pd.Series, period: int = BB_PERIOD, num_std: float = BB_STD
) -> pd.DataFrame:
    """Compute Bollinger Bands for a price series."""
    ma = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std

    # Explicitly align on the original index to avoid scalar-construction issues
    df = pd.DataFrame(index=close.index)
    df["middle"] = ma
    df["upper"] = upper
    df["lower"] = lower
    return df

