#!/usr/bin/env bash
# ==============================================================================
# 本地 CI 质量门禁一键自检脚本
# 用法: bash scripts/ci_check.sh [--fix] [--all-tests]
#   --fix: 自动运行 ruff format 与 ruff check --fix
#   --all-tests: 运行全量测试（默认运行关键/核心单元测试）
# ==============================================================================

set -eo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

AUTO_FIX=false
RUN_ALL_TESTS=false

for arg in "$@"; do
    case "$arg" in
        --fix)
            AUTO_FIX=true
            ;;
        --all-tests)
            RUN_ALL_TESTS=true
            ;;
    esac
done

# 检测 Python 解释器
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
else
    echo -e "${RED}错误: 未找到 Python 解释器 (python3 或 python)${NC}"
    exit 1
fi

# 检测 ruff
if command -v ruff &>/dev/null; then
    RUFF="ruff"
else
    RUFF="$PY -m ruff"
fi

# 检测 mypy
if command -v mypy &>/dev/null; then
    MYPY="mypy"
else
    MYPY="$PY -m mypy"
fi

# 检测 pytest
if command -v pytest &>/dev/null; then
    PYTEST="pytest"
else
    PYTEST="$PY -m pytest"
fi

echo -e "${BLUE}=== 开始本地 CI 质量门禁自检 ===${NC}"

# 1. 代码格式化检查 / 修复
if [ "$AUTO_FIX" = true ]; then
    echo -e "\n${YELLOW}[1/6] 自动格式化代码 (ruff format & fix)...${NC}"
    $RUFF format modules/ tests/
    $RUFF check modules/ tests/ --select=F,E,W,UP --ignore=E501,F401,F403 --fix
else
    echo -e "\n${YELLOW}[1/6] 检查代码格式 (ruff format --check)...${NC}"
    $RUFF format --check modules/ tests/
    echo -e "\n${YELLOW}[2/6] 代码静态检查 (ruff check)...${NC}"
    $RUFF check modules/ tests/ --select=F,E,W,UP --ignore=E501,F401,F403
fi
echo -e "${GREEN}✓ 代码风格检查通过${NC}"

# 2. 静态类型检查
echo -e "\n${YELLOW}[3/6] 静态类型检查 (mypy 全量 + 关键模块)...${NC}"
$MYPY modules/ --ignore-missing-imports
$MYPY modules/screener modules/cli.py modules/cli_commands modules/data_sync modules/indicators/core.py modules/strategies
echo -e "${GREEN}✓ 类型检查通过${NC}"

# 3. 版本号一致性检查
echo -e "\n${YELLOW}[4/6] 检查版本号一致性...${NC}"
$PY scripts/check_version_consistency.py
echo -e "${GREEN}✓ 版本号一致性通过${NC}"

# 4. SKILL.md 质量门
echo -e "\n${YELLOW}[5/6] 检查 SKILL.md 质量门 (12 项确定性门禁)...${NC}"
$PY corpus/quality_check.py SKILL.md --strict
echo -e "${GREEN}✓ SKILL.md 质量门通过${NC}"

# 5. 单元测试
if [ "$RUN_ALL_TESTS" = true ]; then
    echo -e "\n${YELLOW}[6/6] 运行全量单元测试 (pytest tests/)...${NC}"
    $PYTEST tests/ -v --tb=short
else
    echo -e "\n${YELLOW}[6/6] 运行核心单元测试 (pytest tests/test_core.py tests/test_indicators.py)...${NC}"
    $PYTEST tests/test_core.py tests/test_indicators.py -v --tb=short
fi
echo -e "${GREEN}✓ 单元测试通过${NC}"

echo -e "\n${GREEN}==============================================${NC}"
echo -e "${GREEN}🎉 恭喜！所有 CI 质量门禁自检全部通过，可放心提交！${NC}"
echo -e "${GREEN}==============================================${NC}"
