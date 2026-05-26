"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。

路径查找策略：
- 项目模式：当前目录存在 .env / watchlist.toml / data/ 时使用当前目录
- 全局模式：否则使用 XDG 标准路径
  - 配置：~/.config/sequoia-x/
  - 数据：~/.local/share/sequoia-x/
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# XDG 全局路径
GLOBAL_CONFIG_DIR = Path.home() / ".config" / "sequoia-x"
GLOBAL_DATA_DIR = Path.home() / ".local" / "share" / "sequoia-x"

GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"
GLOBAL_DB_FILE = GLOBAL_DATA_DIR / "sequoia_v2.db"
GLOBAL_WATCHLIST_FILE = GLOBAL_CONFIG_DIR / "watchlist.toml"


def _is_project_mode() -> bool:
    """当前目录存在 .env 或 watchlist.toml 时认为是项目开发模式。"""
    return Path(".env").exists() or Path("watchlist.toml").exists()


def _resolve_db_path() -> str:
    """解析数据库路径。项目模式用 data/sequoia_v2.db，全局模式用 XDG 路径。"""
    if _is_project_mode():
        return "data/sequoia_v2.db"
    return str(GLOBAL_DB_FILE)


def _resolve_watchlist_path() -> str:
    """解析 watchlist 路径。项目模式用 watchlist.toml，全局模式用 XDG 路径。"""
    if _is_project_mode():
        return "watchlist.toml"
    return str(GLOBAL_WATCHLIST_FILE)


def _find_env_file() -> str:
    """查找 .env 文件：当前目录优先，回退到全局配置目录。"""
    if Path(".env").exists():
        return ".env"
    if GLOBAL_ENV_FILE.exists():
        return str(GLOBAL_ENV_FILE)
    return ".env"


class Settings(BaseSettings):
    db_path: str = ""  # 默认值由 __init__ 动态设置
    start_date: str = "2024-01-01"
    mail_to: str = ""
    watchlist_path: str = ""  # 默认值由 __init__ 动态设置

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # 未通过环境变量/文件指定时，使用动态解析的默认值
        if not self.db_path:
            self.db_path = _resolve_db_path()
        if not self.watchlist_path:
            self.watchlist_path = _resolve_watchlist_path()


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局 Settings 单例。

    配置查找顺序：
    1. 环境变量
    2. 当前目录 .env（项目模式）
    3. ~/.config/sequoia-x/.env（全局模式）

    Returns:
        Settings: 全局唯一的配置实例。
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
