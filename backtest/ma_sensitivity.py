import logging
from typing import Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy functions
# ---------------------------------------------------------------------------
# Each strategy takes (ohlcv, touch_idx, hold_days) and returns a float
# representing the trade return in %. None = skip (not enough forward data).

def _bounce_return(ohlcv: pd.DataFrame, touch_idx: int, hold_days: int) -> Optional[float]:
    """Simple bounce: return % from touch-day close to close N days later."""
    exit_idx = touch_idx + hold_days
    if exit_idx >= len(ohlcv):
        return None
    entry_price = ohlcv["Close"].iloc[touch_idx]
    exit_price = ohlcv["Close"].iloc[exit_idx]
    return (exit_price - entry_price) / entry_price * 100


def _bounce_max_return(ohlcv: pd.DataFrame, touch_idx: int, hold_days: int) -> Optional[float]:
    """Best possible return within the hold window (high watermark)."""
    exit_idx = touch_idx + hold_days
    if exit_idx >= len(ohlcv):
        return None
    entry_price = ohlcv["Close"].iloc[touch_idx]
    max_high = ohlcv["High"].iloc[touch_idx + 1 : exit_idx + 1].max()
    return (max_high - entry_price) / entry_price * 100


STRATEGIES: Dict[str, Callable] = {
    "bounce": _bounce_return,
    "max_return": _bounce_max_return,
}


# ---------------------------------------------------------------------------
# Core backtest
# ---------------------------------------------------------------------------

def backtest_ma_sensitivity(
    ohlcv: pd.DataFrame,
    ma_periods: tuple = (10, 20),
    trend_ma: int = 50,
    touch_pct: float = 1.0,
    hold_days: int = 5,
    cooldown: int = 3,
    strategy: str = "bounce",
) -> dict:
    """
    Walk through OHLCV history, find all MA touch events where the trend
    was aligned, and measure bounce success using the given strategy.

    Args:
        ohlcv: Daily OHLCV DataFrame.
        ma_periods: Which MAs to test touches against (default MA10, MA20).
        trend_ma: Slow MA for trend alignment check.
        touch_pct: Low must come within this % of an MA to count as touch.
        hold_days: How many days to hold after a touch to measure return.
        cooldown: Minimum days between counted touches (avoid double-counting).
        strategy: Name of the strategy function to use.

    Returns:
        Dict with win_rate, avg_return, per-MA breakdowns, and backtest_score.
    """
    strategy_fn = STRATEGIES.get(strategy, _bounce_return)

    min_period = max(max(ma_periods), trend_ma)
    if len(ohlcv) < min_period + 50:
        return _empty_result(ma_periods)

    close = ohlcv["Close"]
    low = ohlcv["Low"]

    # Compute MAs
    mas = {p: close.rolling(p).mean() for p in ma_periods}
    trend = close.rolling(trend_ma).mean()

    # Walk through history
    touches: List[dict] = []
    last_touch_idx = -cooldown - 1  # allow first touch

    start_idx = min_period + 10  # enough MA warmup
    end_idx = len(ohlcv) - hold_days  # need forward data

    for i in range(start_idx, end_idx):
        # Cooldown check
        if i - last_touch_idx < cooldown:
            continue

        # Trend alignment: all shorter MAs > trend MA
        sorted_periods = sorted(ma_periods)
        ma_values = [mas[p].iloc[i] for p in sorted_periods]
        trend_val = trend.iloc[i]

        # Check ascending alignment: MA10 > MA20 > ... > trend_MA
        aligned = all(ma_values[j] > ma_values[j + 1] for j in range(len(ma_values) - 1))
        aligned = aligned and ma_values[-1] > trend_val
        if not aligned:
            continue

        # Check for MA touch
        low_val = low.iloc[i]
        for p in sorted_periods:
            ma_val = mas[p].iloc[i]
            dist_pct = (low_val - ma_val) / ma_val * 100

            # Touch = low within touch_pct% (above or below)
            if abs(dist_pct) <= touch_pct or dist_pct <= 0:
                ret = strategy_fn(ohlcv, i, hold_days)
                if ret is not None:
                    touches.append({
                        "idx": i,
                        "ma_period": p,
                        "return_pct": ret,
                        "win": ret > 0,
                    })
                    last_touch_idx = i
                break  # count once per day (prefer faster MA)

    return _compute_metrics(touches, ma_periods)


def _empty_result(ma_periods: tuple) -> dict:
    result = {
        "win_rate": 0.0,
        "avg_return": 0.0,
        "total_touches": 0,
        "backtest_score": 0.0,
    }
    for p in ma_periods:
        result[f"ma{p}_win_rate"] = 0.0
        result[f"ma{p}_touches"] = 0
    return result


def _compute_metrics(touches: List[dict], ma_periods: tuple) -> dict:
    if not touches:
        return _empty_result(ma_periods)

    wins = sum(1 for t in touches if t["win"])
    returns = [t["return_pct"] for t in touches]
    total = len(touches)

    win_rate = wins / total * 100
    avg_return = sum(returns) / total

    result = {
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 2),
        "total_touches": total,
    }

    # Per-MA breakdown
    for p in ma_periods:
        ma_touches = [t for t in touches if t["ma_period"] == p]
        if ma_touches:
            ma_wins = sum(1 for t in ma_touches if t["win"])
            result[f"ma{p}_win_rate"] = round(ma_wins / len(ma_touches) * 100, 1)
            result[f"ma{p}_touches"] = len(ma_touches)
        else:
            result[f"ma{p}_win_rate"] = 0.0
            result[f"ma{p}_touches"] = 0

    # Backtest score: weighted combo of win_rate and avg_return
    # Win rate component: 50% of score (60% win rate = 30pts, 80% = 50pts)
    wr_score = min(50, max(0, (win_rate - 40) / 40 * 50))
    # Return component: 50% of score (1% avg return = 25pts, 2% = 50pts)
    ret_score = min(50, max(0, avg_return / 2 * 50))
    # Sample size penalty: fewer than 10 touches reduces confidence
    confidence = min(1.0, total / 10)

    result["backtest_score"] = round((wr_score + ret_score) * confidence, 1)

    return result


def list_strategies() -> Dict[str, str]:
    """Return available strategy names and descriptions."""
    return {
        "bounce": "Return % from touch-day close to close after N hold days",
        "max_return": "Best possible return (high watermark) within hold window",
    }
