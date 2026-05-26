"""邮件发送模块：通过 olk (Microsoft Outlook CLI) 发送 HTML 邮件。"""

import shutil
import subprocess

from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


def find_mail_send(manual_path: str = "") -> str:
    """返回可用的邮件发送工具路径。

    Args:
        manual_path: 保留参数（兼容旧接口），不再使用。

    Returns:
        olk 可执行文件路径。

    Raises:
        RuntimeError: olk 未安装时抛出。
    """
    found = shutil.which("olk")
    if found:
        return found
    raise RuntimeError(
        "未找到 olk 命令，请先安装 Microsoft Outlook CLI。"
    )


def run_mail_send(executable: str, to: str, subject: str, html_body: str) -> None:
    """通过 olk mail send 发送 HTML 邮件。

    Args:
        executable: olk 可执行文件路径。
        to: 收件人邮箱。
        subject: 邮件主题。
        html_body: HTML 格式的邮件正文。

    Raises:
        subprocess.CalledProcessError: olk 返回非零退出码。
    """
    cmd = [executable, "mail", "send", f"--to={to}", f"--subject={subject}", "--body", html_body, "--html"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.error(f"olk mail send 失败 (exit={result.returncode}): {result.stderr.strip()}")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    logger.info(f"邮件发送成功 → {to}")
