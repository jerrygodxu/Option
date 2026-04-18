import datetime as dt
import sys
from typing import Optional, Any

import pandas as pd
import yfinance as yf

from config import (
    PRICE_LOOKBACK_DAYS,
    VIX_TICKER,
    EARNINGS_BLACKOUT_DAYS,
    ETF_UNIVERSE,
)
from data.errors import DataFetchError


def _coerce_to_date(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _extract_calendar_earnings_date(calendar: Any) -> Optional[dt.date]:
    if calendar is None:
        return None

    earnings_value = None
    if isinstance(calendar, dict):
        earnings_value = calendar.get("Earnings Date")
    elif isinstance(calendar, pd.DataFrame):
        if "Earnings Date" in calendar.index and not calendar.empty:
            row = calendar.loc["Earnings Date"]
            if hasattr(row, "iloc"):
                earnings_value = row.iloc[0]
            else:
                earnings_value = row
        elif "Earnings Date" in calendar.columns and not calendar.empty:
            earnings_value = calendar["Earnings Date"].iloc[0]

    if isinstance(earnings_value, (list, tuple)):
        for item in earnings_value:
            parsed = _coerce_to_date(item)
            if parsed is not None:
                return parsed
        return None

    return _coerce_to_date(earnings_value)


def fetch_price_history(
    ticker: str,
    lookback_days: int = PRICE_LOOKBACK_DAYS,
    end_date: Optional[dt.date] = None,
) -> Optional[pd.DataFrame]:
    """Fetch daily price history for the given ticker."""
    end = end_date or dt.date.today()
    start = end - dt.timedelta(days=lookback_days * 2)
    # yfinance's `end` is exclusive; add one day so `end_date` is included.
    end_exclusive = end + dt.timedelta(days=1)
    try:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=end_exclusive.isoformat(),
        )
    except Exception as exc:
        raise DataFetchError(f"Failed to fetch price history for {ticker}: {exc}") from exc

    if hist.empty:
        return None

    hist = hist.dropna()
    return hist


def fetch_current_price(ticker: str) -> Optional[float]:
    """Fetch the latest close/last price for the given ticker."""
    try:
        data = yf.Ticker(ticker).history(period="1d")
    except Exception as exc:
        raise DataFetchError(f"Failed to fetch current price for {ticker}: {exc}") from exc
    if data.empty:
        return None
    return float(data["Close"].iloc[-1])


def fetch_vix_level(as_of_date: Optional[dt.date] = None) -> Optional[float]:
    """Fetch the latest VIX level using the configured VIX ticker."""
    try:
        tk = yf.Ticker(VIX_TICKER)
        if as_of_date is None:
            data = tk.history(period="1d")
        else:
            start = as_of_date - dt.timedelta(days=7)
            end = as_of_date + dt.timedelta(days=1)
            data = tk.history(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        raise DataFetchError(f"Failed to fetch VIX level for {VIX_TICKER}: {exc}") from exc
    if data.empty:
        raise DataFetchError(f"No VIX data returned for {VIX_TICKER}")
    if as_of_date is not None and isinstance(data.index, pd.DatetimeIndex):
        data = data[data.index.date <= as_of_date]
        if data.empty:
            raise DataFetchError(
                f"No VIX data available on or before {as_of_date.isoformat()}"
            )
    return float(data["Close"].iloc[-1])


def fetch_next_earnings_date(ticker: str) -> Optional[dt.date]:
    """Fetch the next earnings date for the given ticker, if available."""
    tk = yf.Ticker(ticker)
    try:
        cal = tk.get_earnings_dates(limit=1)
    except Exception as exc:
        try:
            fallback = _extract_calendar_earnings_date(tk.calendar)
        except Exception as cal_exc:
            raise DataFetchError(
                f"Failed to fetch earnings date for {ticker}: {exc}; calendar fallback failed: {cal_exc}"
            ) from exc
        if fallback is not None:
            return fallback
        raise DataFetchError(f"Failed to fetch earnings date for {ticker}: {exc}") from exc

    if cal is None or cal.empty:
        return _extract_calendar_earnings_date(tk.calendar)

    dt_idx = cal.index[0]
    parsed = _coerce_to_date(dt_idx)
    if parsed is not None:
        return parsed
    return _extract_calendar_earnings_date(tk.calendar)


def has_upcoming_earnings(ticker: str, today: Optional[dt.date] = None) -> bool:
    """Return True if the ticker has earnings within the blackout window."""
    # ETFs do not have earnings; they should always pass the earnings filter.
    if ticker in ETF_UNIVERSE:
        return False
    if today is None:
        today = dt.date.today()
    try:
        next_earnings = fetch_next_earnings_date(ticker)
    except DataFetchError as exc:
        print(
            f"Warning: earnings filter skipped for {ticker}: {exc}",
            file=sys.stderr,
        )
        return False
    if next_earnings is None:
        return False
    days_to_earnings = (next_earnings - today).days
    return 0 <= days_to_earnings <= EARNINGS_BLACKOUT_DAYS


def get_days_to_earnings(
    ticker: str,
    today: Optional[dt.date] = None,
) -> Optional[int]:
    """Return the number of calendar days to the next earnings event."""
    if ticker in ETF_UNIVERSE:
        return None
    if today is None:
        today = dt.date.today()
    try:
        next_earnings = fetch_next_earnings_date(ticker)
    except DataFetchError as exc:
        print(
            f"Warning: earnings distance unavailable for {ticker}: {exc}",
            file=sys.stderr,
        )
        return None
    if next_earnings is None:
        return None
    return (next_earnings - today).days
