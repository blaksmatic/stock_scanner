import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from config import FETCH_SLEEP_SECONDS, FETCH_WORKERS, OHLCV_DIR, OHLCV_HISTORY_YEARS

logger = logging.getLogger(__name__)


def _latest_expected_date() -> pd.Timestamp:
    """
    Return the latest date we'd expect to see in OHLCV data.

    - After market close (~5pm ET) on a weekday: today
    - Before market close on a weekday: previous business day
    - Weekend: Friday
    """
    from datetime import timezone, timedelta

    ET = timezone(timedelta(hours=-5))
    now_et = pd.Timestamp.now(tz=ET)
    today = now_et.normalize().tz_localize(None)
    weekday = today.weekday()

    if weekday == 5:       # Saturday → Friday
        return today - pd.Timedelta(days=1)
    elif weekday == 6:     # Sunday → Friday
        return today - pd.Timedelta(days=2)
    elif now_et.hour >= 17:  # After 5pm ET → today's candle is final
        return today
    else:                  # Before market close → previous business day
        if weekday == 0:   # Monday before close → Friday
            return today - pd.Timedelta(days=3)
        return today - pd.Timedelta(days=1)


def fetch_ohlcv(
    ticker: str, years: int = OHLCV_HISTORY_YEARS, force_full: bool = False
) -> pd.DataFrame:
    """
    Fetch daily OHLCV for a single ticker with incremental caching.

    Cache logic:
      - Compare last date in cached data against the latest trading day.
      - If cache already covers it → return cached data, no network call.
      - Otherwise → incremental fetch from last cached date onward.
      - No cache or force_full → full historical fetch.

    Returns:
        Combined DataFrame with DatetimeIndex and columns [Open, High, Low, Close, Volume].
    """
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = OHLCV_DIR / f"{ticker}.parquet"
    today = pd.Timestamp.now().normalize()
    latest_td = _latest_expected_date()

    if parquet_path.exists() and not force_full:
        cached_df = pd.read_parquet(parquet_path)

        if not cached_df.empty:
            last_date = cached_df.index.max().normalize()

            # Cache already has the latest trading day → fresh
            if last_date >= latest_td:
                return cached_df

            # Incremental fetch from day after last cached date
            start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = (today - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

        new_df = yf.Ticker(ticker).history(start=start, auto_adjust=True)
        if not new_df.empty:
            if new_df.index.tz is not None:
                new_df.index = new_df.index.tz_localize(None)
            combined = pd.concat([cached_df, new_df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined.sort_index(inplace=True)
            ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
            combined = combined[[c for c in ohlcv_cols if c in combined.columns]]
            combined.to_parquet(parquet_path)
            return combined
        return cached_df
    else:
        # Full fetch
        start = (today - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
        df = yf.Ticker(ticker).history(start=start, auto_adjust=True)
        if df.empty:
            logger.warning(f"No OHLCV data returned for {ticker}")
            return df
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        ohlcv_cols = ["Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in ohlcv_cols if c in df.columns]]
        df.to_parquet(parquet_path)
        return df


def _fetch_one(ticker: str, years: int, force_full: bool) -> tuple[str, bool, str]:
    """Wrapper for thread pool. Returns (ticker, success, error_msg)."""
    try:
        fetch_ohlcv(ticker, years=years, force_full=force_full)
        return (ticker, True, "")
    except Exception as e:
        return (ticker, False, str(e))


def fetch_all_ohlcv(
    tickers: list[str],
    years: int = OHLCV_HISTORY_YEARS,
    force_full: bool = False,
) -> list[str]:
    """
    Fetch OHLCV for all tickers using a thread pool with rate limiting.

    Returns:
        List of tickers that failed to fetch.
    """
    failed = []
    total = len(tickers)

    with tqdm(total=total, desc="Fetching OHLCV") as pbar:
        # Process in batches to allow rate-limit pauses
        for batch_start in range(0, total, FETCH_WORKERS):
            batch = tickers[batch_start : batch_start + FETCH_WORKERS]

            with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
                futures = {
                    executor.submit(_fetch_one, t, years, force_full): t
                    for t in batch
                }
                for future in as_completed(futures):
                    ticker, success, err = future.result()
                    if not success:
                        failed.append(ticker)
                        logger.warning(f"Failed {ticker}: {err}")
                    pbar.update(1)

            time.sleep(FETCH_SLEEP_SECONDS)

    if failed:
        logger.warning(f"{len(failed)} tickers failed: {failed[:20]}{'...' if len(failed) > 20 else ''}")
    return failed
