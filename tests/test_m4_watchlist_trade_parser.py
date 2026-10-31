"""M4: except narrowing tests for watchlist.py + trade_parser.py + improvement_logger.py + indevs_client.py + cli.py"""

import sys

import pytest


class TestWatchlistNarrow:
    def test_no_bare_exception(self):
        import inspect
        from modules import watchlist

        assert "except Exception" not in inspect.getsource(watchlist)


class TestTradeParserNarrow:
    def test_no_bare_exception(self):
        import inspect
        from modules import trade_parser

        assert "except Exception" not in inspect.getsource(trade_parser)


class TestImprovementLoggerNarrow:
    def test_no_bare_exception(self):
        import inspect
        from modules import improvement_logger

        assert "except Exception" not in inspect.getsource(improvement_logger)


class TestIndevsClientNarrow:
    def test_no_bare_exception(self):
        import inspect
        from modules import indevs_client

        assert "except Exception" not in inspect.getsource(indevs_client)


class TestCliTopLevelNarrow:
    def test_no_bare_exception(self):
        import inspect
        from modules import cli

        assert "except Exception" not in inspect.getsource(cli)


class TestBacktestSixStepNarrow:
    def test_no_bare_exception(self):
        """裸 except Exception 不得出现在 shaofu 回测实现里。

        v4.8.0 起实现迁至 modules/backtest/shaofu.py；
        modules/backtest_six_step.py 是兼容 re-export，也一并检查。
        """
        import inspect

        from modules.backtest import shaofu
        from modules import backtest_six_step

        assert "except Exception" not in inspect.getsource(shaofu)
        assert "except Exception" not in inspect.getsource(backtest_six_step)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
