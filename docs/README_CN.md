[English](../README.md) | 简体中文

# Stock Scanner - 美股扫描器

一个基于命令行的美股扫描工具，通过可插拔的技术分析算法寻找投资机会。数据来源于 Yahoo Finance，本地缓存为 Parquet 文件。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 快速开始

```bash
# 1. 获取股票池（市值 > 50亿美元的美股）
python main.py refresh-tickers

# 2. 拉取 OHLCV 行情数据 + 基本面数据
python main.py fetch-data

# 3. 运行扫描器
python main.py scan -s entry_point --top 20
```

## 命令说明

### `refresh-tickers`

从 Yahoo Finance 筛选器获取 NYSE + NASDAQ 市值超过 50 亿美元的所有美股，缓存至 `data/tickers.parquet`。

```bash
python main.py refresh-tickers
```

### `fetch-data`

拉取股票池中所有股票的日线 OHLCV 数据和基本面数据。

```bash
python main.py fetch-data                    # 拉取全部（默认 5 年历史数据）
python main.py fetch-data --years 3          # 3 年历史数据
python main.py fetch-data --full             # 强制全量重新下载
python main.py fetch-data -t AAPL -t MSFT    # 仅拉取指定股票
python main.py fetch-data --ohlcv-only       # 仅拉取行情，跳过基本面
python main.py fetch-data --fundamentals-only
```

**缓存机制**：OHLCV 数据按股票分别缓存为 Parquet 文件，后续运行仅增量拉取新数据。缓存会感知交易日——周末或盘前不会重复拉取。

### `scan`

运行扫描器分析缓存数据。默认会先更新 OHLCV 数据（如缓存已是最新则自动跳过）。

```bash
python main.py scan -s entry_point                      # 运行扫描器（自动更新数据）
python main.py scan -s entry_point --no-update           # 跳过数据更新
python main.py scan -s entry_point --top 20              # 仅显示前 20 个结果
python main.py scan -s entry_point --csv                 # 导出结果为 CSV
python main.py scan -s entry_point -t AAPL -t MSFT       # 扫描指定股票
python main.py scan -s ma_pullback -p pullback_pct=3     # 覆盖扫描器参数
```

### `list-scan`

列出所有可用的扫描器。

```bash
python main.py list-scan
```

## 扫描器

### `entry_point` -- 趋势入场点扫描器

寻找处于确认上升趋势中、且在日线 MA10/MA20 支撑位附近出现入场信号的股票。

**过滤条件：**
- 日线 MA10 > MA20 > MA50（日线趋势完好）
- 周线收盘价 > 周线 MA20（中期上升趋势）

**入场信号**（检查最近 3 根 K 线）：
- **HAMMER（锤子线）** -- 长下影线测试 MA10/MA20 后被拒（倒 T 型 / 蜻蜓十字星），最强信号。
- **TOUCH（触及）** -- K 线最低价触及 MA10/MA20，收盘价守住支撑。
- **APPROACHING（接近）** -- 价格向 MA10/MA20 支撑位靠拢。

**加分项：**
- 时效性：当日信号（ago=0）得满分，历史信号递减（0.7x, 0.4x）
- 接近历史新高：距 ATH 3% 以内（无上方阻力）最多 +25 分
- 周线完全排列、日线均线发散、阳线加分

**参数：** `d_fast`, `d_mid`, `d_slow`, `w_fast`, `w_mid`, `approach_pct`, `touch_pct`, `lookback`, `wick_body_ratio`, `upper_wick_max`

### `strong_pullback` -- 强势周线趋势 + 日线回踩

寻找周线趋势强劲（周线收盘 > wMA10 > wMA20 > wMA40）且日线回踩 MA10/MA20 后以阳线反弹的股票。

**参数：** `d_fast`, `d_mid`, `d_slow`, `w_fast`, `w_mid`, `w_slow`, `lookback_days`, `touch_pct`, `min_align_days`

### `ma_pullback` -- 均线排列 + 回踩

寻找日线 20/50/200 均线多头排列、且价格回踩至 20 均线 2% 以内的股票。

**参数：** `ma_short`, `ma_medium`, `ma_long`, `pullback_pct`, `min_trend_days`

## 添加新扫描器

在 `scanners/` 目录下创建文件即可，系统自动发现，无需修改其他文件。

```python
# scanners/my_scanner.py
from typing import Optional
import pandas as pd
from scanners.base import BaseScanner, ScanResult, resample_ohlcv
from scanners.registry import register

@register
class MyScanner(BaseScanner):
    name = "my_scanner"
    description = "在 list-scan 中显示的简短描述"

    def scan(self, ticker: str, ohlcv: pd.DataFrame, fundamentals: pd.Series) -> Optional[ScanResult]:
        # ohlcv: 日线 OHLCV，DatetimeIndex，列 [Open, High, Low, Close, Volume]
        # 用 resample_ohlcv(ohlcv, 'W') 转周线，'ME' 转月线

        close = ohlcv["Close"]
        # ... 你的逻辑 ...

        return ScanResult(
            ticker=ticker,
            score=75.0,         # 0-100
            signal="BUY",       # STRONG_BUY / BUY / WATCH
            details={"close": round(close.iloc[-1], 2)},
        )
```

然后运行：`python main.py scan -s my_scanner`

## 项目结构

```
main.py                 CLI 入口
config.py               路径与常量配置
requirements.txt        Python 依赖
tickers/
  universe.py           通过 yfinance 筛选器获取股票池
data/
  ohlcv_cache.py        按股票缓存 Parquet，增量拉取
  fundamentals_cache.py 基本面缓存（单文件，每日刷新）
scanners/
  base.py               BaseScanner 抽象类、ScanResult、resample_ohlcv 工具函数
  registry.py           通过 @register 装饰器自动发现扫描器
  ma_pullback.py        均线排列 + 回踩扫描器
  strong_pullback.py    强势周线趋势 + 日线反弹扫描器
  entry_point.py        趋势入场点扫描器（触及/锤子线识别）
output/
  formatter.py          Rich 终端表格 + CSV 导出
```

## 数据存储

所有数据缓存在 `data/` 目录下：

- `data/tickers.parquet` -- 股票池
- `data/ohlcv/{TICKER}.parquet` -- 每只股票的日线 OHLCV
- `data/fundamentals.parquet` -- 所有股票的基本面数据
- `output_results/` -- `--csv` 导出的扫描结果
