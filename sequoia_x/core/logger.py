"""日志模块：基于 rich 库提供带颜色的结构化终端日志输出。"""

import logging

from rich.console import Console
from rich.logging import RichHandler

_FORMAT = "%(name)s - %(message)s"

_stderr_console = Console(stderr=True)


def get_logger(name: str) -> logging.Logger:
    """
    工厂函数，返回配置了 RichHandler 的 Logger 实例。

    所有日志输出到 stderr，不影响 stdout 的 JSON/数据输出。
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    handler = RichHandler(
        console=_stderr_console,
        rich_tracebacks=True,
        show_path=False,
        log_time_format="[%Y-%m-%d %H:%M:%S]",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    return logger
