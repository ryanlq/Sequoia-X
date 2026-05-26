"""CLI 入口属性测试。"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from typer.testing import CliRunner

import sequoia_x.cli as cli_module

runner = CliRunner()


# Feature: sequoia-x-v2, Property 13: 主程序异常以非零退出码终止
@given(error_msg=st.text(min_size=1, max_size=100))
@h_settings(max_examples=30, deadline=None)
def test_main_exits_nonzero_on_exception(error_msg: str) -> None:
    """属性 13：CLI 命令中任意未捕获异常应导致非零退出码。"""
    with patch("sequoia_x.cli._get_deps", side_effect=RuntimeError(error_msg)):
        result = runner.invoke(cli_module.app, ["daily"])
        assert result.exit_code != 0


def test_sync_json_output() -> None:
    """--format json 应输出合法 JSON。"""
    import json

    with patch("sequoia_x.cli._get_deps") as mock_deps:
        from unittest.mock import MagicMock

        engine = MagicMock()
        engine.sync_today_bulk.return_value = 42
        mock_deps.return_value = (engine, MagicMock(), MagicMock())

        result = runner.invoke(cli_module.app, ["sync", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["synced"] == 42


def test_scan_json_output() -> None:
    """scan --format json 应输出策略结果 JSON。"""
    import json

    with patch("sequoia_x.cli._get_deps") as mock_deps:
        with patch("sequoia_x.cli._run_all_strategies") as mock_run:
            mock_run.return_value = {"MaVolumeStrategy": ["600519", "000858"]}
            mock_deps.return_value = (MagicMock(), MagicMock(), MagicMock())

            result = runner.invoke(cli_module.app, ["scan", "--format", "json", "--no-email"])

            result = runner.invoke(cli_module.app, ["scan", "--format", "json", "--no-email"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "strategies" in data
            assert data["strategies"]["MaVolumeStrategy"] == ["600519", "000858"]


def test_strategy_list_json() -> None:
    """strategy list --format json 应列出所有策略。"""
    import json

    result = runner.invoke(cli_module.app, ["strategy", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 7
    names = [e["name"] for e in data]
    assert "MaVolumeStrategy" in names
    assert "TurtleTradeStrategy" in names


def test_strategy_run_unknown() -> None:
    """运行未知策略应返回非零退出码。"""
    result = runner.invoke(cli_module.app, ["strategy", "run", "NonExistent"])
    assert result.exit_code != 0
    assert "未知策略" in result.output or "Unknown" in result.output.lower()


def test_kline_no_data() -> None:
    """查询单股无数据时应返回非零退出码。"""
    from unittest.mock import MagicMock
    import pandas as pd

    with patch("sequoia_x.cli._get_deps") as mock_deps:
        engine = MagicMock()
        engine.get_ohlcv.return_value = pd.DataFrame()
        mock_deps.return_value = (engine, MagicMock(), MagicMock())

        result = runner.invoke(cli_module.app, ["kline", "999999"])
        assert result.exit_code != 0


def test_compare_needs_two_symbols() -> None:
    """compare 至少需要 2 只股票。"""
    result = runner.invoke(cli_module.app, ["compare", "600519"])
    assert result.exit_code != 0


def test_watchlist_show_json() -> None:
    """watchlist show --format json 应输出结构化数据。"""
    import json
    from sequoia_x.analysis.watchlist import Watchlist, WatchlistEntry

    with patch("sequoia_x.core.config.get_settings") as mock_settings:
        mock_settings.return_value.watchlist_path = "watchlist.toml"
        with patch("sequoia_x.analysis.watchlist.load_watchlist") as mock_wl:
            mock_wl.return_value = Watchlist(
                holdings=[WatchlistEntry(symbol="600519", name="贵州茅台", cost_price=1800.0)],
                watchlist=[],
            )
            result = runner.invoke(cli_module.app, ["watchlist", "show", "--format", "json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["holdings"]) == 1
            assert data["holdings"][0]["symbol"] == "600519"
