"""scan 结果缓存模块：将策略扫描结果持久化到本地文件，避免重复扫描。"""

import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "sequoia-x"
DEFAULT_TTL = 86400  # 1 天


def _cache_path(board: str | None = None, min_turnover: float | None = None) -> Path:
    """根据过滤条件生成缓存文件路径。"""
    key_parts = [board or "all"]
    key_parts.append(f"t{min_turnover or 0}")
    key = "_".join(key_parts)
    return CACHE_DIR / f"scan_{key}.json"


def save_scan_results(
    results: dict[str, list[str]],
    board: str | None = None,
    min_turnover: float | None = None,
) -> None:
    """保存扫描结果到缓存文件。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(board, min_turnover)
    data = {"timestamp": time.time(), "results": results}
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def load_scan_results(
    ttl: int = DEFAULT_TTL,
    board: str | None = None,
    min_turnover: float | None = None,
) -> dict[str, list[str]] | None:
    """加载缓存中未过期的扫描结果。过期或不存在返回 None。"""
    path = _cache_path(board, min_turnover)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data["timestamp"] > ttl:
            return None
        return data["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
