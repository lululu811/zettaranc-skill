# 贡献指南

感谢你对 zettaranc（万千）· skill 的兴趣！以下是几种贡献方式：

## 1. 报告问题

如果你发现：
- Skill 的回答不符合 zettaranc 的说话风格
- 心智模型或决策启发式有事实错误
- 某个交易规则描述不准确

请在 Issues 中提交，尽量附上：
- 触发问题的具体提问
- Skill 的实际回答
- 你认为正确的回答方向（如有依据更佳）

## 2. 补充语料

zettaranc 持续输出内容，如果你有新的高质量语料：

- **一手语料**：zettaranc 本人的视频 transcript、直播录屏文字稿、付费课笔记
- **时间跨度**：2026 年 4 月之后的新内容
- **格式要求**：尽量提供原文，标注来源和时间

请将语料整理为 Markdown 文件，通过 PR 描述或附件形式提交（由于版权和体积原因，原始语料不直接存入仓库，但会在后续蒸馏迭代中使用）。

## 3. 优化 SKILL.md

如果你想直接改进 Skill 的表现：

1. 先阅读 `SKILL.md` 和 `references/research/` 下的调研文件
2. 修改 `SKILL.md` 中的相关部分
3. 在 PR 中说明修改依据（引用具体语料来源）

**修改原则**：
- 最小改动原则：只改确实不准确的部分
- 有依据：任何改动都需要语料支撑，不能凭印象
- 保持角色一致性：修改后的回答仍需符合 zettaranc 的表达 DNA

## 4. 翻译

如果你想将 README 或 SKILL.md 翻译为其他语言：
- 直接提交翻译文件（如 `README_EN.md`）
- 注意投资术语的准确性（如「少妇战法」「四块砖」等专有名词保留中文或加注）

## 风格验证清单

提交 PR 前，用以下问题自检修改后的回答是否符合 zettaranc 风格：

- [ ] 是否用「我」而非「Z 哥认为...」？
- [ ] 是否包含职业背书开场？
- [ ] 是否分 1/2/3/4 点拆解？
- [ ] 是否用了具体数字或案例？
- [ ] 是否以金句或反问收尾？
- [ ] 是否避免「如果 Z 哥，他可能会...」这类跳出角色的表述？
- [ ] 交易建议是否包含具体的进场/止损/止盈规则？

## 开发流程

```bash
# 1. Fork 本仓库
# 2. 克隆到本地
git clone https://github.com/YOUR_USERNAME/zettaranc-perspective.git

# 3. 修改 SKILL.md 或添加语料

# 4. 本地测试（如果你有 Claude Code / Kimi Code CLI）
npx skills add ./SKILL.md
# 然后提问验证修改效果

# 5. 提交 PR
```

## 语料来源黑名单

为保证信息质量，以下来源**不应**作为主要依据：
- 知乎回答（可作为二手交叉验证，但不能作为核心来源）
- 微信公众号（除 zettaranc 本人账号外）
- 百度百科/搜狗百科（仅用于快速事实校验）
- 股吧/雪球帖子（除 zettaranc 本人账号外）

优先来源：
- zettaranc 本人直接产出（视频、直播、付费课、雪球专栏）
- 权威媒体报道（澎湃新闻等）
- 证券业协会公示资料等一手公开记录

---

## Rust 核心构建（`_core_compute`）

> 适用对象：在 macOS / Linux 上修改 `rust/crates/*` 后需要重新编译 PyO3 扩展的开发者。

### 1. 工具链要求

| 工具 | 版本 | 安装 |
| --- | --- | --- |
| Rust | stable（≥ 1.78；推荐 1.97+） | `rustup install stable && rustup default stable` |
| maturin | 1.14.x | `pip install 'maturin>=1.5,<2'`（或 `brew install maturin`） |
| PyO3 | 0.22（已在 `rust/Cargo.toml` 锁定） | 由 maturin 拉取 |
| Python | 3.11 | `brew install python@3.11`（macOS） / 系统包（Linux） |
| lld | 22+ | `brew install lld`（macOS） / `apt install lld`（Linux） |

> **macOS 用户特别注意**：`rust-toolchain.toml` 已 pin 到 `stable`（即 1.97.x）。如果你的 `rustup default` 是别的 channel，请在 `rust/` 下用 `rustup show` 确认。

### 2. macOS 构建（含 LINKEDIT 修复）

macOS 15+ 的 dyld 强制要求 `LC_SYMTAB.stroff` 必须是 8 字节对齐，而 lld 22.x 输出的 .so 实际只 4 字节对齐，会直接 `dlopen` 失败并报：

```
ImportError: dlopen(...): mis-aligned LINKEDIT string pool
```

我们用一个 build 脚本把所有 workaround 串起来：

```bash
# 在 rust/ 目录下：
./scripts/build_macos.sh
# 等价于：maturin develop --release
#       + python3 scripts/fix_linkedit_alignment.py <.so>
#       + codesign --force --sign - <.so>
#       + python -c "import _core_compute"
```

如果你想手动逐步走：

```bash
# Step 1: 装 Python 3.11 venv + maturin
python3.11 -m venv /tmp/venv311
/tmp/venv311/bin/pip install 'maturin>=1.5,<2'

# Step 2: 构建（需要 PYO3_PYTHON 指向 3.11）
export PYO3_PYTHON=/tmp/venv311/bin/python
cd rust/crates/bindings
maturin develop --release

# Step 3: 修复 LINKEDIT 对齐
python3 ../../scripts/fix_linkedit_alignment.py \
    /tmp/venv311/lib/python3.11/site-packages/_core_compute/_core_compute.cpython-311-darwin.so

# Step 4: 重新签名（修复破坏了原签名）
codesign --remove-signature /tmp/venv311/lib/python3.11/site-packages/_core_compute/_core_compute.cpython-311-darwin.so
codesign --force --sign - /tmp/venv311/lib/python3.11/site-packages/_core_compute/_core_compute.cpython-311-darwin.so

# Step 5: 验证
/tmp/venv311/bin/python -c "import _core_compute; print(_core_compute.rust_smoke())"
```

### 3. Linux 构建（Docker 推荐）

Linux 没有 Mach-O LINKEDIT 校验问题，标准 `maturin develop/build` 即可，但推荐用我们提供的 Dockerfile 来获得一致的 Rust 工具链版本：

```bash
docker build -f rust/Dockerfile.test -t zt-rust-builder .
docker run --rm -v "$(pwd):/src" zt-rust-builder bash /src/rust/scripts/build-linux.sh
# 产物在 ./dist/*.whl
```

### 4. 排错清单

| 报错 | 原因 | 解决 |
| --- | --- | --- |
| `the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)` | `python3` 默认是 3.14 | 显式 `export PYO3_PYTHON=/path/to/python3.11` |
| `missing field 'package'` (maturin) | maturin 1.14.x 对新版 cargo workspace 字段敏感 | 切换到 `rust/crates/bindings` 子目录运行 maturin |
| `unknown binary 'rustc' in toolchain` | rustup toolchain 没装好 | `rustup show` 检查 + `rustup default stable` |
| `code signature invalid` | 跑了 `fix_linkedit_alignment.py` 但没重签 | `codesign --force --sign - <.so>` |
| `symbol(s) not found` (Apple ld) | 同时启用了 `linker = rust-lld` 和 `-fuse-ld` | 二选一；推荐用 `link-arg=-fuse-ld=…` 让 clang 调度 |

### 5. 跑 workspace 测试

```bash
export PYO3_PYTHON=/opt/homebrew/bin/python3.11
cd rust
cargo test --workspace --release
# 应当看到 24 个 test 全过
```

---

如有疑问，欢迎在 Discussions 中交流。

Love and Share 🖤
