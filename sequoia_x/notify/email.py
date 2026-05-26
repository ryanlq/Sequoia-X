"""邮件通知模块：将选股结果通过 mail-send CLI 以 HTML 邮件发送。"""

from datetime import date

from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger
from sequoia_x.notify.mail_send import find_mail_send, run_mail_send

logger = get_logger(__name__)


class EmailNotifier:
    """选股结果邮件推送器，通过本地 mail-send CLI 发送 HTML 邮件。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._mail_send_path: str | None = None

    @staticmethod
    def _to_xueqiu_code(code: str) -> str:
        """将纯数字代码转为雪球格式：6开头→SH，4/8开头→BJ，其余→SZ。"""
        if code.startswith("6"):
            return f"SH{code}"
        elif code.startswith(("4", "8")):
            return f"BJ{code}"
        return f"SZ{code}"

    @staticmethod
    def _get_stock_names(symbols: list[str]) -> dict[str, str]:
        """通过 baostock 批量查询股票名称，返回 {code: name} 映射。"""
        import baostock as bs

        bs.login()
        mapping: dict[str, str] = {}
        for code in symbols:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            rs = bs.query_stock_basic(code=f"{prefix}.{code}")
            while rs.next():
                row = rs.get_row_data()
                mapping[code] = row[1]
        bs.logout()
        return mapping

    def _build_section_html(self, symbols: list[str], strategy_name: str, names: dict[str, str]) -> str:
        """构建单个策略的 HTML 区块。"""
        rows_html = ""
        for code in symbols:
            xq_code = self._to_xueqiu_code(code)
            name = names.get(code, xq_code)
            link = f"https://xueqiu.com/S/{xq_code}"
            rows_html += (
                f"<tr>"
                f"<td style='padding:4px 10px;border:1px solid #ddd;'>{code}</td>"
                f"<td style='padding:4px 10px;border:1px solid #ddd;'>{name}</td>"
                f"<td style='padding:4px 10px;border:1px solid #ddd;'>"
                f"<a href='{link}' target='_blank'>{xq_code}</a></td>"
                f"</tr>"
            )

        return f"""\
    <h3 style="margin-top:20px;margin-bottom:8px;">{strategy_name}（{len(symbols)} 只）</h3>
    <table style="border-collapse:collapse; width:100%; max-width:600px;">
      <thead>
        <tr style="background:#f5f5f5;">
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>代码</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>名称</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>雪球链接</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>"""

    def _build_combined_html(self, results: dict[str, list[str]]) -> str:
        """构建合并邮件 HTML：所有策略汇总为一封邮件。"""
        today = date.today().strftime("%Y-%m-%d")
        total = sum(len(v) for v in results.values())

        # 一次性批量查询所有股票名称
        all_symbols = [s for symbols in results.values() for s in symbols]
        names = self._get_stock_names(all_symbols) if all_symbols else {}

        sections = ""
        for strategy_name, symbols in results.items():
            sections += self._build_section_html(symbols, strategy_name, names)

        strategy_summary = " | ".join(f"{k}({len(v)})" for k, v in results.items())

        return f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
  <h2>Sequoia-X 选股播报 | {today}</h2>
  <p><b>日期：</b>{today} &nbsp; <b>策略数：</b>{len(results)} &nbsp; <b>总选股：</b>{total} 只</p>
  <p style="color:#666;font-size:13px;">{strategy_summary}</p>
  <hr style="border:none;border-top:1px solid #eee;">
  {sections}
  <p style="color:#999;font-size:12px;margin-top:24px;">— Sequoia-X V2</p>
</body>
</html>"""

    def _ensure_mail_send(self) -> str:
        """懒加载：首次调用时检测 olk 是否可用。"""
        if self._mail_send_path is None:
            self._mail_send_path = find_mail_send()
        return self._mail_send_path

    def send_all(self, results: dict[str, list[str]]) -> None:
        """将所有策略的选股结果合并为一封邮件发送。

        Args:
            results: {策略名: 股票代码列表} 的映射，仅包含有结果的策略。

        Raises:
            不抛出异常，发送失败时记录 ERROR 日志。
        """
        if not results:
            logger.info("无选股结果，跳过邮件推送")
            return

        total = sum(len(v) for v in results.values())
        try:
            exe = self._ensure_mail_send()
            today = date.today()
            subject = f"Sequoia-X 选股播报 | {today} | {total} 只"
            html = self._build_combined_html(results)
            run_mail_send(exe, self.settings.mail_to, subject, html)
            logger.info(f"邮件推送成功，共 {len(results)} 个策略、{total} 只股票")
        except Exception as exc:
            logger.error(f"邮件推送失败：{exc}")
