"""技术指标计算模块：基于 OHLCV 数据计算趋势、动量、波动率等指标。"""

import pandas as pd


def compute_indicators(df: pd.DataFrame) -> dict | None:
    """从 OHLCV DataFrame 计算技术指标。

    Args:
        df: 至少包含 date, open, high, low, close, volume 列的 DataFrame，
            按日期升序排列。

    Returns:
        指标字典。数据不足 20 条时返回 None。
    """
    if len(df) < 20:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    last = df.iloc[-1]
    current_price = float(last["close"])

    # ── 均线 ──
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean() if len(df) >= 60 else None

    last_ma5 = float(ma5.iloc[-1])
    last_ma10 = float(ma10.iloc[-1])
    last_ma20 = float(ma20.iloc[-1])
    last_ma60 = float(ma60.iloc[-1]) if ma60 is not None and not ma60.isna().iloc[-1] else None

    # ── 趋势判断 ──
    trend = _classify_trend(last_ma5, last_ma10, last_ma20, last_ma60)

    # ── 价格相对均线位置 ──
    price_vs_mas = {}
    for label, ma_val in [("ma5", last_ma5), ("ma20", last_ma20), ("ma60", last_ma60)]:
        if ma_val and ma_val > 0:
            price_vs_mas[label] = round((current_price - ma_val) / ma_val * 100, 2)
        else:
            price_vs_mas[label] = None

    # ── 支撑/阻力位 ──
    support_near = float(low.iloc[-20:].min())
    resistance_near = float(high.iloc[-20:].max())
    support_medium = float(low.iloc[-60:].min()) if len(df) >= 60 else support_near

    # ── 成交量 ──
    vol_ma20 = volume.rolling(20).mean()
    last_vol_ma20 = float(vol_ma20.iloc[-1]) if not vol_ma20.isna().iloc[-1] else 0
    volume_ratio = round(float(volume.iloc[-1]) / last_vol_ma20, 2) if last_vol_ma20 > 0 else 0
    vol_ma5 = volume.rolling(5).mean()
    last_vol_ma5 = float(vol_ma5.iloc[-1]) if not vol_ma5.isna().iloc[-1] else 0
    vol_trend = "放量" if last_vol_ma5 > last_vol_ma20 * 1.2 else ("缩量" if last_vol_ma5 < last_vol_ma20 * 0.8 else "正常")

    # ── ATR14 ──
    atr = _calc_atr(high, low, close, period=14)

    # ── RSI14 ──
    rsi = _calc_rsi(close, period=14)

    return {
        "current_price": current_price,
        "ma5": last_ma5,
        "ma10": last_ma10,
        "ma20": last_ma20,
        "ma60": last_ma60,
        "trend": trend,
        "price_vs_mas": price_vs_mas,
        "support_near": support_near,
        "support_medium": support_medium,
        "resistance_near": resistance_near,
        "volume_ratio": volume_ratio,
        "vol_trend": vol_trend,
        "atr": atr,
        "rsi": rsi,
    }


def _classify_trend(ma5: float, ma10: float, ma20: float, ma60: float | None) -> str:
    """根据均线排列判断趋势。"""
    if ma60 is not None:
        if ma5 > ma10 > ma20 > ma60:
            return "强多头"
        if ma5 < ma10 < ma20 < ma60:
            return "强空头"

    if ma5 > ma20 and (ma60 is None or ma20 > ma60):
        return "多头"
    if ma5 < ma20 and (ma60 is None or ma20 < ma60):
        return "空头"
    return "震荡"


def _calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """计算 ATR (Average True Range)。"""
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_series = tr.rolling(period).mean()
    val = atr_series.iloc[-1]
    return float(val) if not pd.isna(val) else 0.0


def _calc_rsi(close: pd.Series, period: int = 14) -> float:
    """计算 RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi_series = 100 - 100 / (1 + rs)
    val = rsi_series.iloc[-1]
    return round(float(val), 1) if not pd.isna(val) else 50.0
