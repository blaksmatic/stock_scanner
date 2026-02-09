import logging
import sys

import click
import pandas as pd

from config import FUNDAMENTALS_PATH, OHLCV_DIR, OHLCV_HISTORY_YEARS, OUTPUT_DIR
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Stock Scanner CLI - scan US stocks for investment opportunities."""
    pass


@cli.command("refresh-tickers")
def refresh_tickers():
    """Refresh the ticker universe from Yahoo Finance screener."""
    from tickers.universe import fetch_universe

    click.echo("Fetching US equities with market cap > $5B from NYSE + NASDAQ...")
    df = fetch_universe()
    click.echo(f"Found {len(df)} tickers.")


@cli.command("fetch-data")
@click.option("--years", type=int, default=OHLCV_HISTORY_YEARS, show_default=True, help="Years of OHLCV history to fetch.")
@click.option("--full", is_flag=True, help="Force full re-download, ignoring cache.")
@click.option("--ticker", "-t", multiple=True, help="Fetch specific ticker(s) only.")
@click.option("--fundamentals-only", is_flag=True, help="Only refresh fundamentals.")
@click.option("--ohlcv-only", is_flag=True, help="Only refresh OHLCV data.")
def fetch_data(years, full, ticker, fundamentals_only, ohlcv_only):
    """Fetch/update OHLCV and fundamentals data."""
    from data.fundamentals_cache import fetch_fundamentals
    from data.ohlcv_cache import fetch_all_ohlcv
    from tickers.universe import load_universe

    if ticker:
        tickers = list(ticker)
    else:
        tickers = load_universe()["symbol"].tolist()

    if not fundamentals_only:
        click.echo(f"Fetching OHLCV for {len(tickers)} tickers ({years}yr history)...")
        failed = fetch_all_ohlcv(tickers, years=years, force_full=full)
        if failed:
            click.echo(f"  {len(failed)} tickers failed.")

    if not ohlcv_only:
        click.echo(f"Fetching fundamentals for {len(tickers)} tickers...")
        fetch_fundamentals(tickers, use_cache=not full)

    click.echo("Done.")


@cli.command("scan")
@click.option("--scanner", "-s", required=True, help="Scanner name to run.")
@click.option("--csv", "export_csv", is_flag=True, help="Export results to CSV.")
@click.option("--top", type=int, default=None, help="Show only top N results.")
@click.option("--param", "-p", multiple=True, help="Scanner param as key=value.")
@click.option("--ticker", "-t", multiple=True, help="Scan specific ticker(s) instead of universe.")
@click.option("--no-update", is_flag=True, help="Skip data refresh, use cached data only.")
def scan(scanner, export_csv, top, param, ticker, no_update):
    """Run a scanner against cached data. Updates OHLCV data first by default."""
    from scanners.registry import auto_discover, get_scanner
    from output.formatter import print_results, export_csv as do_export_csv
    from data.ohlcv_cache import fetch_all_ohlcv
    from tickers.universe import load_universe

    auto_discover()
    scanner_obj = get_scanner(scanner)

    if param:
        params = dict(p.split("=", 1) for p in param)
        scanner_obj.configure(**params)

    if ticker:
        symbols = list(ticker)
    else:
        tickers_df = load_universe()
        symbols = tickers_df["symbol"].tolist()

    if not no_update:
        click.echo(f"Updating OHLCV for {len(symbols)} tickers...")
        failed = fetch_all_ohlcv(symbols)
        if failed:
            click.echo(f"  {len(failed)} tickers failed to update.")

    fundamentals_df = None
    if FUNDAMENTALS_PATH.exists():
        fundamentals_df = pd.read_parquet(FUNDAMENTALS_PATH)

    results = []
    skipped = 0
    for sym in tqdm(symbols, desc=f"Scanning [{scanner}]"):
        ohlcv_path = OHLCV_DIR / f"{sym}.parquet"
        if not ohlcv_path.exists():
            skipped += 1
            continue

        ohlcv = pd.read_parquet(ohlcv_path)
        if fundamentals_df is not None and sym in fundamentals_df.index:
            fund = fundamentals_df.loc[sym]
        else:
            fund = pd.Series()

        result = scanner_obj.scan(sym, ohlcv, fund)
        if result is not None:
            results.append(result)

    if skipped:
        click.echo(f"  Skipped {skipped} tickers (no OHLCV cache).")

    if top:
        results = sorted(results, key=lambda r: r.score, reverse=True)[:top]

    if results:
        print_results(results, scanner)
        if export_csv:
            path = do_export_csv(results, scanner, OUTPUT_DIR)
            click.echo(f"CSV exported to {path}")
    else:
        click.echo("No results matched the scanner criteria.")


@cli.command("list-scan")
def list_scan():
    """List all available scanners."""
    from scanners.registry import auto_discover, list_scanners

    auto_discover()
    scanners = list_scanners()
    if not scanners:
        click.echo("No scanners found.")
        return
    for name, desc in scanners.items():
        click.echo(f"  {name:20s}  {desc}")


if __name__ == "__main__":
    cli()
