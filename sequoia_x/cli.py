"""Sequoia-X CLI: Typer-based command-line interface for A-share stock selection."""

from __future__ import annotations

import dataclasses
import socket
import sys
from datetime import date
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()
socket.setdefaulttimeout(10.0)

app = typer.Typer(
    name="sequoia",
    help="Sequoia-X V2: A股量化选股系统",
    no_args_is_help=True,
)

strategy_app = typer.Typer(help="策略管理")
app.add_typer(strategy_app, name="strategy")

watchlist_app = typer.Typer(help="关注列表")
app.add_typer(watchlist_app, name="watchlist")


# ── Shared helpers ──

FormatOption = typer.Option("rich", "--format", help="输出格式: json 或 rich")


def _get_deps():
    """Lazy init: returns (engine, settings, logger)."""
    from sequoia_x.core.config import get_settings
    from sequoia_x.core.logger import get_logger
    from sequoia_x.data.engine import DataEngine

    settings = get_settings()
    engine = DataEngine(settings)
    logger = get_logger(__name__)
    return engine, settings, logger


# Strategy registry: name → (class, description)
_STRATEGY_MAP: dict[str, tuple[type, str]] = {}


def _build_strategy_map() -> dict[str, tuple[type, str]]:
    """Import strategies lazily and build the name→(class, desc) map."""
    if _STRATEGY_MAP:
        return _STRATEGY_MAP
    from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
    from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
    from sequoia_x.strategy.ma_volume import MaVolumeStrategy
    from sequoia_x.strategy.private_placement import PrivatePlacementStrategy
    from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
    from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
    from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy

    entries = [
        (MaVolumeStrategy, "均线放量突破"),
        (TurtleTradeStrategy, "海龟突破"),
        (HighTightFlagStrategy, "高窄旗形突破"),
        (LimitUpShakeoutStrategy, "涨停洗盘回踩"),
        (UptrendLimitDownStrategy, "上升跌停反包"),
        (RpsBreakoutStrategy, "RPS 相对强度突破"),
        (PrivatePlacementStrategy, "定增公告监控"),
    ]
    for cls, desc in entries:
        _STRATEGY_MAP[cls.__name__] = (cls, desc)
    return _STRATEGY_MAP


def _instantiate_strategies(engine, settings) -> list:
    """Create instances of all strategies."""
    result = []
    for cls, _ in _build_strategy_map().values():
        result.append(cls(engine=engine, settings=settings))
    return result


def _run_all_strategies(engine, settings) -> dict[str, list[str]]:
    """Run all strategies and return {name: [symbols]}."""
    results: dict[str, list[str]] = {}
    for strategy in _instantiate_strategies(engine, settings):
        name = type(strategy).__name__
        selected = strategy.run()
        if selected:
            results[name] = selected
    return results


# ══════════════════════════════════════════════════
# Phase 1: Core commands (from existing main.py)
# ══════════════════════════════════════════════════


@app.command()
def daily(
    format: str = FormatOption,
    no_email: bool = typer.Option(False, "--no-email", help="跳过邮件推送"),
) -> None:
    """日常模式：同步数据 + 跑策略 + 邮件推送"""
    engine, settings, logger = _get_deps()

    logger.info("开始拉取最新快照...")
    count = engine.sync_today_bulk()
    logger.info(f"快照同步完成，写入 {count} 只股票")

    logger.info("开始执行策略...")
    results = _run_all_strategies(engine, settings)

    for name, symbols in results.items():
        logger.info(f"{name} 选出 {len(symbols)} 只股票")

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({"synced": count, "strategies": results})
    else:
        rows = [[name, str(len(symbols)), ", ".join(symbols[:10])] for name, symbols in results.items()]
        rows.append(["同步", str(count), "—"])
        render_rich_table("Sequoia-X 日常运行结果", ["策略", "数量", "股票"], rows)

    if not no_email and results:
        from sequoia_x.notify.email import EmailNotifier

        notifier = EmailNotifier(settings)
        notifier.send_all(results)


@app.command()
def sync(
    format: str = FormatOption,
) -> None:
    """仅同步模式：拉取最新行情数据"""
    engine, settings, logger = _get_deps()

    logger.info("开始拉取最新快照...")
    count = engine.sync_today_bulk()
    logger.info(f"快照同步完成，写入 {count} 只股票")

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({"synced": count})
    else:
        render_rich_table("同步结果", ["更新股票数"], [[str(count)]])


@app.command()
def backfill(
    format: str = FormatOption,
) -> None:
    """回填模式：全市场历史K线数据"""
    engine, settings, logger = _get_deps()

    logger.info("进入回填模式...")
    all_symbols = engine.get_all_symbols()
    engine.backfill(all_symbols)

    from sequoia_x.output import render_json

    if format == "json":
        render_json({"status": "done", "symbols_requested": len(all_symbols)})
    # rich mode: logger already printed progress


@app.command()
def scan(
    format: str = FormatOption,
    no_email: bool = typer.Option(False, "--no-email", help="跳过邮件推送"),
) -> None:
    """扫描模式：运行所有策略（不同步数据）"""
    engine, settings, logger = _get_deps()

    results = _run_all_strategies(engine, settings)

    for name, symbols in results.items():
        logger.info(f"{name} 选出 {len(symbols)} 只股票")

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({"strategies": results})
    else:
        rows = [[name, str(len(symbols)), ", ".join(symbols[:10])] for name, symbols in results.items()]
        render_rich_table("策略扫描结果", ["策略", "数量", "股票"], rows)

    if not no_email and results:
        from sequoia_x.notify.email import EmailNotifier

        notifier = EmailNotifier(settings)
        notifier.send_all(results)


@app.command()
def analyze(
    format: str = FormatOption,
    no_email: bool = typer.Option(False, "--no-email", help="跳过邮件推送"),
) -> None:
    """个股分析模式：分析 watchlist 中的持仓和观察股"""
    engine, settings, logger = _get_deps()

    from sequoia_x.analysis.advisor import run_analysis
    from sequoia_x.analysis.watchlist import load_watchlist

    wl = load_watchlist(settings.watchlist_path)
    if not wl.holdings and not wl.watchlist:
        logger.info("关注列表为空，跳过分析")
        from sequoia_x.output import render_json

        if format == "json":
            render_json({"holdings": [], "watchlist": []})
        return

    holdings_results, watchlist_results = run_analysis(engine, wl)
    total = len(holdings_results) + len(watchlist_results)

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({
            "holdings": [dataclasses.asdict(r) for r in holdings_results],
            "watchlist": [dataclasses.asdict(r) for r in watchlist_results],
        })
    else:
        _render_analysis_tables(holdings_results, watchlist_results)

    if not no_email:
        from sequoia_x.analysis.report import build_analysis_email
        from sequoia_x.notify.mail_send import find_mail_send, run_mail_send

        html = build_analysis_email(holdings_results, watchlist_results)
        exe = find_mail_send()
        subject = f"Sequoia-X 个股分析 | {date.today()} | {total} 只"
        run_mail_send(exe, settings.mail_to, subject, html)
        logger.info(f"个股分析邮件推送成功，共 {total} 只股票")


@app.command()
def report(
    format: str = FormatOption,
) -> None:
    """报告模式：分析 watchlist 并展示结果（不发邮件）"""
    engine, settings, logger = _get_deps()

    from sequoia_x.analysis.advisor import run_analysis
    from sequoia_x.analysis.watchlist import load_watchlist

    wl = load_watchlist(settings.watchlist_path)
    if not wl.holdings and not wl.watchlist:
        from sequoia_x.output import render_json

        if format == "json":
            render_json({"holdings": [], "watchlist": []})
        return

    holdings_results, watchlist_results = run_analysis(engine, wl)

    from sequoia_x.output import render_json

    if format == "json":
        render_json({
            "holdings": [dataclasses.asdict(r) for r in holdings_results],
            "watchlist": [dataclasses.asdict(r) for r in watchlist_results],
        })
    else:
        _render_analysis_tables(holdings_results, watchlist_results)


def _render_analysis_tables(holdings_results, watchlist_results) -> None:
    """Render analysis results as Rich tables."""
    from sequoia_x.output import render_rich_table

    if holdings_results:
        rows = []
        for r in holdings_results:
            pnl = f"{r.pnl_pct:+.2f}%" if r.pnl_pct is not None else "—"
            rows.append([
                f"{r.symbol} {r.name}", r.trend, r.recommendation,
                f"{r.current_price:.2f}", pnl,
                f"{r.stop_loss:.2f}" if r.stop_loss else "—",
            ])
        render_rich_table("持仓分析", ["股票", "趋势", "建议", "现价", "盈亏%", "止损"], rows)

    if watchlist_results:
        rows = []
        for r in watchlist_results:
            buy_zone = f"{r.buy_zone_low:.2f}-{r.buy_zone_high:.2f}" if r.buy_zone_low else "—"
            rows.append([
                f"{r.symbol} {r.name}", r.trend, r.recommendation,
                f"{r.current_price:.2f}", buy_zone, r.reason[:40],
            ])
        render_rich_table("观察股分析", ["股票", "趋势", "建议", "现价", "买入区间", "理由"], rows)


# ══════════════════════════════════════════════════
# Phase 2: On-demand query commands
# ══════════════════════════════════════════════════


@app.command()
def kline(
    symbol: str = typer.Argument(..., help="股票代码，如 600519"),
    limit: int = typer.Option(30, "--limit", "-n", help="返回条数"),
    format: str = FormatOption,
) -> None:
    """查看股票K线数据"""
    engine, _, _ = _get_deps()
    df = engine.get_ohlcv(symbol)

    if df.empty:
        typer.echo(f"未找到 {symbol} 的数据，请先 sequoia sync 或 sequoia backfill", err=True)
        raise typer.Exit(1)

    df = df.tail(limit)

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json(df.to_dict(orient="records"))
    else:
        rows = []
        for _, r in df.iterrows():
            rows.append([
                str(r["date"]),
                f"{r['open']:.2f}", f"{r['high']:.2f}",
                f"{r['low']:.2f}", f"{r['close']:.2f}",
                f"{r['volume']:.0f}",
            ])
        render_rich_table(
            f"K线: {symbol}（最近 {limit} 天）",
            ["日期", "开盘", "最高", "最低", "收盘", "成交量"],
            rows,
        )


@app.command()
def indicators(
    symbol: str = typer.Argument(..., help="股票代码，如 600519"),
    format: str = FormatOption,
) -> None:
    """查看股票技术指标"""
    engine, _, _ = _get_deps()
    df = engine.get_ohlcv(symbol)

    if df.empty:
        typer.echo(f"未找到 {symbol} 的数据", err=True)
        raise typer.Exit(1)

    from sequoia_x.analysis.indicators import compute_indicators

    ind = compute_indicators(df)
    if ind is None:
        typer.echo(f"{symbol} 数据不足（需要 20+ 条记录）", err=True)
        raise typer.Exit(1)

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({"symbol": symbol, **ind})
    else:
        rows = [
            ["趋势", ind["trend"]],
            ["当前价", f"{ind['current_price']:.2f}"],
            ["MA5", f"{ind['ma5']:.2f}"],
            ["MA10", f"{ind['ma10']:.2f}"],
            ["MA20", f"{ind['ma20']:.2f}"],
            ["MA60", f"{ind['ma60']:.2f}" if ind.get("ma60") else "—"],
            ["RSI(14)", f"{ind['rsi']:.1f}"],
            ["ATR(14)", f"{ind['atr']:.2f}"],
            ["量比", f"{ind['volume_ratio']:.2f}"],
            ["量能趋势", ind["vol_trend"]],
            ["近支撑", f"{ind['support_near']:.2f}"],
        ]
        for k, v in ind.get("price_vs_mas", {}).items():
            rows.append([f"偏离{k.upper()}", f"{v:+.1f}%"])
        render_rich_table(f"技术指标: {symbol}", ["指标", "值"], rows)


@app.command()
def compare(
    symbols: list[str] = typer.Argument(..., help="两个或以上股票代码"),
    format: str = FormatOption,
) -> None:
    """多股技术指标对比"""
    if len(symbols) < 2:
        typer.echo("至少需要 2 只股票进行对比", err=True)
        raise typer.Exit(1)

    engine, _, _ = _get_deps()
    from sequoia_x.analysis.indicators import compute_indicators

    results: dict[str, dict | None] = {}
    for sym in symbols:
        df = engine.get_ohlcv(sym)
        results[sym] = compute_indicators(df) if not df.empty else None

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json(results)
    else:
        keys = ["trend", "current_price", "rsi", "volume_ratio", "vol_trend", "atr", "support_near"]
        labels = ["趋势", "现价", "RSI", "量比", "量能", "ATR", "支撑"]
        cols = ["指标"] + symbols
        rows = []
        for label, key in zip(labels, keys):
            row = [label]
            for sym in symbols:
                ind = results.get(sym)
                if ind is None:
                    row.append("无数据")
                elif key == "trend":
                    row.append(ind.get(key, "—"))
                elif key in ("current_price", "atr", "support_near"):
                    row.append(f"{ind.get(key, 0):.2f}")
                elif key == "rsi":
                    row.append(f"{ind.get(key, 0):.1f}")
                elif key == "volume_ratio":
                    row.append(f"{ind.get(key, 0):.2f}")
                else:
                    row.append(str(ind.get(key, "—")))
            rows.append(row)
        render_rich_table("多股对比", cols, rows)


# ── Strategy subcommands ──


@strategy_app.command("list")
def strategy_list(
    format: str = FormatOption,
) -> None:
    """列出可用策略"""
    registry = _build_strategy_map()
    entries = [{"name": name, "description": desc} for name, (_, desc) in registry.items()]

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json(entries)
    else:
        render_rich_table(
            "可用策略",
            ["策略名", "说明"],
            [[e["name"], e["description"]] for e in entries],
        )


@strategy_app.command("run")
def strategy_run(
    name: str = typer.Argument(..., help="策略类名，如 MaVolumeStrategy"),
    format: str = FormatOption,
) -> None:
    """运行指定策略"""
    registry = _build_strategy_map()
    entry = registry.get(name)
    if entry is None:
        typer.echo(f"未知策略: {name}\n可用策略: {', '.join(registry)}", err=True)
        raise typer.Exit(1)

    engine, settings, _ = _get_deps()
    cls, _ = entry
    strategy = cls(engine=engine, settings=settings)
    selected = strategy.run()

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({"strategy": name, "count": len(selected), "symbols": selected})
    else:
        render_rich_table(
            f"{name}（{len(selected)} 只）",
            ["股票代码"],
            [[s] for s in selected],
        )


# ── Watchlist subcommands ──


@watchlist_app.command("show")
def watchlist_show(
    format: str = FormatOption,
) -> None:
    """查看关注列表"""
    from sequoia_x.core.config import get_settings
    from sequoia_x.analysis.watchlist import load_watchlist

    settings = get_settings()
    wl = load_watchlist(settings.watchlist_path)

    from sequoia_x.output import render_json, render_rich_table

    if format == "json":
        render_json({
            "holdings": [dataclasses.asdict(e) for e in wl.holdings],
            "watchlist": [dataclasses.asdict(e) for e in wl.watchlist],
        })
    else:
        if wl.holdings:
            rows = []
            for e in wl.holdings:
                cost = f"{e.cost_price:.3f}" if e.cost_price else "—"
                rows.append([e.symbol, e.name, cost])
            render_rich_table("持仓股", ["代码", "名称", "成本价"], rows)

        if wl.watchlist:
            rows = []
            for e in wl.watchlist:
                target = f"{e.target_price:.2f}" if e.target_price else "—"
                rows.append([e.symbol, e.name, target, e.note])
            render_rich_table("观察股", ["代码", "名称", "目标价", "备注"], rows)

        if not wl.holdings and not wl.watchlist:
            typer.echo("关注列表为空")
