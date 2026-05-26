"""投资建议模块：根据技术指标给出持仓/观察股的操作建议。"""

from dataclasses import dataclass

from sequoia_x.analysis.indicators import compute_indicators
from sequoia_x.analysis.watchlist import Watchlist, WatchlistEntry
from sequoia_x.core.logger import get_logger
from sequoia_x.data.engine import DataEngine

logger = get_logger(__name__)


def _get_actual_price(symbol: str) -> float | None:
    """通过 baostock 获取最新真实（不复权）收盘价。"""
    import baostock as bs

    bs_code = DataEngine._to_baostock_code(symbol)
    lg = bs.login()
    if lg.error_code != "0":
        return None
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,close",
            start_date="2026-01-01",
            end_date="2030-12-31",
            frequency="d",
            adjustflag="3",  # 不复权
        )
        last_close = None
        while rs.next():
            last_close = rs.get_row_data()[1]
        return float(last_close) if last_close else None
    except Exception:
        return None
    finally:
        bs.logout()


def _batch_actual_prices(symbols: list[str]) -> dict[str, float]:
    """批量获取多只股票的真实收盘价。"""
    import baostock as bs

    if not symbols:
        return {}

    bs.login()
    result: dict[str, float] = {}
    try:
        for symbol in symbols:
            bs_code = DataEngine._to_baostock_code(symbol)
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,close",
                start_date="2026-01-01",
                end_date="2030-12-31",
                frequency="d",
                adjustflag="3",
            )
            last_close = None
            while rs.next():
                last_close = rs.get_row_data()[1]
            if last_close:
                result[symbol] = float(last_close)
    finally:
        bs.logout()
    return result


@dataclass
class StockAnalysis:
    """单只股票的分析结果。"""

    symbol: str
    name: str
    current_price: float
    indicators: dict | None
    recommendation: str       # HOLD/SELL/TAKE_PROFIT 或 BUY/WAIT/AVOID
    reason: str
    trend: str
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    buy_zone_low: float | None = None
    buy_zone_high: float | None = None
    pnl_pct: float | None = None       # 持仓股盈亏百分比


def _indicators_brief(ind: dict) -> str:
    """从指标中提取关键数据摘要，用于理由拼接。"""
    rsi = ind.get("rsi", 50)
    vol_ratio = ind.get("volume_ratio", 0)
    vol_trend = ind.get("vol_trend", "")
    dist_ma20 = ind.get("price_vs_mas", {}).get("ma20", 0) or 0
    dist_ma60 = ind.get("price_vs_mas", {}).get("ma60")

    parts = [f"RSI={rsi:.0f}"]

    if vol_ratio > 1.5:
        parts.append(f"放量({vol_ratio:.1f}倍)")
    elif vol_ratio < 0.7:
        parts.append("缩量")
    else:
        parts.append(vol_trend)

    if dist_ma20:
        sign = "+" if dist_ma20 > 0 else ""
        parts.append(f"偏离MA20 {sign}{dist_ma20:.1f}%")

    if dist_ma60 is not None:
        sign = "+" if dist_ma60 > 0 else ""
        parts.append(f"偏离MA60 {sign}{dist_ma60:.1f}%")

    return "，".join(parts)


def analyze_holding(ind: dict, entry: WatchlistEntry) -> tuple[str, str, float | None, float | None, float | None]:
    """分析持仓股，返回 (recommendation, reason, stop_loss, tp1, tp2)。"""
    price = ind["current_price"]
    trend = ind["trend"]
    atr = ind["atr"]
    rsi = ind["rsi"]
    support_near = ind["support_near"]
    ma20 = ind["ma20"]
    ma60 = ind.get("ma60")
    brief = _indicators_brief(ind)

    stop = round(max(support_near, price - 2 * atr), 2) if atr > 0 else round(support_near, 2)
    tp1 = round(price + 2 * atr, 2) if atr > 0 else None
    tp2 = round(price + 4 * atr, 2) if atr > 0 else None

    # ── SELL ──
    if trend in ("强空头", "空头") and ma60 and price < ma60:
        return "SELL", f"趋势破位，跌破MA60({ma60:.2f})。{brief}", stop, tp1, tp2

    if trend in ("空头",) and ind["volume_ratio"] > 2.0 and price < ma20:
        return "SELL", f"空头放量下跌，资金出逃。{brief}", stop, tp1, tp2

    # ── TAKE_PROFIT ──
    dist_from_ma20 = ind["price_vs_mas"].get("ma20", 0) or 0
    if dist_from_ma20 > 15 and rsi > 70:
        return "TAKE_PROFIT", f"偏离MA20达{dist_from_ma20:.1f}%且RSI超买，考虑分批止盈。{brief}", stop, tp1, tp2

    # ── HOLD ──
    reason_parts = []
    if trend in ("强多头", "多头"):
        reason_parts.append("趋势向好")
    else:
        reason_parts.append("趋势待确认")

    if ma20 and price > ma20:
        reason_parts.append(f"MA20支撑({ma20:.2f})")
    else:
        reason_parts.append(f"近支撑({support_near:.2f})")

    reason_parts.append(f"跌破{stop:.2f}需警惕")
    reason_parts.append(brief)

    return "HOLD", "。".join(reason_parts), stop, tp1, tp2


def analyze_watchlist_stock(ind: dict, entry: WatchlistEntry) -> tuple[str, str, float | None, float | None, float | None, float | None, float | None]:
    """分析观察股，返回 (recommendation, reason, buy_low, buy_high, stop_loss, tp1, tp2)。"""
    price = ind["current_price"]
    trend = ind["trend"]
    atr = ind["atr"]
    support_near = ind["support_near"]
    ma20 = ind["ma20"]
    brief = _indicators_brief(ind)

    # ── AVOID ──
    if trend in ("强空头",):
        return "AVOID", f"空头排列，暂时远离。{brief}", None, None, None, None, None

    # ── BUY ──
    if entry.target_price and price <= entry.target_price * 1.05:
        buy_low = round(min(ma20, entry.target_price) if ma20 else entry.target_price, 2)
        buy_high = round(buy_low * 1.03, 2)
        stop = round(buy_low - 2 * atr, 2) if atr > 0 else None
        tp1 = round(price + 2 * atr, 2) if atr > 0 else None
        tp2 = round(price + 4 * atr, 2) if atr > 0 else None
        return "BUY", f"接近目标价{entry.target_price:.2f}。{brief}", buy_low, buy_high, stop, tp1, tp2

    if trend in ("多头", "强多头") and ma20 and abs(price - ma20) / ma20 < 0.03 and ind["vol_trend"] != "缩量":
        buy_low = round(ma20 * 0.97, 2)
        buy_high = round(ma20 * 1.03, 2)
        stop = round(buy_low - 2 * atr, 2) if atr > 0 else None
        tp1 = round(price + 2 * atr, 2) if atr > 0 else None
        tp2 = round(price + 4 * atr, 2) if atr > 0 else None
        return "BUY", f"回踩MA20附近，量能健康。{brief}", buy_low, buy_high, stop, tp1, tp2

    # ── WAIT ── 告诉用户等什么价位
    dist = ind["price_vs_mas"].get("ma20", 0) or 0
    if dist > 10 and ma20:
        return "WAIT", f"偏离MA20达{dist:.1f}%，等待回调至{ma20:.2f}附近。{brief}", None, None, None, None, None

    if trend in ("空头",):
        return "WAIT", f"趋势偏弱，等待MA20拐头再考虑。{brief}", None, None, None, None, None

    # 多头但暂无明确买入点，给出关注价位
    watch_price = f"关注{ma20:.2f}附近企稳机会" if ma20 else "等待明确信号"
    return "WAIT", f"{watch_price}。{brief}", None, None, None, None, None


def run_analysis(engine: DataEngine, watchlist: Watchlist) -> tuple[list[StockAnalysis], list[StockAnalysis]]:
    """对关注列表中的所有股票执行分析。

    Returns:
        (持仓分析列表, 观察股分析列表)
    """
    from sequoia_x.notify.email import EmailNotifier

    all_symbols = [e.symbol for e in watchlist.holdings + watchlist.watchlist]
    if not all_symbols:
        return [], []

    names = EmailNotifier._get_stock_names(all_symbols)

    # 批量获取真实（不复权）收盘价，用于将复权数据转换为实际价格
    logger.info("获取真实收盘价...")
    actual_prices = _batch_actual_prices(all_symbols)

    holdings_results: list[StockAnalysis] = []
    watchlist_results: list[StockAnalysis] = []

    for entry in watchlist.holdings:
        analysis = _analyze_one(engine, entry, names, actual_prices, is_holding=True)
        if analysis:
            holdings_results.append(analysis)

    for entry in watchlist.watchlist:
        analysis = _analyze_one(engine, entry, names, actual_prices, is_holding=False)
        if analysis:
            watchlist_results.append(analysis)

    return holdings_results, watchlist_results


def _convert(val: float | None, ratio: float) -> float | None:
    """用比率将复权价转换为真实价。"""
    return round(val * ratio, 2) if val is not None else None


def _analyze_one(
    engine: DataEngine,
    entry: WatchlistEntry,
    names: dict[str, str],
    actual_prices: dict[str, float],
    is_holding: bool,
) -> StockAnalysis | None:
    """分析单只股票。"""
    symbol = entry.symbol
    name = entry.name or names.get(symbol, symbol)
    df = engine.get_ohlcv(symbol)

    if df.empty:
        return StockAnalysis(
            symbol=symbol, name=name, current_price=0,
            indicators=None, recommendation="WAIT" if not is_holding else "HOLD",
            reason="本地无数据", trend="未知",
        )

    # 复权数据上的技术指标计算（趋势、MA、RSI 等用复权数据是正确的）
    ind = compute_indicators(df)
    if ind is None:
        return StockAnalysis(
            symbol=symbol, name=name, current_price=0,
            indicators=None, recommendation="WAIT" if not is_holding else "HOLD",
            reason="数据不足（少于20条）", trend="未知",
        )

    # 计算复权→真实价格转换比率
    adj_price = ind["current_price"]
    actual = actual_prices.get(symbol)
    if actual and adj_price > 0:
        ratio = actual / adj_price
    else:
        logger.warning(f"[{symbol}] 无法获取真实价格，使用复权价")
        ratio = 1.0

    actual_ma20 = _convert(ind["ma20"], ratio)
    actual_support = _convert(ind["support_near"], ratio)
    actual_atr = _convert(ind["atr"], ratio)

    # 构建供建议逻辑使用的指标（已转换为真实价格）
    real_ind = {
        **ind,
        "current_price": round(actual, 2) if actual else adj_price,
        "ma20": actual_ma20,
        "atr": actual_atr if actual_atr else ind["atr"],
        "support_near": actual_support if actual_support else ind["support_near"],
    }

    pnl_pct = None
    if is_holding and entry.cost_price and entry.cost_price > 0:
        pnl_pct = round((actual - entry.cost_price) / entry.cost_price * 100, 2)

    if is_holding:
        rec, reason, stop, tp1, tp2 = analyze_holding(real_ind, entry)
        return StockAnalysis(
            symbol=symbol, name=name, current_price=real_ind["current_price"],
            indicators={**ind, "ma20": actual_ma20}, recommendation=rec, reason=reason,
            trend=ind["trend"], stop_loss=stop,
            take_profit_1=tp1, take_profit_2=tp2,
            pnl_pct=pnl_pct,
        )
    else:
        rec, reason, buy_low, buy_high, stop, tp1, tp2 = analyze_watchlist_stock(real_ind, entry)
        return StockAnalysis(
            symbol=symbol, name=name, current_price=real_ind["current_price"],
            indicators={**ind, "ma20": actual_ma20}, recommendation=rec, reason=reason,
            trend=ind["trend"], stop_loss=stop,
            take_profit_1=tp1, take_profit_2=tp2,
            buy_zone_low=buy_low, buy_zone_high=buy_high,
        )
