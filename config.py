UNIVERSE = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "GLD",
    "XLE",
    "XLF",
    "XLK",
    "SMH",
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "GOOGL",
    "TSLA",
    "AMD",
    "NFLX",
    "COIN",
    "PLTR",
    "UBER",
    "CRWD",
    "SHOP",
]

ETF_UNIVERSE = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "GLD",
    "XLE",
    "XLF",
    "XLK",
    "SMH",
]

# Lookback for price data (in days)
PRICE_LOOKBACK_DAYS = 180

# Technical indicator parameters
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0

# IV Rank parameters (historical window in trading days)
IVR_LOOKBACK_DAYS = 252
IVR_MIN_HISTORY_DAYS = 30
IV_HISTORY_FILE = "iv_history.csv"

# Option selection parameters
MIN_DTE = 5
MAX_DTE = 45
CORE_MIN_DTE = 21
CORE_MAX_DTE = 45
WEEKLY_MIN_DTE = 7
WEEKLY_MAX_DTE = 14
EARNINGS_MIN_DTE = 5
EARNINGS_MAX_DTE = 10
MAX_EXPIRATIONS_PER_TICKER = 6
MAX_CORE_EXPIRATIONS_PER_TICKER = 3
MAX_WEEKLY_EXPIRATIONS_PER_TICKER = 2
MAX_EARNINGS_EXPIRATIONS_PER_TICKER = 2
TARGET_DELTA = 0.15
DELTA_TOLERANCE = 0.05
FALLBACK_DELTA_TOLERANCE = 0.10
MAX_ABS_DELTA = 0.32
DELTA_CONSERVATIVE_MIN = 0.10
DELTA_CONSERVATIVE_MAX = 0.16
DELTA_AGGRESSIVE_MIN = 0.20
DELTA_AGGRESSIVE_MAX = 0.30
DELTA_CONSERVATIVE_WEIGHT = 0.7
DELTA_AGGRESSIVE_WEIGHT = 0.3
MAX_CANDIDATES_PER_SIDE = 4
MIN_STRICT_CANDIDATES = 1

# Basic filters (can be tuned)
MIN_OPEN_INTEREST = 150  # relaxed OI filter
MIN_ANNUAL_RETURN = 0.05  # 5% annualized
MIN_PREMIUM = 1.2
MAX_SPREAD = 1.25
MAX_SPREAD_PCT = 0.40
RELAXED_OPEN_INTEREST_FACTOR = 0.4
RELAXED_ANNUAL_RETURN_FACTOR = 0.7
RELAXED_MAX_SPREAD_FACTOR = 1.40
RELAXED_MAX_SPREAD_PCT_FACTOR = 1.25

# Contract sanity filters (avoid obviously broken strike/spot mappings)
MIN_STRIKE_TO_SPOT_RATIO = 0.40
MAX_STRIKE_TO_SPOT_RATIO = 2.50

# Volatility regime filter
VIX_TICKER = "^VIX"
VIX_MIN_LEVEL = 13.0   # below this: premium too thin
VIX_MAX_LEVEL = 35.0   # above this: assignment risk too high

# Earnings blackout / event window (days)
EARNINGS_BLACKOUT_DAYS = 7
EARNINGS_PLAY_WINDOW_DAYS = 7
ALLOW_EARNINGS_PLAYS = True
WEEKLY_PRIORITY_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "GOOGL",
    "TSLA",
    "AMD",
    "NFLX",
    "COIN",
    "PLTR",
]
EARNINGS_PLAY_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "GOOGL",
    "TSLA",
    "AMD",
    "NFLX",
    "COIN",
    "PLTR",
]

# Report
REPORT_DIR = "reports"
MASTER_REPORT_FILE = "options_premium_scan_all.md"
FINAL_SELECTION_LIMIT = 10
MAX_OPPS_PER_TICKER = 2
MIN_OPPS_PER_DIRECTION = 3
MAX_OTM_BUFFER_FOR_SCORING = 0.35
ROLL_PROFIT_CAPTURE_PCT = 0.75
ROLL_DTE_THRESHOLD = 7

# Scanner performance tuning
SCAN_MAX_WORKERS = 8
