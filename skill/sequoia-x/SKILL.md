---
name: sequoia-x
description: A股量化选股系统 CLI 工具。用于查询A股股票K线数据、技术指标、策略选股、持仓分析和多股对比。当用户需要以下操作时使用：(1) 查看股票行情或K线数据 (2) 查看技术指标（MA、RSI、ATR、趋势等）(3) 运行选股策略（海龟突破、均线放量、RPS等7种策略）(4) 分析持仓股或观察股的操作建议 (5) 多股技术指标对比 (6) 管理关注列表。触发关键词：股价、行情、选股、策略、技术指标、K线、持仓、止损、止盈、A股、股票分析、MA、RSI、MACD。
---

# Sequoia-X CLI

A股量化选股系统。通过 `sequoia` 命令行工具使用，所有命令支持 `--format json` 输出结构化数据。

## 前置条件

需要本地有行情数据。首次使用需运行 `sequoia backfill`（约12分钟回填全市场历史数据），之后每个交易日收盘后运行 `sequoia sync` 增量更新。

## 命令速查

### 数据同步

```bash
sequoia backfill          # 首次：全市场历史K线回填（~12分钟）
sequoia sync              # 日常：增量同步最新行情（需16:00后运行）
sequoia sync --format json  # JSON输出：{"synced": 42}
```

### 单股查询

```bash
sequoia kline <symbol>              # 查看K线（默认最近30天）
sequoia kline 600519 -n 10          # 最近10天
sequoia kline 600519 --format json  # JSON输出：[{date,open,high,low,close,volume}, ...]

sequoia indicators <symbol>              # 技术指标（趋势、MA、RSI、ATR、量比等）
sequoia indicators 600519 --format json  # JSON输出：{symbol, trend, ma5, ma20, rsi, atr, ...}
```

### 多股对比

```bash
sequoia compare 600519 000858 601138              # 表格对比
sequoia compare 600519 000858 --format json       # JSON输出：{symbol: {trend, rsi, ...}}
```

### 策略选股

```bash
sequoia strategy list                   # 列出7种可用策略
sequoia strategy list --format json     # [{name, description}, ...]

sequoia strategy run <策略名>              # 运行单个策略
sequoia strategy run MaVolumeStrategy --format json
# JSON输出：{strategy, count, symbols}

sequoia scan --format json --no-email   # 运行全部策略（不同步、不发邮件）
# JSON输出：{strategies: {策略名: [symbols], ...}}
```

### 持仓分析

```bash
sequoia report --format json   # 分析watchlist，输出JSON（不发邮件）
sequoia analyze --format json  # 同上 + 发送邮件
```

JSON 输出格式：
```json
{
  "holdings": [{
    "symbol": "600703", "name": "三安光电",
    "current_price": 18.50, "trend": "多头",
    "recommendation": "HOLD", "reason": "趋势向好...",
    "stop_loss": 16.80, "take_profit_1": 20.20,
    "pnl_pct": 14.65
  }],
  "watchlist": [{
    "symbol": "002463", "name": "沪电股份",
    "recommendation": "WAIT", "reason": "偏离MA20...",
    "buy_zone_low": null, "buy_zone_high": null
  }]
}
```

### 关注列表

```bash
sequoia watchlist show --format json
```

## 7种选股策略

| 策略名 | 说明 | 适合场景 |
|---|---|---|
| `MaVolumeStrategy` | 均线放量突破 | MA5上穿MA20 + 量能放大 |
| `TurtleTradeStrategy` | 海龟突破 | 20日新高 + 成交额过亿 |
| `HighTightFlagStrategy` | 高窄旗形 | 40日涨60%后窄幅整理 |
| `LimitUpShakeoutStrategy` | 涨停洗盘 | 涨停后放量回踩确认 |
| `UptrendLimitDownStrategy` | 上升跌停 | 上升趋势中跌停反包 |
| `RpsBreakoutStrategy` | RPS突破 | 欧奈尔相对强度TOP10% |
| `PrivatePlacementStrategy` | 定增监控 | 近7天定增公告 |

## 推荐分析（recommendation）含义

**持仓股**：`HOLD`（持有）/ `SELL`（卖出）/ `TAKE_PROFIT`（分批止盈）
**观察股**：`BUY`（可买入，附买入区间）/ `WAIT`（等待）/ `AVOID`（回避）

## 典型工作流

1. 用户问"帮我看看 600519"→ `sequoia indicators 600519 --format json` + `sequoia kline 600519 -n 5 --format json`
2. 用户问"最近有什么好股票"→ `sequoia scan --format json --no-email`
3. 用户问"我的持仓怎么样"→ `sequoia report --format json`
4. 用户问"600519和000858哪个好"→ `sequoia compare 600519 000858 --format json`
5. 用户问"跑一下海龟策略"→ `sequoia strategy run TurtleTradeStrategy --format json`

## 数据说明

- 数据源：baostock（免费、无需注册）
- 复权方式：后复权
- 存储：本地 SQLite（`data/sequoia_v2.db`）
- 股票代码格式：纯6位数字，如 `600519`、`000858`
