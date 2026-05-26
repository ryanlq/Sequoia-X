"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 全局配置文件位置（uv tool install 后从任意目录也能找到）
_GLOBAL_CONFIG_DIR = Path.home() / ".config" / "sequoia-x"
_GLOBAL_ENV_FILE = _GLOBAL_CONFIG_DIR / ".env"


def _find_env_file() -> str:
    """查找 .env 文件：当前目录优先，回退到全局配置目录。"""
    cwd_env = Path(".env")
    if cwd_env.exists():
        return str(cwd_env)
    if _GLOBAL_ENV_FILE.exists():
        return str(_GLOBAL_ENV_FILE)
    # 都不存在时返回默认值，pydantic-settings 会跳过
    return str(cwd_env)


class Settings(BaseSettings):
    db_path: str = "data/sequoia_v2.db"
    start_date: str = "2024-01-01"
    mail_to: str = ""  # 可选，邮件推送时才需要
    watchlist_path: str = "watchlist.toml"

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局 Settings 单例。

    配置查找顺序：
    1. 环境变量
    2. 当前目录 .env
    3. ~/.config/sequoia-x/.env

    Returns:
        Settings: 全局唯一的配置实例。
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
