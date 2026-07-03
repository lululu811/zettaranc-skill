# Phase B.0 实施报告 — DataSource Protocol 与实现

## 完成的功能

按照任务简报创建了 `modules/datasource.py` 与 `tests/test_datasource.py`：

- **Protocol 定义**：`DataSource` 使用 `@runtime_checkable` 装饰，包含 `name` 属性、`health_check()` 以及 10 个数据查询方法。
- **TushareDataSource**：包装 `modules.tushare_client.TushareClient`，完整映射日线/指数/实时行情/资金流向/股票基础/交易日历；`get_daily_basic` 与 `get_stk_factor` 按简报要求直接访问 `client._pro`。
- **BridgeDataSource**：包装 `modules.bridge_client`，仅实现 `health_check()`、`get_kline_dicts()`、`get_stock_list()`，其余方法返回 `None`。
- **SqliteDataSource**：直接查询本地 SQLite 的 `daily_kline` 与 `stock_basic` 表，提供 K 线字典与股票列表。
- **CompositeDataSource**：支持 `preferred="auto" | "bridge" | "sqlite" | "tushare"`，对 `get_kline_dicts` 与 `get_stock_list` 按优先级回退；`auto` 策略为 bridge → sqlite → tushare。
- **工厂函数**：`get_datasource(preferred="auto")` 按名称返回对应数据源实现。

## 测试命令与结果

```bash
.venv/bin/python -m pytest tests/test_datasource.py -v
```

结果：

```
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.0.3, pluggy-1.6.0 -- .venv/bin/python
configfile: pyproject.toml
collected 7 items

tests/test_datasource.py::test_datasource_protocol_runtime_checkable PASSED [ 14%]
tests/test_datasource.py::test_tushare_datasource_name PASSED            [ 28%]
tests/test_datasource.py::test_bridge_datasource_name PASSED             [ 42%]
tests/test_datasource.py::test_sqlite_datasource_name PASSED             [ 57%]
tests/test_datasource.py::test_composite_prefers_bridge_when_available PASSED [ 71%]
tests/test_datasource.py::test_composite_falls_back_to_sqlite PASSED     [ 85%]
tests/test_datasource.py::test_get_datasource_factory PASSED             [100%]

============================== 7 passed in 2.97s ===============================
```

## Lint 结果

```bash
.venv/bin/python -m ruff check modules tests --output-format=concise
```

结果：`All checks passed!`

## Mypy 结果

```bash
.venv/bin/python -m mypy modules/ --ignore-missing-imports
```

结果：`Success: no issues found in 61 source files`

## 遇到的问题或假设

1. **简报文件位置**：任务简报 `.superpowers/sdd/task-b0-brief.md` 位于主项目根目录，而非本次工作区 `.worktrees/refactor-datasource` 内。实施前已从主项目根目录读取该简报，所有实现严格遵循其中要求。
2. **虚拟环境位置**：工作区根目录没有独立的 `.venv`。为执行简报要求的 `.venv/bin/python ...` 命令，在工作区内创建了指向主项目 `.venv` 的符号链接（已加入 worktree 的 `info/exclude`，不会进入提交）。
3. **Bridge 方法降级**：`BridgeDataSource` 对未在 bridge_client 中提供的方法统一返回 `None`，与简报一致。
4. **Tushare 私有属性访问**：`get_daily_basic` / `get_stk_factor` 按简报要求访问 `TushareClient._pro`；在 `DATA_MODE=websearch` 测试环境下 `_pro` 为 `None`，实现中做了防御性判断。

## 提交信息

```
feat(datasource): Phase B.0 DataSource Protocol + Tushare/Bridge/SQLite/Composite implementations
```

## 提交哈希

`90e1956`
