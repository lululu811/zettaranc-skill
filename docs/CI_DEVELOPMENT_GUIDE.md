# CI 质量门禁与本地代码开发规范

> 本规范旨在指导开发者在本地开发、修改代码及提交代码时，严格对照 GitHub Actions CI 检查项进行自测，确保所有提交（Push / PR）在 CI 流水线上一次性通过（全绿 ✓），杜绝「本地能跑、CI 挂掉」或反复修格式、修类型的问题。

---

## 1. CI 测试流水线全景解构

仓库通过 GitHub Actions 在 `.github/workflows/test.yml` 与 `rust-ci.yml` 中定义了完整的自动化测试与质量门禁。每次推送分支或提交 Pull Request 均会触发。

### 1.1 `test.yml` 包含的 7 项核心任务

| 任务名称 (Job) | 执行环境 | 触发的命令 / 目标 | 失败判定原因 |
|---|---|---|---|
| **lint** | Python 3.12 | `ruff check modules/ tests/ --select=F,E,W,UP --ignore=E501,F401,F403 --exit-non-zero-on-fix`<br>`ruff format --check modules/ tests/` | 存在语法规范警告、未清除的无用引用、或**代码格式未被 ruff 格式化** |
| **type-check** | Python 3.12 | `python -m mypy modules/ --ignore-missing-imports` | `modules/` 目录下存在任何静态类型推断不兼容错误 |
| **pre-commit** | Python 3.12 | `pre-commit run --all-files --show-diff-on-failure` | 包含 ruff、ruff-format、关键模块更严格的 mypy、版本号一致性、SKILL.md 质量门、行尾及空白符等检查失败 |
| **quality-gate** | Python 3.12 | `python corpus/quality_check.py SKILL.md --strict`<br>`python corpus/dual_axis_review.py SKILL.md --json` | 角色协议 `SKILL.md` 12 项确定性门禁或双轴评审不通过 |
| **test (3.12)** | Python 3.12 | `python -m pytest tests/ -v --tb=short` | 任何单元测试断言失败或异常中断 |
| **test (3.13)** | Python 3.13 | `python -m pytest tests/ -v --tb=short` | 新版 Python 3.13 兼容性测试断言失败 |
| **e2e-realdata** | Python 3.12 | `pytest tests/test_indicators_realdata.py -v --tb=short` | 真实行情指标回归测试失败（无 token 时跳过） |

### 1.2 `rust-ci.yml` 任务（修改 `rust/` 或 `python/` 时触发）

- **cargo fmt --check**：Rust 代码格式规范。
- **cargo clippy**：Rust 严格静态代码检查（`-D warnings`）。
- **cargo test**：Rust 计算核心单元测试。
- **python smoke**：构建 PyO3 扩展 `_core_compute` 并验证 import 正常。

---

## 2. 本地开发环境配置

建议使用 Python 3.12 或 3.13 环境。

```bash
# 1. 安装核心与开发依赖
pip install -r requirements.txt
pip install -e ".[dev]"

# 2. 安装并注册 pre-commit 钩子（强烈推荐）
# 安装后每次 git commit 时会自动运行基础检查，提前拦截问题
pre-commit install
```

---

## 3. 本地提交前标准自检流程（4 步法）

在每次执行 `git commit` 或 `git push` 前，请务必在本地按序运行以下 4 步检查：

### 第 1 步：自动代码格式化与代码质量修复（Ruff）

```bash
# 自动格式化（自动统一单双引号、换行、括号缩进等）
ruff format modules/ tests/

# 自动 lint 检查并安全修复
ruff check modules/ tests/ --select=F,E,W,UP --ignore=E501,F401,F403 --fix
```

> [!IMPORTANT]
> **Ruff Format 与 Ruff Check 是两个独立的检查！**
> `ruff check` 仅检查语法错误与警告，而 CI 的 `lint` 任务中包含 `ruff format --check modules/ tests/`。如果仅执行了 check 而未执行 format，CI 必定挂在 `Format check` 上。

### 第 2 步：静态类型检查（Mypy 双重验证）

```bash
# 1. 全局宽松类型检查（对应 CI 中的 type-check job）
python -m mypy modules/ --ignore-missing-imports

# 2. 关键模块更严格的类型检查（对应 CI 中的 pre-commit mypy hook）
python -m mypy modules/screener modules/cli.py modules/cli_commands modules/data_sync modules/indicators/core.py modules/strategies
```

确保终端输出：`Success: no issues found`。

### 第 3 步：运行单元测试（Pytest）

```bash
# 运行全部单元测试
python -m pytest tests/ -v --tb=short

# 如果只想快速回归你修改的相关模块测试（例如核心指标与同步）：
python -m pytest tests/test_core.py tests/test_data_sync.py -v
```

### 第 4 步：运行 Pre-commit 全量检查与专项门禁

```bash
# 本地模拟 CI 的 pre-commit 全量检查
pre-commit run --all-files

# 如果修改了 SKILL.md，单独运行 12 项质量门
python corpus/quality_check.py SKILL.md --strict

# 如果修改了版本号，单独运行一致性检查
python scripts/check_version_consistency.py
```

---

## 4. 常见 CI 报错根因与防雷指南（避坑手册）

### 4.1 Mypy 类型系统避坑

#### ① 动态获取对象属性放入列表时的类型弱化
- **错误写法**：
  ```python
  # 局部变量未显式声明类型，且可能追加 None
  holding_days_list = []
  for t in trades:
      hd = getattr(t, "holding_days", None)
      holding_days_list.append(hd)
  # 后续传入期待 Sequence[float] 的函数：
  stats = calc_trade_stats(pnls, holding_days_list)
  # 报错：Argument 2 to "calc_trade_stats" has incompatible type "list[Any | None] | None"; expected "Sequence[float] | None"
  ```
- **规范写法**：
  ```python
  # 显式声明列表类型，并在追加时进行空值兜底与显式 float 转换
  holding_days_list: list[float] = []
  for t in trades:
      hd = getattr(t, "holding_days", None) or getattr(t, "hold_days", 0)
      holding_days_list.append(float(hd) if hd is not None else 0.0)

  stats = calc_trade_stats(pnls, holding_days_list if holding_days_list else None)
  ```

#### ② 返回类型标注为 `list[tuple]` 实际却填充了 `list[list]`
- **错误写法**：
  ```python
  def build_records(df: Any) -> list[tuple[Any, ...]]:
      records = []
      for row in df.itertuples():
          records.append([row.a, row.b])  # 内部是 list
      return records  # 报错：got "list[list[Any]]", expected "list[tuple[Any, ...]]"
  ```
- **规范写法**：
  ```python
  def build_records(df: Any) -> list[tuple[Any, ...]]:
      records: list[tuple[Any, ...]] = []
      for row in df.itertuples():
          records.append(tuple([row.a, row.b]))  # 明确构造 tuple
      return records
  ```

#### ③ 针对联合类型或兼容对象的属性访问
- 当函数静态返回类型为 `tuple`，但在代码中保留了向后兼容某对象属性（如 `.j`）的分支时，由于 `tuple` 类型不存在该属性，Mypy 会报 `attr-defined`。
- **错误写法**：
  ```python
  j_val = kdj[2] if isinstance(kdj, tuple) else kdj.j
  ```
- **规范写法**：
  ```python
  from typing import cast, Any
  # 明确使用 cast(Any, ...) 或 getattr 避免 mypy 误报
  j_val = kdj[2] if isinstance(kdj, tuple) else cast(Any, kdj).j
  # 或直接：getattr(kdj, "j", 0.0)
  ```

---

### 4.2 Ruff 格式化避坑

1. **避免行尾空格与空行空白符**：
   - 空行如果包含空格，会触发 `W293 Blank line contains whitespace`。
   - `ruff format modules/ tests/` 会自动去除多余空格与规范换行。
2. **多行条件表达式格式**：
   - 超长 if 条件避免手动使用 `\` 换行，优先使用圆括号包裹条件，交由 `ruff format` 格式化。
3. **不要手动保留不一致的代码风格**：
   - 单双引号统一使用双引号 `"`。
   - 依赖导入顺序由 ruff 统一管理。

---

### 4.3 版本号修改规范（7 处必须一致）

修改版本号时，**禁止**仅修改 `pyproject.toml`。CI 的 `pre-commit` 会强制执行 `check-version-consistency`。

必须同步更新以下文件中的版本号：
1. `pyproject.toml`（`version = "x.y.z"`）
2. `skill.json`（`"version": "x.y.z"`）
3. `SKILL.md`（frontmatter `Version: x.y.z` 以及「版本与追踪」表格）
4. `docs/CHANGELOG.md`（顶端最新版本标题）
5. `README.md`（版本 badge）
6. `AGENTS.md`（当前版本描述行）
7. `docs/INDEX.md`（维护规则与版本）

更新后运行 `python scripts/check_version_consistency.py` 验证。

---

### 4.4 严禁使用 `--no-verify`

在执行 `git commit` 时，**严禁添加 `--no-verify` 跳过本地 hooks**。
跳过本地 hook 只会将错误推迟到 GitHub Actions 远端，不仅占用 GitHub Runner 队列，还会导致 PR 出现红叉并打断集成节奏。如果 pre-commit 报错，必须根据提示修复问题。

---

## 5. 一键本地自检脚本

项目在 `scripts/` 目录下提供了快捷自检脚本 `scripts/ci_check.sh`。在每次准备 push 前，可直接运行：

```bash
bash scripts/ci_check.sh
```

该脚本会自动执行：
1. `ruff format --check`
2. `ruff check`
3. `mypy`（全局 + 关键模块）
4. 版本一致性检查
5. SKILL.md 质量门检查
6. 核心单元测试

全绿即可放心推送！
