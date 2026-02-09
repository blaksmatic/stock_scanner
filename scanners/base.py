from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class ScanResult:
    """Result of a scanner evaluating a single ticker."""

    ticker: str
    score: float
    signal: str  # e.g. "BUY", "WATCH", "STRONG_BUY"
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        self.score = max(0.0, min(100.0, self.score))


class BaseScanner(ABC):
    """Base class for all scanners."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in CLI --scanner flag."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for help text."""
        ...

    @abstractmethod
    def scan(
        self,
        ticker: str,
        ohlcv: pd.DataFrame,
        fundamentals: pd.Series,
    ) -> Optional[ScanResult]:
        """
        Evaluate a single ticker.

        Args:
            ticker: The stock symbol.
            ohlcv: DataFrame with columns [Open, High, Low, Close, Volume],
                   DatetimeIndex, sorted ascending. Always daily frequency.
            fundamentals: Series with fundamental data for this ticker.

        Returns:
            ScanResult if the ticker passes the scan, None otherwise.
        """
        ...

    def configure(self, **kwargs) -> None:
        """Accept runtime parameters from CLI --param key=value flags."""
        pass


def resample_ohlcv(daily_df: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """
    Resample daily OHLCV to a lower frequency.

    Args:
        daily_df: Daily OHLCV DataFrame with DatetimeIndex.
        freq: Pandas frequency string. Common values:
              'W'  - weekly
              'ME' - month-end
              'QE' - quarter-end

    Returns:
        Resampled OHLCV DataFrame.
    """
    return (
        daily_df.resample(freq)
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    )
