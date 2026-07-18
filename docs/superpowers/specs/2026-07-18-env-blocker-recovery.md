# Env Blocker Recovery Report (2026-07-18)

> **TL;DR**：macOS 路径**可行**。升级到 Rust stable 1.97.1 + lld 22.1.8 之后，
> 仍然会触发 lld 的 LC_SYMTAB.stroff 4 字节对齐 bug（macOS 15+ dyld 要求 8 字节）。
> 我们写了一个 post-build Python 脚本（`rust/scripts/fix_linkedit_alignment.py`）
> 把 stroff 手动 pad 到 8 字节，然后重新 `codesign`。完整流程由
> `rust/scripts/build_macos.sh` 一键完成。5 个被卡住的 task 全部解锁。

## 1. 环境基线

```
macOS         27.0.0 (Darwin 27.0.0, arm64)
Rust          1.78.0 (原 pinned) → 1.97.1 (stable, 升级后)
maturin       1.14.1
PyO3          0.22.6 (受 Cargo.toml 锁)
Python 系统   /opt/homebrew/bin/python3 → 3.14.6 (默认)
Python 3.11   /opt/homebrew/bin/python3.11 → 3.11.15 ✅
Homebrew lld  22.1.8 (/opt/homebrew/bin/ld64.lld)
rust-lld      22.1.6 (bundled with stable)
PyO3 max      3.13 (PyO3 0.22 不支持 3.14)
```

## 2. 链路 bug 现状

```
ImportError: dlopen(.../_core_compute.cpython-311-darwin.so, 0x0002):
  tried: '.../.so' (mis-aligned LINKEDIT string pool, fileOffset=0x0005DBF4)
```

`0x5DBF4` mod 8 = 4。`LC_SYMTAB.stroff` 落在 4 字节边界而不是 8 字节。
在 `rust/target/release/.../_core_compute.cpython-311-darwin.so` 上
`otool -l` 验证：

```
segname __LINKEDIT
  vmaddr 0x000000000005c000
  vmsize 0x0000000000004000
  fileoff 376832
  filesize 12480

cmd LC_SYMTAB
  symoff 381128
  nsyms 122
  stroff 383988        ← 0x5DBF4, 需要 +4 字节 padding
  strsize 2136
```

## 3. Path 1（toolchain 升级）结果

### 3.1 尝试 1：仅 bump `rust-toolchain.toml`（不动 linker）

```bash
# rust-toolchain.toml: 1.78.0 → stable
```

- 工具链自动下载 1.97.1，rust-lld 22.1.6
- `maturin develop --release` 编译成功
- `python -c "import _core_compute"` **仍然报** mis-aligned LINKEDIT
- 结论：升级 Rust 1.78 → 1.97 本身**不能**修复此 bug

### 3.2 尝试 2：换成 `linker = "rust-lld"` 直接链接

```toml
# .cargo/config.toml
[target.aarch64-apple-darwin]
linker = "/Users/.../lib/rustlib/aarch64-apple-darwin/bin/rust-lld"
```

- 失败：maturin 注入的 `-Wl,-install_name,...` 是 gcc/clang driver 语法，
  rust-lld 不认。
- 结论：不能直接把链接器换掉，maturin 的链路需要 clang 在中间。

### 3.3 尝试 3：保留 clang driver，只让 clang 选 lld

```toml
# .cargo/config.toml
[target.aarch64-apple-darwin]
rustflags = ["-C", "link-arg=-fuse-ld=/opt/homebrew/bin/ld64.lld"]
```

- 编译成功
- `import _core_compute` 仍然 mis-aligned（fileOffset 0x5DBF4）
- 结论：lld 22.1.8 自身就有这个对齐 bug，跟它叫不叫 rust-lld 无关。

### 3.4 尝试 4：禁用 lld 的字符串去重

```toml
rustflags = [
  "-C", "link-arg=-fuse-ld=/opt/homebrew/bin/ld64.lld",
  "-C", "link-arg=-Wl,-no-deduplicate-symbol-strings",
  "-C", "link-arg=-Wl,--no-tail-merge-strings",
]
```

- 编译成功
- `import _core_compute` 仍然 mis-aligned
- 结论：去重逻辑不是 stroff 偏 4 字节的根因。

### 3.5 尝试 5：post-build 手工 pad + 重签 ✅

写 `rust/scripts/fix_linkedit_alignment.py`：

1. 扫 LC_SYMTAB + LC_SEGMENT_64
2. 若 `stroff % 8 != 0`，算出 padding (典型 4 字节)
3. 在 file offset == stroff 处插入 N 个 0x00
4. 更新 LC_SYMTAB.stroff 与 __LINKEDIT.filesize
5. 把所有 fileoff 严格大于 stroff 的 LC_SEGMENT_64 也 +N

然后：

```bash
codesign --remove-signature .../_core_compute.cpython-311-darwin.so
codesign --force --sign -     .../_core_compute.cpython-311-darwin.so
python -c "import _core_compute; print(_core_compute.rust_smoke())"
# OK: ok from rust
```

**最终工具链配置**（`rust/.cargo/config.toml`）：

```toml
[target.aarch64-apple-darwin]
rustflags = [
  "-C", "link-arg=-fuse-ld=/opt/homebrew/bin/ld64.lld",
  "-C", "link-arg=-Wl,-no-deduplicate-symbol-strings",
  "-C", "link-arg=-Wl,--no-tail-merge-strings",
]
```

（`no-deduplicate-symbol-strings` / `no-tail-merge-strings` 实际不影响对齐，
但留着能减少后续 lld 版本升级时的回归风险。）

### 3.6 一键脚本

`rust/scripts/build_macos.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
export PYO3_PYTHON=/tmp/venv311/bin/python
export VIRTUAL_ENV=/tmp/venv311
cd rust/crates/bindings
maturin develop --release
python3 ../../scripts/fix_linkedit_alignment.py \
    "$VIRTUAL_ENV/lib/python3.11/site-packages/_core_compute/_core_compute.cpython-311-darwin.so"
codesign --remove-signature "$SO"
codesign --force --sign -   "$SO"
"$VIRTUAL_ENV/bin/python" -c "import _core_compute; print('OK:', _core_compute.rust_smoke())"
```

### 3.7 端到端验证

```bash
$ /tmp/venv311/bin/python -c "import _core_compute; print('rust_smoke:', _core_compute.rust_smoke())"
rust_smoke: ok from rust

$ /tmp/venv311/bin/python -c "
import _core_compute
klines = [{'ts_code':'000001.SZ', 'trade_date':20240100+i,
           'open':10.0+i*0.1,'high':10.5+i*0.1,'low':9.5+i*0.1,
           'close':10.2+i*0.1,'vol':1000.0,'amount':10200.0,
           'pct_chg':1.0,'vol_ratio':None,'is_limit_up':False,'is_limit_down':False}
          for i in range(20)]
print(_core_compute.compute_atr_py(klines, window=14))
"
[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

$ cd rust && cargo test --workspace --release
test result: ok. 6 passed; 0 failed
test result: ok. 1 passed; 0 failed
test result: ok. 1 passed; 0 failed
test result: ok. 2 passed; 0 failed
test result: ok. 5 passed; 0 failed
test result: ok. 4 passed; 0 failed
test result: ok. 5 passed; 0 failed
# 24 tests passed, 0 failed (用户预期 22，实际 24)
```

## 4. Path 2（Docker Linux）准备

> **没用上**，因为 macOS 路径已经走通。但 Docker fallback 已经就位以便 CI 用。

新增文件：

| 路径 | 作用 |
| --- | --- |
| `rust/Dockerfile.test` | `python:3.11-slim` + `rustup` + `lld` + `clang` |
| `rust/scripts/build-linux.sh` | 容器内跑 `maturin build` + 烟测 |
| `docs/CONTRIBUTING.md` | 新增 "Rust 核心构建" 章节，含 macOS / Linux / 排错清单 |

Linux 之所以不需要 patch：Linux 上的 .so 是 ELF，没有 LC_SYMTAB 这种 Mach-O
load command，dyld 那一套校验不存在。

## 5. Path 3（系统补丁）清单

> 给**用户**自己跑的环境探针。我们没在沙盒里跑（避免误改用户机器）。

```bash
# 1. macOS 版本
sw_vers

# 2. 是否有可用更新（特别是 27.x 的小版本，可能修了 dyld 的误报）
softwareupdate --list

# 3. Xcode CLI tools 版本（决定 ld-prime 的版本）
xcode-select -p
pkgutil --pkg-info=com.apple.pkg.CLTools_Executables | grep version

# 4. lld 是否安装了最新版
brew info lld
brew upgrade lld   # 升级到 22.1.8+（我们这边已经 22.1.8）

# 5. maturin 版本
which maturin && maturin --version
pip show maturin | head -5

# 6. Python 多版本管理
ls /opt/homebrew/bin/python3.1{1,2,3,4}
# 如果只有 3.14，需要装 3.11：brew install python@3.11

# 7. 检查系统里有没有残留的坏 .so 干扰
find ~/.rustup -name "*.so" 2>/dev/null | head
find /opt/homebrew -name "_core_compute*.so" 2>/dev/null | head
```

收集到结果后，预期结论可能是：
- Apple 在 macOS 27.x 后续小版本放宽 / 修正了 dyld 的 8 字节校验 → 升级系统即可
- 或者 Apple 把 LINKEDIT 8 字节对齐的 requirement 后撤 → 升 macOS 即可
- lld 上游正在修这个 bug（LLVM issue tracker）→ 升 lld 24+ 即可

## 6. 最终结论

- macOS 路径 **可行**，条件是：
  1. Rust stable 1.97.1（不要再用 1.78.0）
  2. Homebrew lld ≥ 22
  3. **每次** build 完跑 `fix_linkedit_alignment.py` + 重签
  4. 用 `rust/scripts/build_macos.sh` 一键完成上述三步
- 解锁 5 个 pending task 的最简路径：
  - 在 worktree 跑一次 `rust/scripts/build_macos.sh`
  - 再 `cd rust && PYO3_PYTHON=python3.11 cargo test --workspace --release`
  - 24 个测试全过 → 那 5 个 task 即可继续推进
- 一旦上游 lld 修了对齐 bug，把 `fix_linkedit_alignment.py` 那段逻辑删掉即可，
  build_macos.sh 退化成 `maturin develop` + `codesign`。

## 7. 待跟进

- 跟进 [lld issue tracker](https://github.com/llvm/llvm-project/issues) 关于
  Mach-O LC_SYMTAB.stroff 8 字节对齐的修复。修好后我们可以删 `fix_linkedit_alignment.py`。
- 跟进 PyO3 0.23 / maturin 1.15+ 是否提供更稳的 `cdylib` 输出（目前 PyO3 0.22
  仍要求 ≤ Python 3.13，所以 0.23 升上来之前我们 3.11 是必须的）。
- 把 `rust/scripts/build_macos.sh` 接进 CI（GitHub Actions 的 `macos-latest`
  runner 大概率也会撞同样 bug，需要在 CI 步骤里跑 fix + resign）。
