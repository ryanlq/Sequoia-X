"""分析报告生成模块：将分析结果生成为 HTML 邮件。"""

from datetime import date

from sequoia_x.analysis.advisor import StockAnalysis
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


def _rec_color(rec: str) -> str:
    """建议对应的背景颜色。"""
    if rec in ("SELL", "AVOID"):
        return "#fde8e8"
    if rec in ("BUY", "TAKE_PROFIT"):
        return "#e8f5e8"
    return "#f5f5f5"


def _fmt(val: float | None, suffix: str = "") -> str:
    """格式化可选浮点数。"""
    return f"{val:.2f}{suffix}" if val is not None else "-"


def _fmt_pnl(pnl: float | None) -> str:
    """格式化盈亏百分比，带颜色。"""
    if pnl is None:
        return "-"
    sign = "+" if pnl >= 0 else ""
    color = "#e74c3c" if pnl < 0 else "#27ae60"
    return f"<span style='color:{color};font-weight:bold'>{sign}{pnl:.2f}%</span>"


def _xueqiu_link(code: str) -> tuple[str, str]:
    """返回 (雪球代码, 雪球链接)。"""
    if code.startswith("6"):
        xq = f"SH{code}"
    elif code.startswith(("4", "8")):
        xq = f"BJ{code}"
    else:
        xq = f"SZ{code}"
    return xq, f"https://xueqiu.com/S/{xq}"


def _build_holdings_table(results: list[StockAnalysis]) -> str:
    """构建持仓股分析表格。"""
    if not results:
        return "<p style='color:#999'>无持仓股</p>"

    action_count = sum(1 for r in results if r.recommendation != "HOLD")

    rows = ""
    for r in results:
        xq_code, link = _xueqiu_link(r.symbol)
        bg = _rec_color(r.recommendation)
        rows += (
            f"<tr style='background:{bg}'>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>"
            f"<a href='{link}' target='_blank' style='text-decoration:none;color:#333'>{r.symbol}</a></td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{r.name}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.current_price)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.stop_loss)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.indicators.get('ma20') if r.indicators else None)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt_pnl(r.pnl_pct)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;font-weight:bold;'>{r.recommendation}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;font-size:12px;'>{r.reason}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{r.trend}</td>"
            f"</tr>"
        )

    return f"""\
    <h3 style="margin-top:20px;margin-bottom:8px;">持仓股（{len(results)} 只，{action_count} 只需操作）</h3>
    <table style="border-collapse:collapse; width:100%; max-width:1000px; font-size:13px;">
      <thead>
        <tr style="background:#f0f0f0;">
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>代码</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>名称</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>现价</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>止损</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>MA20</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>盈亏</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>建议</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>理由</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>趋势</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>"""


def _build_watchlist_table(results: list[StockAnalysis]) -> str:
    """构建观察股分析表格。"""
    if not results:
        return "<p style='color:#999'>无观察股</p>"

    buy_count = sum(1 for r in results if r.recommendation == "BUY")

    rows = ""
    for r in results:
        xq_code, link = _xueqiu_link(r.symbol)
        bg = _rec_color(r.recommendation)
        buy_zone = f"{_fmt(r.buy_zone_low)} ~ {_fmt(r.buy_zone_high)}" if r.buy_zone_low else "-"
        rows += (
            f"<tr style='background:{bg}'>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>"
            f"<a href='{link}' target='_blank' style='text-decoration:none;color:#333'>{r.symbol}</a></td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{r.name}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.current_price)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{buy_zone}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.stop_loss)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.take_profit_1)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{_fmt(r.take_profit_2)}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;font-weight:bold;'>{r.recommendation}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;font-size:12px;'>{r.reason}</td>"
            f"<td style='padding:4px 10px;border:1px solid #ddd;'>{r.trend}</td>"
            f"</tr>"
        )

    return f"""\
    <h3 style="margin-top:20px;margin-bottom:8px;">观察股（{len(results)} 只，{buy_count} 只买入信号）</h3>
    <table style="border-collapse:collapse; width:100%; max-width:1000px; font-size:13px;">
      <thead>
        <tr style="background:#f0f0f0;">
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>代码</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>名称</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>现价</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>买入区间</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>止损</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>目标1</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>目标2</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>建议</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>理由</th>
          <th style='padding:4px 10px;border:1px solid #ddd;text-align:left;'>趋势</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>"""


def build_analysis_email(
    holdings: list[StockAnalysis],
    watchlist_stocks: list[StockAnalysis],
) -> str:
    """生成完整的个股分析 HTML 邮件。"""
    today = date.today().strftime("%Y-%m-%d")
    total = len(holdings) + len(watchlist_stocks)

    hold_action = sum(1 for r in holdings if r.recommendation != "HOLD")
    watch_buy = sum(1 for r in watchlist_stocks if r.recommendation == "BUY")

    summary = (
        f"持仓 {len(holdings)} 只（{hold_action} 只需操作）"
        f" | 观察 {len(watchlist_stocks)} 只（{watch_buy} 只买入信号）"
    )

    holdings_html = _build_holdings_table(holdings)
    watchlist_html = _build_watchlist_table(watchlist_stocks)

    return f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
  <h2>Sequoia-X 个股分析 | {today}</h2>
  <p><b>日期：</b>{today} &nbsp; <b>总计：</b>{total} 只</p>
  <p style="color:#666;font-size:13px;">{summary}</p>
  <hr style="border:none;border-top:1px solid #eee;">
  {holdings_html}
  {watchlist_html}
  <p style="color:#999;font-size:12px;margin-top:24px;">— Sequoia-X V2 个股分析</p>
</body>
</html>"""
