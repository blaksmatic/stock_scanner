# Stock Scanner

A CLI tool for scanning US stocks to find investment opportunities using pluggable algorithm-based scanners. Data sourced from Yahoo Finance, cached locally as Parquet files.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

```bash
# 1. Build the ticker universe (US stocks with market cap > $5B)
python main.py refresh-tickers

# 2. Fetch OHLCV + fundamentals data
python main.py fetch-data

# 3. Run a scanner
python main.py scan -s entry_point --top 20
```

## Commands

### `refresh-tickers`

Fetches all US equities (NYSE + NASDAQ) with market cap > $5B using the Yahoo Finance screener. Results cached to `data/tickers.parquet`.

```bash
python main.py refresh-tickers
```

### `fetch-data`

Fetches daily OHLCV price history and fundamental data for all tickers in the universe.

```bash
python main.py fetch-data                    # Fetch all (default 5 years of history)
python main.py fetch-data --years 3          # 3 years of history
python main.py fetch-data --full             # Force full re-download
python main.py fetch-data -t AAPL -t MSFT    # Specific tickers only
python main.py fetch-data --ohlcv-only       # Skip fundamentals
python main.py fetch-data --fundamentals-only
```

**Caching**: OHLCV data is cached per-ticker as Parquet files. Subsequent runs only fetch new data since the last cached date. The cache is aware of trading days -- it won't re-fetch on weekends or before market close if data is already current.

### `scan`

Runs a scanner against cached data. By default, updates OHLCV data before scanning (skips automatically if cache is fresh).

```bash
python main.py scan -s entry_point                      # Run scanner (auto-updates data)
python main.py scan -s entry_point --no-update           # Skip data update
python main.py scan -s entry_point --top 20              # Show top 20 results
python main.py scan -s entry_point --csv                 # Export results to CSV
python main.py scan -s entry_point -t AAPL -t MSFT       # Scan specific tickers
python main.py scan -s ma_pullback -p pullback_pct=3     # Override scanner parameters
```

### `list-scan`

Lists all available scanners.

```bash
python main.py list-scan
```

## Scanners

### `entry_point` -- Trend Entry Scanner

Finds stocks in a confirmed uptrend that are at an actionable entry point near daily MA10/MA20 support.

**Filters:**
- Daily MA10 > MA20 > MA50 (daily trend intact)
- Weekly close > weekly MA20 (intermediate uptrend)

**Entry signals** (checked over the last 3 candles):
- **HAMMER** -- Long lower wick tested MA10/MA20 and got rejected (reversed T / dragonfly doji). Strongest signal.
- **TOUCH** -- Candle low reached MA10/MA20, close held above.
- **APPROACHING** -- Price drifting toward MA10/MA20 support.

**Scoring bonuses:**
- Recency: today's signal (ago=0) scores full points; older signals decay (0.7x, 0.4x)
- Near ATH: stocks within 3% of all-time high (no overhead resistance) get up to +25 bonus points
- Weekly alignment, daily MA spread, green candle

**Parameters:** `d_fast`, `d_mid`, `d_slow`, `w_fast`, `w_mid`, `approach_pct`, `touch_pct`, `lookback`, `wick_body_ratio`, `upper_wick_max`

### `strong_pullback` -- Strong Weekly Trend + Daily Bounce

Finds stocks with a strong weekly trend (weekly close > wMA10 > wMA20 > wMA40) that have pulled back to daily MA10/MA20 and bounced with a green candle.

**Parameters:** `d_fast`, `d_mid`, `d_slow`, `w_fast`, `w_mid`, `w_slow`, `lookback_days`, `touch_pct`, `min_align_days`

### `ma_pullback` -- MA Alignment + Pullback

Finds stocks where daily 20/50/200 SMAs are aligned bullishly and price has pulled back within 2% of the 20 SMA.

**Parameters:** `ma_short`, `ma_medium`, `ma_long`, `pullback_pct`, `min_trend_days`

## Adding a New Scanner

Create a file in `scanners/` -- it's auto-discovered, no other files need changes.

```python
# scanners/my_scanner.py
from typing import Optional
import pandas as pd
from scanners.base import BaseScanner, ScanResult, resample_ohlcv
from scanners.registry import register

@register
class MyScanner(BaseScanner):
    name = "my_scanner"
    description = "Short description shown in list-scan"

    def scan(self, ticker: str, ohlcv: pd.DataFrame, fundamentals: pd.Series) -> Optional[ScanResult]:
        # ohlcv: daily OHLCV with DatetimeIndex [Open, High, Low, Close, Volume]
        # Use resample_ohlcv(ohlcv, 'W') for weekly, 'ME' for monthly

        close = ohlcv["Close"]
        # ... your logic ...

        return ScanResult(
            ticker=ticker,
            score=75.0,         # 0-100
            signal="BUY",       # STRONG_BUY / BUY / WATCH
            details={"close": round(close.iloc[-1], 2)},
        )
```

Then run: `python main.py scan -s my_scanner`

## Project Structure

```
main.py                 CLI entry point
config.py               Paths and constants
requirements.txt        Python dependencies
tickers/
  universe.py           Ticker universe fetch via yfinance screener
data/
  ohlcv_cache.py        Per-ticker Parquet cache with incremental fetch
  fundamentals_cache.py Fundamentals cache (single Parquet, daily refresh)
scanners/
  base.py               BaseScanner ABC, ScanResult, resample_ohlcv helper
  registry.py           Auto-discovery via @register decorator
  ma_pullback.py        MA alignment + pullback scanner
  strong_pullback.py    Strong weekly trend + daily bounce scanner
  entry_point.py        Trend entry point scanner (touch/hammer at MA)
output/
  formatter.py          Rich console table + CSV export
```

## Data Storage

All data is cached locally under `data/`:

- `data/tickers.parquet` -- Ticker universe
- `data/ohlcv/{TICKER}.parquet` -- Daily OHLCV per ticker
- `data/fundamentals.parquet` -- Fundamentals for all tickers
- `output_results/` -- CSV exports from `--csv` flag
