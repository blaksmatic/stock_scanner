import logging

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import FUNDAMENTALS_PATH

logger = logging.getLogger(__name__)

FUNDAMENTAL_FIELDS = [
    "marketCap",
    "sharesOutstanding",
    "sector",
    "industry",
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "dividendYield",
    "returnOnEquity",
    "revenueGrowth",
    "earningsGrowth",
    "debtToEquity",
    "currentRatio",
    "operatingMargins",
    "shortName",
    "exchange",
]


def fetch_fundamentals(
    tickers: list[str], use_cache: bool = True
) -> pd.DataFrame:
    """
    Fetch fundamental data for all tickers.

    Caches to a single Parquet file. If fetched today and use_cache=True,
    returns the cached version.

    Returns:
        DataFrame indexed by ticker with fundamental fields as columns.
    """
    today = pd.Timestamp.today().normalize()

    cached = None
    if FUNDAMENTALS_PATH.exists():
        cached = pd.read_parquet(FUNDAMENTALS_PATH)

    # Figure out which tickers we actually need to fetch
    to_fetch = tickers
    if use_cache and cached is not None and "_fetched_date" in cached.columns:
        # Only skip tickers that were already fetched today
        fresh = cached[cached["_fetched_date"] == today]
        already_have = set(fresh.index)
        to_fetch = [t for t in tickers if t not in already_have]
        if not to_fetch:
            logger.info("Fundamentals already fetched today for all requested tickers.")
            return cached

    logger.info(f"Fetching fundamentals for {len(to_fetch)} tickers ({len(tickers) - len(to_fetch)} cached)...")
    rows = []
    for ticker in tqdm(to_fetch, desc="Fetching fundamentals"):
        try:
            info = yf.Ticker(ticker).info
            row = {field: info.get(field) for field in FUNDAMENTAL_FIELDS}
            row["ticker"] = ticker
            row["_fetched_date"] = today
            rows.append(row)
        except Exception as e:
            logger.warning(f"Failed to fetch fundamentals for {ticker}: {e}")
            rows.append({"ticker": ticker, "_fetched_date": today})

    new_df = pd.DataFrame(rows).set_index("ticker")

    # Merge with existing cache: update existing rows, add new ones
    if cached is not None:
        cached.update(new_df)
        new_tickers = new_df.index.difference(cached.index)
        if len(new_tickers):
            cached = pd.concat([cached, new_df.loc[new_tickers]])
        df = cached
    else:
        df = new_df

    FUNDAMENTALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FUNDAMENTALS_PATH)
    logger.info(f"Saved fundamentals for {len(df)} tickers to {FUNDAMENTALS_PATH}")
    return df
