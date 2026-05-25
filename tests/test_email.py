"""邮件通知属性测试。"""

from unittest.mock import patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from sequoia_x.core.config import Settings
from sequoia_x.notify.email import EmailNotifier


def make_settings(mail_to: str = "test@example.com") -> Settings:
    return Settings(
        db_path="data/test.db",
        start_date="2024-01-01",
        mail_to=mail_to,
    )


# Feature: sequoia-x-v2, Property 10: 邮件 HTML 包含所有选股结果
@given(
    symbols=st.lists(
        st.text(min_size=6, max_size=6, alphabet="0123456789"),
        min_size=1, max_size=10, unique=True,
    )
)
@h_settings(max_examples=50)
def test_email_html_contains_all_symbols(symbols: list[str]) -> None:
    """属性 10：生成的 HTML 应包含所有 symbol。"""
    settings = make_settings()
    notifier = EmailNotifier(settings)

    with patch.object(notifier, "_get_stock_names", return_value={s: f"股票{s}" for s in symbols}):
        html = notifier._build_combined_html({"TestStrategy": symbols})

    for symbol in symbols:
        assert symbol in html


# Feature: sequoia-x-v2, Property 11: 邮件发送调用 mail-send
def test_send_all_calls_mail_send() -> None:
    """属性 11：send_all() 应调用 run_mail_send 并传入正确的收件人。"""
    settings = make_settings(mail_to="user@example.com")
    notifier = EmailNotifier(settings)

    with patch("sequoia_x.notify.email.find_mail_send", return_value="/usr/local/bin/mail-send"):
        with patch("sequoia_x.notify.email.run_mail_send") as mock_run:
            with patch.object(notifier, "_get_stock_names", return_value={"000001": "平安银行"}):
                notifier.send_all({"TestStrategy": ["000001"]})

    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][1] == "user@example.com"  # --to 参数


def test_send_all_skips_when_empty() -> None:
    """无选股结果时 send_all() 不应调用 mail-send。"""
    settings = make_settings()
    notifier = EmailNotifier(settings)

    with patch("sequoia_x.notify.email.find_mail_send") as mock_find:
        notifier.send_all({})

    mock_find.assert_not_called()


# Feature: sequoia-x-v2, Property 12: 发送失败记录 ERROR 日志
def test_send_all_failure_logs_error() -> None:
    """属性 12：发送失败时，send_all() 应记录 ERROR 级别日志，不抛出异常。"""
    import logging as _logging
    import sequoia_x.notify.email as email_module

    settings = make_settings()
    notifier = EmailNotifier(settings)

    email_logger = _logging.getLogger(email_module.__name__)
    log_records: list[_logging.LogRecord] = []

    class _ListHandler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            log_records.append(record)

    handler = _ListHandler(_logging.ERROR)
    email_logger.addHandler(handler)
    try:
        with patch("sequoia_x.notify.email.find_mail_send", side_effect=RuntimeError("download failed")):
            notifier.send_all({"TestStrategy": ["000001"]})
    finally:
        email_logger.removeHandler(handler)

    assert any(r.levelno == _logging.ERROR for r in log_records)
