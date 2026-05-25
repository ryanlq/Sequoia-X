"""Sequoia-X V2 主程序入口。

四种运行模式：
  python main.py               # 日常模式：8进程增量补数据 + 跑策略 + 邮件推送（2~3分钟）
  python main.py --backfill    # 回填模式：baostock 拉全市场历史K线（首次/补数据用，约12分钟）
  python main.py --sync        # 仅同步模式：拉取最新行情数据，不跑策略不推送
  python main.py --analyze     # 个股分析模式：分析 watchlist.toml 中的持仓和观察股，发送分析邮件
"""

import argparse
import sys
from dotenv import load_dotenv
load_dotenv()

from datetime import date

import socket
socket.setdefaulttimeout(10.0)

from sequoia_x.core.config import get_settings
from sequoia_x.core.logger import get_logger
from sequoia_x.data.engine import DataEngine
from sequoia_x.notify.email import EmailNotifier
from sequoia_x.strategy.base import BaseStrategy
from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
from sequoia_x.strategy.ma_volume import MaVolumeStrategy
from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy
from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
from sequoia_x.strategy.private_placement import PrivatePlacementStrategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequoia-X V2 选股系统")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="回填模式：通过 baostock 拉取全市场历史 K 线（约12分钟）",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="仅同步模式：拉取最新行情数据，不跑策略不推送",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="个股分析模式：分析 watchlist.toml 中的持仓和观察股，发送分析邮件",
    )
    args = parser.parse_args()

    try:
        # 1. 初始化配置
        settings = get_settings()

        # 2. 初始化日志
        logger = get_logger(__name__)
        logger.info("Sequoia-X V2 启动")

        # 3. 初始化数据引擎
        engine = DataEngine(settings)

        if args.backfill:
            # ── 回填模式：单线程保守拉历史 K 线，自动多轮重跑 ──
            logger.info("进入回填模式...")
            all_symbols = engine.get_all_symbols()
            engine.backfill(all_symbols)
            logger.info("Sequoia-X V2 回填模式运行完成")
            return

        # ── 日常模式 / 仅同步模式：拉取最新行情 ──
        logger.info("开始拉取最新快照...")
        count = engine.sync_today_bulk()
        logger.info(f"快照同步完成，写入 {count} 只股票")

        if args.sync:
            logger.info("Sequoia-X V2 仅同步模式运行完成")
            return

        if args.analyze:
            # ── 个股分析模式：同步数据 → 加载关注列表 → 分析 → 推送 ──
            from sequoia_x.analysis.advisor import run_analysis
            from sequoia_x.analysis.report import build_analysis_email
            from sequoia_x.analysis.watchlist import load_watchlist
            from sequoia_x.notify.mail_send import find_mail_send, run_mail_send

            logger.info("进入个股分析模式...")
            wl = load_watchlist(settings.watchlist_path)
            if not wl.holdings and not wl.watchlist:
                logger.info("关注列表为空，跳过分析")
                return

            holdings_results, watchlist_results = run_analysis(engine, wl)
            html = build_analysis_email(holdings_results, watchlist_results)

            exe = find_mail_send(settings.mail_send_path)
            today = date.today()
            total = len(holdings_results) + len(watchlist_results)
            subject = f"Sequoia-X 个股分析 | {today} | {total} 只"
            run_mail_send(exe, settings.mail_to, subject, html)
            logger.info(f"个股分析邮件推送成功，共 {total} 只股票")
            return

        # 4. 策略列表（新增策略在此追加即可）
        strategies: list[BaseStrategy] = [
            MaVolumeStrategy(engine=engine, settings=settings),
            TurtleTradeStrategy(engine=engine, settings=settings),
            HighTightFlagStrategy(engine=engine, settings=settings),
            LimitUpShakeoutStrategy(engine=engine, settings=settings),
            UptrendLimitDownStrategy(engine=engine, settings=settings),
            RpsBreakoutStrategy(engine=engine, settings=settings),
            PrivatePlacementStrategy(engine=engine, settings=settings),
        ]

        notifier = EmailNotifier(settings)

        # 5. 遍历策略，收集所有有结果的策略
        results: dict[str, list[str]] = {}
        for strategy in strategies:
            strategy_name = type(strategy).__name__
            logger.info(f"执行策略：{strategy_name}")

            selected: list[str] = strategy.run()
            logger.info(f"{strategy_name} 选出 {len(selected)} 只股票")

            if selected:
                results[strategy_name] = selected
            else:
                logger.info(f"{strategy_name} 无选股结果，跳过推送")

        # 6. 合并为一封邮件发送
        notifier.send_all(results)

    except Exception:
        try:
            _logger = get_logger(__name__)
            _logger.exception("主流程发生未捕获异常，程序终止")
        except Exception:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    logger.info("Sequoia-X V2 运行完成")


if __name__ == "__main__":
    main()
