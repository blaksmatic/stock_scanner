import csv
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from scanners.base import ScanResult

SIGNAL_COLORS = {
    "STRONG_BUY": "bold green",
    "BUY": "yellow",
    "WATCH": "white",
}


def print_results(results: list[ScanResult], scanner_name: str):
    """Print scan results as a Rich console table."""
    console = Console()

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

    table = Table(
        title=f"Scanner: {scanner_name} | {datetime.now():%Y-%m-%d %H:%M}",
        show_lines=False,
        expand=True,
    )
    table.add_column("#", style="dim", width=3, no_wrap=True)
    table.add_column("Ticker", style="bold cyan", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("Score", justify="right", no_wrap=True)

    # Dynamic columns from details
    detail_keys = list(sorted_results[0].details.keys())
    for key in detail_keys:
        table.add_column(key, justify="right", no_wrap=True, overflow="ellipsis")

    for i, r in enumerate(sorted_results, 1):
        color = SIGNAL_COLORS.get(r.signal, "white")
        row = [
            str(i),
            r.ticker,
            f"[{color}]{r.signal}[/{color}]",
            f"{r.score:.1f}",
        ]
        row.extend(str(r.details.get(k, "")) for k in detail_keys)
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]{len(sorted_results)} results found.[/dim]")


def export_csv(
    results: list[ScanResult], scanner_name: str, output_dir: Path
) -> Path:
    """Export scan results to a timestamped CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"{scanner_name}_{datetime.now():%Y%m%d_%H%M%S}.csv"

    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

    fieldnames = ["rank", "ticker", "signal", "score"]
    if sorted_results:
        fieldnames.extend(sorted_results[0].details.keys())

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(sorted_results, 1):
            row = {"rank": i, "ticker": r.ticker, "signal": r.signal, "score": r.score}
            row.update(r.details)
            writer.writerow(row)

    return filename
