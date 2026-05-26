"""数据引擎模块：负责 SQLite 行情数据存储，支持 baostock + akshare 双数据源。"""

import sqlite3
from pathlib import Path

import pandas as pd

from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_daily (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   REAL,
    turnover REAL,
    UNIQUE (symbol, date)
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_daily (symbol, date);
"""


def _bs_fetch_batch(tasks: list) -> list:
    """多进程 worker：独立 login，批量拉取 baostock 数据。"""
    import baostock as bs

    bs.login()
    results = []
    for symbol, bs_code, start, end in tasks:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="1",  # 后复权
        )
        if rs.error_code != "0":
            continue
        while rs.next():
            results.append([symbol] + rs.get_row_data())
    bs.logout()
    return results


def _write_df_to_db(db_path: str, df: pd.DataFrame) -> int:
    """将 DataFrame 写入 SQLite，先删除同日期旧数据再追加。返回写入条数。"""
    if df.empty:
        return 0
    count = len(df)
    with sqlite3.connect(db_path) as conn:
        for d in df["date"].unique().tolist():
            conn.execute("DELETE FROM stock_daily WHERE date = ?", (d,))
        df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=500)
        conn.commit()
    return count


class DataEngine:
    """行情数据引擎，负责 SQLite 存储和双源数据同步（baostock + akshare）。"""

    def __init__(self, settings: Settings) -> None:
        self.db_path: str = settings.db_path
        self.start_date: str = settings.start_date
        self._akcli_path: str | None = None  # lazy init
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
        logger.info(f"数据库初始化完成：{self.db_path}")

    def _get_last_date(self, symbol: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM stock_daily WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return row[0] if row and row[0] else None

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql(
                "SELECT * FROM stock_daily WHERE symbol = ? ORDER BY date",
                conn,
                params=(symbol,),
            )
        return df

    @staticmethod
    def _to_baostock_code(symbol: str) -> str:
        """将纯数字代码转为 baostock 格式：6/9开头 -> sh，其余 -> sz。"""
        prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
        return f"{prefix}.{symbol}"

    def _get_akcli(self) -> str | None:
        """获取 ak CLI 路径，首次调用时自动检测并安装。"""
        if self._akcli_path is not None:
            return self._akcli_path
        from sequoia_x.data.akshare_source import ensure_akcli, _find_akcli
        path = _find_akcli()
        if not path:
            try:
                path = ensure_akcli()
            except Exception as e:
                logger.warning(f"ak CLI 不可用: {e}")
                self._akcli_path = ""  # 标记为不可用，不再重试
                return None
        self._akcli_path = path
        return path

    # ── 数据同步 ──

    def sync_today_bulk(self) -> int:
        """多进程并行拉取增量数据（后复权），写入 SQLite。

        双源策略：先尝试 baostock，失败后自动切换 akshare。
        """
        from datetime import date, datetime, timedelta
        from multiprocessing import Pool

        today = date.today()
        today_str = today.strftime("%Y-%m-%d")

        # A 股 15:00 收盘，数据源约 15:30 后更新，取 16:00 作为安全阈值
        if datetime.now().hour < 16:
            logger.warning(
                f"当前时间 {datetime.now().strftime('%H:%M')}，"
                "A 股尚未收盘（或数据未更新），跳过当日同步。"
                "请在 16:00 后重新运行。"
            )
            return 0

        tasks = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol"
            ).fetchall()

        if not rows:
            logger.warning("本地无股票数据，请先执行 backfill")
            return 0

        for symbol, last_date in rows:
            if last_date and last_date >= today_str:
                continue
            start = today_str
            if last_date:
                start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")
            tasks.append((symbol, self._to_baostock_code(symbol), start, today_str))

        if not tasks:
            logger.info("所有股票已是最新，无需更新")
            return 0

        logger.info(f"需要更新 {len(tasks)} 只股票...")

        # ── 尝试 baostock ──
        all_rows: list = []
        bs_failed = False
        try:
            n_workers = min(8, len(tasks))
            chunks = [tasks[i::n_workers] for i in range(n_workers)]
            with Pool(n_workers) as pool:
                batch_results = pool.map(_bs_fetch_batch, chunks)
            for batch in batch_results:
                all_rows.extend(batch)
        except Exception as e:
            logger.warning(f"baostock 同步失败: {e}")
            bs_failed = True

        # ── baostock 无数据时切换 akshare ──
        if not all_rows:
            logger.info("baostock 无数据，尝试 akshare...")
            akcli = self._get_akcli()
            if akcli:
                from sequoia_x.data.akshare_source import fetch_kline_akshare_batch

                ak_tasks = [(sym, start, end) for sym, _, start, end in tasks]
                df = fetch_kline_akshare_batch(ak_tasks, akcli_path=akcli)
                if not df.empty:
                    count = _write_df_to_db(self.db_path, df)
                    logger.info(f"akshare 同步完成，写入 {count} 条数据")
                    return count
                else:
                    logger.warning("akshare 也无数据（可能非交易日）")
                    return 0
            elif bs_failed:
                logger.error("baostock 失败且 akshare 不可用，同步中止")
                return 0
            else:
                logger.info("无新数据（可能非交易日）")
                return 0

        df = pd.DataFrame(
            all_rows,
            columns=["symbol", "date", "open", "high", "low", "close", "volume", "turnover"],
        )
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df[df["volume"] > 0]

        count = _write_df_to_db(self.db_path, df)
        logger.info(f"baostock 同步完成，写入 {count} 条数据")
        return count

    def _backfill_one_bs(self, symbol: str, bs_code: str, start: str, end: str) -> pd.DataFrame:
        """用 baostock 回填单只股票，失败返回空 DataFrame。"""
        import time
        import baostock as bs

        max_retries = 3
        for attempt in range(max_retries):
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount",
                    start_date=start,
                    end_date=end,
                    frequency="d",
                    adjustflag="1",
                )
                if rs.error_code != "0":
                    raise RuntimeError(rs.error_msg)
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows, columns=rs.fields)
                for col in ["open", "high", "low", "close", "volume", "amount"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"])
                df = df[df["volume"] > 0]
                if df.empty:
                    return pd.DataFrame()
                df["symbol"] = symbol
                df = df.rename(columns={"amount": "turnover"})
                return df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]]
            except Exception as exc:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"[{symbol}] baostock 第{attempt + 1}次失败: {exc}，{wait}s 后重试")
                    time.sleep(wait)
                    bs.logout()
                    time.sleep(1)
                    bs.login()
                else:
                    logger.warning(f"[{symbol}] baostock {max_retries}次重试均失败")
        return pd.DataFrame()

    def _backfill_one_ak(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """用 akshare 回填单只股票。"""
        akcli = self._get_akcli()
        if not akcli:
            return pd.DataFrame()
        from sequoia_x.data.akshare_source import fetch_kline_akshare
        return fetch_kline_akshare(symbol, start, end, akcli_path=akcli)

    def backfill(self, symbols: list[str]) -> None:
        """批量回填历史日 K 线数据，支持 baostock + akshare 双源切换。

        策略：先用 baostock，单只失败后自动切换 akshare 重试。
        """
        import time
        from datetime import date, timedelta

        import baostock as bs

        today_str = date.today().strftime("%Y-%m-%d")
        reconnect_interval = 200

        def _login():
            lg = bs.login()
            if lg.error_code != "0":
                logger.error(f"baostock 登录失败: {lg.error_msg}")
                return False
            return True

        if not _login():
            # baostock 完全不可用，尝试全量用 akshare
            logger.warning("baostock 登录失败，尝试全部使用 akshare...")
            self._backfill_akshare_only(symbols, today_str)
            return

        success = 0
        skipped = 0
        failed = 0
        ak_fallback = 0
        since_reconnect = 0

        try:
            for i, symbol in enumerate(symbols):
                last_date = self._get_last_date(symbol)
                if last_date and last_date >= today_str:
                    skipped += 1
                    if (i + 1) % 500 == 0:
                        logger.info(
                            f"已处理 {i + 1}/{len(symbols)}，"
                            f"成功 {success} 跳过 {skipped} 失败 {failed} akshare替补 {ak_fallback}"
                        )
                    continue

                since_reconnect += 1
                if since_reconnect >= reconnect_interval:
                    bs.logout()
                    time.sleep(1)
                    if not _login():
                        logger.error("重连失败，切换到 akshare 继续剩余股票")
                        remaining = symbols[i:]
                        self._backfill_akshare_only(remaining, today_str)
                        return
                    since_reconnect = 0

                start = last_date or self.start_date
                if last_date:
                    start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")

                bs_code = self._to_baostock_code(symbol)

                # 先尝试 baostock
                df = self._backfill_one_bs(symbol, bs_code, start, today_str)

                # baostock 失败，切换 akshare
                if df.empty:
                    df_ak = self._backfill_one_ak(symbol, start, today_str)
                    if not df_ak.empty:
                        df = df_ak
                        ak_fallback += 1
                    else:
                        failed += 1
                        continue

                try:
                    with sqlite3.connect(self.db_path) as conn:
                        df.to_sql(
                            "stock_daily", conn, if_exists="append",
                            index=False, method="multi", chunksize=500,
                        )
                except sqlite3.IntegrityError:
                    pass

                success += 1

                if (i + 1) % 500 == 0:
                    logger.info(
                        f"已处理 {i + 1}/{len(symbols)}，"
                        f"成功 {success} 跳过 {skipped} 失败 {failed} akshare替补 {ak_fallback}"
                    )

        finally:
            try:
                bs.logout()
            except Exception:
                pass

        logger.info(
            f"回填完成 — 成功: {success} | 跳过: {skipped} | "
            f"失败: {failed} | akshare替补: {ak_fallback}"
        )

    def _backfill_akshare_only(self, symbols: list[str], today_str: str) -> None:
        """纯 akshare 回填，用于 baostock 完全不可用时。"""
        from datetime import date, timedelta

        success = 0
        skipped = 0
        failed = 0

        for i, symbol in enumerate(symbols):
            last_date = self._get_last_date(symbol)
            if last_date and last_date >= today_str:
                skipped += 1
                continue

            start = last_date or self.start_date
            if last_date:
                start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")

            df = self._backfill_one_ak(symbol, start, today_str)
            if df.empty:
                failed += 1
                continue

            try:
                with sqlite3.connect(self.db_path) as conn:
                    df.to_sql(
                        "stock_daily", conn, if_exists="append",
                        index=False, method="multi", chunksize=500,
                    )
            except sqlite3.IntegrityError:
                pass

            success += 1

            if (i + 1) % 100 == 0:
                logger.info(
                    f"[akshare] 已处理 {i + 1}/{len(symbols)}，"
                    f"成功 {success} 跳过 {skipped} 失败 {failed}"
                )

        logger.info(
            f"[akshare] 回填完成 — 成功: {success} | 跳过: {skipped} | 失败: {failed}"
        )

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        """通过 baostock 获取全市场 A 股代码列表。"""
        import baostock as bs

        lg = bs.login()
        if lg.error_code != "0":
            logger.error(f"baostock 登录失败: {lg.error_msg}")
            return []

        try:
            rs = bs.query_stock_basic(code_name="", code="")
            symbols = []
            while rs.next():
                row = rs.get_row_data()
                code = row[0]
                status = row[4]
                stock_type = row[5]
                if status == "1" and stock_type == "1":
                    symbols.append(code.split(".")[1])
            logger.info(f"获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
        finally:
            bs.logout()

    def get_local_symbols(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM stock_daily"
            ).fetchall()
        return [row[0] for row in rows]
