"""AkShare 数据源：通过 ak CLI 工具获取 A 股行情数据。"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, timedelta

import pandas as pd

from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)

_AKCLI_INSTALL_URL = (
    "https://github.com/ryanlq/akshare-cli/releases/download/"
    "v0.1.0/akcli-0.1.0-py3-none-any.whl"
)


def _find_akcli() -> str | None:
    """查找 ak CLI 可执行文件路径，未安装返回 None。"""
    return shutil.which("ak")


def ensure_akcli() -> str:
    """确保 ak CLI 可用，返回路径。未安装则自动安装。"""
    path = _find_akcli()
    if path:
        return path

    logger.info("未检测到 ak CLI，自动安装中...")
    try:
        subprocess.run(
            ["uv", "tool", "install", _AKCLI_INSTALL_URL],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        logger.warning("uv 未安装，无法自动安装 ak CLI，请手动执行：")
        logger.warning(f"  uv tool install {_AKCLI_INSTALL_URL}")
        raise
    except subprocess.CalledProcessError as e:
        logger.warning(f"ak CLI 安装失败: {e.stderr}")
        raise

    path = _find_akcli()
    if not path:
        raise RuntimeError("ak CLI 安装后仍未找到，请检查 PATH")
    logger.info(f"ak CLI 安装成功: {path}")
    return path


def fetch_kline_akshare(
    symbol: str,
    start: str,
    end: str,
    akcli_path: str | None = None,
) -> pd.DataFrame:
    """通过 ak CLI 获取单只股票后复权日 K 线数据。

    Args:
        symbol: 纯6位股票代码，如 "600519"
        start: 开始日期 "YYYY-MM-DD" 或 "YYYYMMDD"
        end: 结束日期
        akcli_path: ak CLI 路径，None 则自动查找

    Returns:
        DataFrame with columns: [symbol, date, open, high, low, close, volume, turnover]
        空数据返回空 DataFrame。
    """
    ak = akcli_path or _find_akcli()
    if not ak:
        return pd.DataFrame()

    # ak CLI 日期格式为 YYYYMMDD
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")

    try:
        result = subprocess.run(
            [
                ak, "stock_zh_a_hist",
                "--symbol", symbol,
                "--period", "daily",
                "--start_date", start_fmt,
                "--end_date", end_fmt,
                "--adjust", "hfq",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"[{symbol}] akshare 请求失败: {e}")
        return pd.DataFrame()

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.warning(f"[{symbol}] akshare 返回错误: {stderr}")
        return pd.DataFrame()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning(f"[{symbol}] akshare 返回非 JSON 数据")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    # akshare 返回字段映射 → 统一格式
    rows = []
    for item in data:
        try:
            d = item.get("日期", "")
            if isinstance(d, str) and "T" in d:
                d = d[:10]
            elif hasattr(d, "strftime"):
                d = d.strftime("%Y-%m-%d")
            rows.append({
                "symbol": symbol,
                "date": d,
                "open": float(item.get("开盘", 0)),
                "high": float(item.get("最高", 0)),
                "low": float(item.get("最低", 0)),
                "close": float(item.get("收盘", 0)),
                "volume": float(item.get("成交量", 0)),
                "turnover": float(item.get("成交额", 0)),
            })
        except (ValueError, TypeError, KeyError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    df = df[df["volume"] > 0]
    return df


def fetch_kline_akshare_batch(
    tasks: list[tuple[str, str, str]],
    akcli_path: str | None = None,
) -> pd.DataFrame:
    """批量获取多只股票的 K 线数据。

    Args:
        tasks: [(symbol, start, end), ...]
        akcli_path: ak CLI 路径

    Returns:
        合并后的 DataFrame
    """
    ak = akcli_path
    if ak is None:
        ak = _find_akcli()
        if not ak:
            return pd.DataFrame()

    frames = []
    for symbol, start, end in tasks:
        df = fetch_kline_akshare(symbol, start, end, akcli_path=ak)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
