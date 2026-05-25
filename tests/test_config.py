"""配置管理属性测试。"""

import os
import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from pydantic import ValidationError


# Feature: sequoia-x-v2, Property 1: 环境变量覆盖配置默认值
@given(db_path=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="/_.-")))
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_env_overrides_default(db_path: str, monkeypatch) -> None:
    """属性 1：任意合法 db_path 通过环境变量设置后，Settings 实例应反映该值。"""
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("MAIL_TO", "test@example.com")
    import sequoia_x.core.config as cfg_module
    monkeypatch.setattr(cfg_module, "_settings", None)
    from sequoia_x.core.config import Settings
    s = Settings()
    assert s.db_path == db_path


# Feature: sequoia-x-v2, Property 2: 缺失必填字段触发 ValidationError
def test_missing_required_field_raises() -> None:
    """属性 2：缺少 mail_to 时，实例化 Settings 应抛出 ValidationError。"""
    from sequoia_x.core.config import Settings
    env_backup = os.environ.pop("MAIL_TO", None)
    try:
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)
        assert "mail_to" in str(exc_info.value).lower()
    finally:
        if env_backup is not None:
            os.environ["MAIL_TO"] = env_backup
