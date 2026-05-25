"""关注列表加载模块：解析 watchlist.toml 文件。"""

from dataclasses import dataclass, field
from pathlib import Path

from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WatchlistEntry:
    """关注列表中的单只股票条目。"""

    symbol: str
    name: str = ""
    cost_price: float | None = None
    shares: int | None = None
    target_price: float | None = None
    note: str = ""


@dataclass
class Watchlist:
    """完整的关注列表。"""

    holdings: list[WatchlistEntry] = field(default_factory=list)
    watchlist: list[WatchlistEntry] = field(default_factory=list)


def load_watchlist(path: str) -> Watchlist:
    """从 TOML 文件加载关注列表。

    Args:
        path: TOML 文件路径。

    Returns:
        Watchlist 实例。文件不存在时返回空列表。
    """
    if not Path(path).is_file():
        logger.warning(f"关注列表文件不存在: {path}，跳过个股分析")
        return Watchlist()

    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            logger.error("Python 3.10 需要安装 tomli: uv add tomli")
            return Watchlist()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    holdings = []
    for item in data.get("holdings", []):
        symbol = item.get("symbol", "").strip()
        if not symbol:
            continue
        holdings.append(
            WatchlistEntry(
                symbol=symbol,
                name=item.get("name", ""),
                cost_price=item.get("cost_price"),
                shares=item.get("shares"),
                target_price=item.get("target_price"),
                note=item.get("note", ""),
            )
        )

    watchlist = []
    for item in data.get("watchlist", []):
        symbol = item.get("symbol", "").strip()
        if not symbol:
            continue
        watchlist.append(
            WatchlistEntry(
                symbol=symbol,
                name=item.get("name", ""),
                cost_price=item.get("cost_price"),
                shares=item.get("shares"),
                target_price=item.get("target_price"),
                note=item.get("note", ""),
            )
        )

    logger.info(f"关注列表加载完成: {len(holdings)} 只持仓, {len(watchlist)} 只观察")
    return Watchlist(holdings=holdings, watchlist=watchlist)
