"""mail-send CLI 自动安装模块：检测平台、按需下载对应二进制到项目 bin/ 目录。"""

import platform
import shutil
import stat
import subprocess
from pathlib import Path

from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)

MAIL_SEND_VERSION = "v0.1.0"
RELEASE_BASE_URL = f"https://github.com/ryanlq/smtp-send/releases/download/{MAIL_SEND_VERSION}"

# 平台 → Release 资源文件名映射
_BINARY_MAP: dict[str, str] = {
    "Linux-x86_64": "mail-send-linux-amd64",
    "Linux-aarch64": "mail-send-linux-arm64",
    "Darwin-x86_64": "mail-send-darwin-amd64",
    "Darwin-arm64": "mail-send-darwin-arm64",
    "Windows-AMD64": "mail-send-windows-amd64.exe",
}


def _platform_key() -> str:
    """返回 'OS-arch' 格式的平台标识。"""
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin" and machine == "arm64":
        return "Darwin-arm64"
    if system == "Darwin":
        return "Darwin-x86_64"
    if system == "Windows":
        return "Windows-AMD64"
    if machine in ("x86_64", "AMD64"):
        return "Linux-x86_64"
    if machine in ("aarch64", "arm64"):
        return "Linux-aarch64"
    return f"{system}-{machine}"


def _project_bin_dir() -> Path:
    """返回项目根目录下的 bin/ 绝对路径。"""
    return Path(__file__).resolve().parent.parent.parent / "bin"


def find_mail_send(manual_path: str = "") -> str:
    """返回可用的 mail-send 可执行文件路径。

    查找顺序：
    1. 手动指定的路径（manual_path）
    2. 系统 $PATH 中的 mail-send
    3. 项目 bin/ 目录下已下载的二进制
    4. 自动下载到 bin/ 并返回

    Args:
        manual_path: 用户通过环境变量手动指定的路径。

    Returns:
        mail-send 的绝对路径字符串。

    Raises:
        RuntimeError: 下载失败时抛出。
    """
    # 1. 手动指定
    if manual_path:
        p = Path(manual_path)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p.resolve())
        logger.warning(f"手动指定的 mail-send 路径无效: {manual_path}")

    # 2. 系统 PATH
    found = shutil.which("mail-send")
    if found:
        return found

    # 3. 已下载
    bin_dir = _project_bin_dir()
    key = _platform_key()
    binary_name = _BINARY_MAP.get(key)
    if not binary_name:
        raise RuntimeError(f"不支持的平台: {key}")

    local_binary = bin_dir / binary_name
    if local_binary.is_file():
        return str(local_binary)

    # 4. 自动下载
    return _download(binary_name, bin_dir, local_binary)


def _download(binary_name: str, bin_dir: Path, dest: Path) -> str:
    """从 GitHub Release 下载 mail-send 二进制文件。"""
    import os
    import urllib.request
    import urllib.error

    url = f"{RELEASE_BASE_URL}/{binary_name}"
    bin_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"正在下载 mail-send: {url}")
    try:
        tmp = dest.with_suffix(".tmp")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        logger.info(f"mail-send 下载完成: {dest}")
        return str(dest)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"mail-send 下载失败: {exc}") from exc


def run_mail_send(executable: str, to: str, subject: str, html_body: str) -> None:
    """调用 mail-send CLI 发送 HTML 邮件。

    Args:
        executable: mail-send 可执行文件路径。
        to: 收件人邮箱。
        subject: 邮件主题。
        html_body: HTML 格式的邮件正文。

    Raises:
        subprocess.CalledProcessError: mail-send 返回非零退出码。
    """
    cmd = [executable, "--to", to, "--subject", subject, "--body", "-", "--html"]
    result = subprocess.run(
        cmd,
        input=html_body,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error(f"mail-send 执行失败 (exit={result.returncode}): {result.stderr.strip()}")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    logger.info(f"邮件发送成功 → {to}")
