"""scan 结果缓存模块：将策略扫描结果持久化到本地文件，避免重复扫描。"""

import json
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "sequoia-x"
SCAN_CACHE_FILE = CACHE_DIR / "scan_results.json"
DEFAULT_TTL = 86400  # 1 天


def save_scan_results(results: dict[str, list[str]]) -> None:
    """保存扫描结果到缓存文件。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {"timestamp": time.time(), "results": results}
    with open(SCAN_CACHE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def load_scan_results(ttl: int = DEFAULT_TTL) -> dict[str, list[str]] | None:
    """加载缓存中未过期的扫描结果。过期或不存在返回 None。"""
    if not SCAN_CACHE_FILE.exists():
        return None
    try:
        with open(SCAN_CACHE_FILE) as f:
            data = json.load(f)
        if time.time() - data["timestamp"] > ttl:
            return None
        return data["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
