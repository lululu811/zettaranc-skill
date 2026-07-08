"""
行业分散化过滤器

实现行业维度的持仓约束：
1. 查询股票行业分类（从 stock_basic 表，申万一级行业 ~30 类）
2. 限制同行业持仓数量（默认最多 2 只）
3. 限制同行业总仓位（默认 ≤ 40%）
4. 构建行业均匀分布的股票池

数据库路径从环境变量 DB_PATH 读取，默认 data/stock_data.db。
"""

import logging
from collections import Counter, defaultdict
from pathlib import Path

from modules.database import get_connection, get_db_path

logger = logging.getLogger(__name__)


class IndustryFilter:
    """行业分散化过滤器

    通过行业分类信息对股票池进行分散化约束，避免持仓过度集中于单一行业。

    Attributes:
        db_path: 数据库文件路径
        max_per_industry: 同行业最大持仓只数
        max_industry_pct: 同行业最大仓位占比（0~1）
    """

    def __init__(
        self,
        db_path: str | None = None,
        max_per_industry: int = 2,
        max_industry_pct: float = 0.4,
    ):
        """初始化过滤器

        Args:
            db_path: 数据库路径，为 None 时使用环境变量 DB_PATH 的默认路径
            max_per_industry: 同行业最大持仓只数，默认 2
            max_industry_pct: 同行业最大仓位占比，默认 0.4（即 40%）
        """
        self.db_path = Path(db_path) if db_path else get_db_path()
        self.max_per_industry = max_per_industry
        self.max_industry_pct = max_industry_pct

    def get_industry(self, ts_code: str) -> str:
        """获取单只股票的行业分类

        Args:
            ts_code: 股票代码（如 "600487.SH"）

        Returns:
            行业名称（如 "半导体"、"银行"），未找到时返回空字符串
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT industry FROM stock_basic WHERE ts_code = ?",
                (ts_code,),
            )
            row = cursor.fetchone()
            if row and row["industry"]:
                return row["industry"]
            return ""

    def get_all_industries(self) -> dict[str, str]:
        """获取所有股票的行业映射

        Returns:
            {ts_code: industry} 字典，仅包含 industry 非空的记录
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT ts_code, industry FROM stock_basic WHERE industry IS NOT NULL AND industry != ''"
            )
            return {row["ts_code"]: row["industry"] for row in cursor.fetchall()}

    def build_diversified_pool(
        self,
        stocks: list[str],
        target_size: int | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[str]:
        """构建行业均匀分布的股票池

        采用蛇形轮转（snake draft）分配：按行业分组后轮流从各行业选取，
        确保最终池中各行业股票数量尽量均匀。同时遵守 max_per_industry 约束。

        Args:
            stocks: 候选股票代码列表
            target_size: 目标池大小，为 None 时尽量保留所有满足约束的股票
            weights: 可选的股票权重字典 {ts_code: weight}，用于同行业内排序
                     （权重高的优先入选）。未提供时按原始列表顺序

        Returns:
            行业分散化后的股票代码列表
        """
        if not stocks:
            return []

        # 获取候选股票的行业映射
        industry_map = self._get_industries_for_stocks(stocks)

        # 按行业分组
        industry_groups: dict[str, list[str]] = defaultdict(list)
        no_industry: list[str] = []
        for ts_code in stocks:
            ind = industry_map.get(ts_code, "")
            if ind:
                industry_groups[ind].append(ts_code)
            else:
                no_industry.append(ts_code)

        # 同行业内按权重降序排列（权重高的优先）
        if weights:
            for ind in industry_groups:
                industry_groups[ind].sort(key=lambda c: weights.get(c, 0.0), reverse=True)
            no_industry.sort(key=lambda c: weights.get(c, 0.0), reverse=True)

        # 蛇形轮转选股
        result: list[str] = []
        industry_count: Counter = Counter()
        industries = sorted(industry_groups.keys())

        # 跟踪各行业已选数量，用于轮转
        remaining = {ind: len(group) for ind, group in industry_groups.items()}
        total_remaining = sum(remaining.values())

        while total_remaining > 0:
            # 每轮遍历所有行业
            progressed = False
            for ind in industries:
                if remaining.get(ind, 0) <= 0:
                    continue
                if industry_count[ind] >= self.max_per_industry:
                    # 已达行业上限，跳过
                    continue

                # 从该行业取下一只
                group = industry_groups[ind]
                # 找到该行业下一个未被选入的股票
                while group:
                    candidate = group.pop(0)
                    if candidate not in set(result):
                        result.append(candidate)
                        industry_count[ind] += 1
                        remaining[ind] -= 1
                        total_remaining -= 1
                        progressed = True
                        break
                else:
                    remaining[ind] = 0

                # 检查是否达到目标大小
                if target_size and len(result) >= target_size:
                    return result[:target_size]

            # 如果一轮下来没有任何进展（所有剩余行业都达上限），终止
            if not progressed:
                break

        # 追加无行业信息的股票（也受 max_per_industry 约束，归入 "未知" 类别）
        unknown_count = 0
        for ts_code in no_industry:
            if target_size and len(result) >= target_size:
                break
            # 无行业信息的股票统一按 "未知" 行业计数
            if unknown_count >= self.max_per_industry:
                break
            result.append(ts_code)
            unknown_count += 1

        if target_size:
            return result[:target_size]
        return result

    def check_industry_limit(
        self,
        ts_code: str,
        current_holdings: list[str],
        holding_weights: dict[str, float] | None = None,
    ) -> bool:
        """检查买入该股票是否违反行业限制

        检查两个约束：
        1. 同行业持仓只数 ≤ max_per_industry
        2. 同行业仓位占比 ≤ max_industry_pct

        Args:
            ts_code: 待买入的股票代码
            current_holdings: 当前持仓股票列表
            holding_weights: 持仓权重字典 {ts_code: weight}，用于计算仓位占比。
                             未提供时仅检查只数约束，仓位约束默认等权计算

        Returns:
            True 表示可以买入（不违反约束），False 表示违反行业限制
        """
        target_industry = self.get_industry(ts_code)
        if not target_industry:
            # 无行业信息的股票不受行业约束
            return True

        # 统计当前持仓的行业分布
        industry_count = self._count_industry_in_holdings(target_industry, current_holdings)

        # 约束 1：同行业只数限制
        if industry_count >= self.max_per_industry:
            logger.debug(
                "行业只数限制: %s 已有 %d 只（上限 %d）",
                target_industry,
                industry_count,
                self.max_per_industry,
            )
            return False

        # 约束 2：同行业仓位占比限制
        if holding_weights and len(current_holdings) > 0:
            # 计算同行业权重占比
            same_industry_holdings = [h for h in current_holdings if self.get_industry(h) == target_industry]
            total_weight = sum(holding_weights.get(h, 1.0) for h in current_holdings)
            # 加上拟买入股票的权重
            new_stock_weight = holding_weights.get(ts_code, 1.0)
            industry_weight = sum(holding_weights.get(h, 1.0) for h in same_industry_holdings)
            new_total_weight = total_weight + new_stock_weight
            new_industry_weight = industry_weight + new_stock_weight

            if new_total_weight > 0:
                industry_pct = new_industry_weight / new_total_weight
                if industry_pct > self.max_industry_pct:
                    logger.debug(
                        "行业仓位限制: %s 占比 %.1f%% 超过上限 %.1f%%",
                        target_industry,
                        industry_pct * 100,
                        self.max_industry_pct * 100,
                    )
                    return False

        elif not holding_weights and len(current_holdings) > 0:
            # 等权模式：同行业占比 = 同行业只数 / 总只数
            same_industry_holdings = [h for h in current_holdings if self.get_industry(h) == target_industry]
            total_count = len(current_holdings) + 1  # +1 为拟买入
            industry_pct = (len(same_industry_holdings) + 1) / total_count
            if industry_pct > self.max_industry_pct:
                logger.debug(
                    "行业仓位限制(等权): %s 占比 %.1f%% 超过上限 %.1f%%",
                    target_industry,
                    industry_pct * 100,
                    self.max_industry_pct * 100,
                )
                return False

        return True

    def get_industry_distribution(self, holdings: list[str]) -> dict[str, int]:
        """获取持仓的行业分布

        Args:
            holdings: 持仓股票列表

        Returns:
            {行业名称: 持仓只数} 字典，无行业信息的归入 "未知"
        """
        if not holdings:
            return {}

        industry_map = self._get_industries_for_stocks(holdings)
        distribution: Counter = Counter()

        for ts_code in holdings:
            ind = industry_map.get(ts_code, "")
            if ind:
                distribution[ind] += 1
            else:
                distribution["未知"] += 1

        return dict(distribution)

    # ──────────────────────────────────────────────
    # 内部辅助方法
    # ──────────────────────────────────────────────

    def _get_industries_for_stocks(self, stocks: list[str]) -> dict[str, str]:
        """批量查询股票的行业映射

        使用 IN 查询一次性获取，避免逐只查询的 N+1 问题。
        SQLite 对 IN 子句的参数数量有 SQLITE_MAX_SQL_LENGTH 限制，
        但对常规股票池（几百只）没有问题。

        Args:
            stocks: 股票代码列表

        Returns:
            {ts_code: industry} 字典
        """
        if not stocks:
            return {}

        placeholders = ",".join("?" for _ in stocks)
        with get_connection() as conn:
            cursor = conn.execute(
                f"SELECT ts_code, industry FROM stock_basic "
                f"WHERE ts_code IN ({placeholders}) AND industry IS NOT NULL AND industry != ''",
                stocks,
            )
            return {row["ts_code"]: row["industry"] for row in cursor.fetchall()}

    def _count_industry_in_holdings(self, target_industry: str, holdings: list[str]) -> int:
        """统计持仓中属于指定行业的股票只数

        Args:
            target_industry: 目标行业名称
            holdings: 持仓股票列表

        Returns:
            属于该行业的持仓只数
        """
        if not holdings:
            return 0

        placeholders = ",".join("?" for _ in holdings)
        with get_connection() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) as cnt FROM stock_basic WHERE ts_code IN ({placeholders}) AND industry = ?",
                holdings + [target_industry],
            )
            row = cursor.fetchone()
            return row["cnt"] if row else 0


# ──────────────────────────────────────────────
# 测试入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s - %(message)s")

    f = IndustryFilter()

    # 1. 测试获取所有行业映射
    print("=" * 60)
    print("行业分散化过滤器 - 功能测试")
    print("=" * 60)

    all_industries = f.get_all_industries()
    print(f"\n数据库中共 {len(all_industries)} 只有行业信息的股票")

    # 统计行业数量
    industry_counter = Counter(all_industries.values())
    print(f"共 {len(industry_counter)} 个行业")
    print("\n前 10 大行业:")
    for ind, cnt in industry_counter.most_common(10):
        print(f"  {ind}: {cnt} 只")

    # 2. 测试单只股票行业查询
    test_code = "600487.SH"
    industry = f.get_industry(test_code)
    print(f"\n{test_code} 的行业: {industry or '(未找到)'}")

    # 3. 测试行业均匀分布股票池构建
    # 取半导体行业前 10 只 + 银行行业前 10 只 + 通信行业前 10 只
    sample_stocks = []
    target_industries = ["半导体", "银行", "通信"]
    for ind in target_industries:
        codes = [code for code, i in all_industries.items() if i == ind][:10]
        sample_stocks.extend(codes)
        print(f"\n{ind} 候选 {len(codes)} 只: {codes[:5]}...")

    pool = f.build_diversified_pool(sample_stocks, target_size=15)
    print("\n构建分散化股票池 (目标 15 只, max_per_industry=2):")
    dist = f.get_industry_distribution(pool)
    for ind, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {ind}: {cnt} 只")
    print(f"  总计: {len(pool)} 只")
    print(f"  股票列表: {pool}")

    # 4. 测试行业限制检查
    print("\n行业限制检查测试:")
    # 假设已持有 2 只半导体
    semi_stocks = [c for c, i in all_industries.items() if i == "半导体"][:2]
    if semi_stocks and industry == "半导体":
        can_buy = f.check_industry_limit(test_code, semi_stocks)
        print(f"  已持有 {len(semi_stocks)} 只半导体, 再买 {test_code}: {'可以' if can_buy else '不可以'}")
    else:
        # 用第一只半导体股票测试
        if semi_stocks:
            test_target = semi_stocks[0]
            can_buy = f.check_industry_limit(test_target, semi_stocks[1:])
            print(f"  已持有 {len(semi_stocks) - 1} 只半导体, 再买 {test_target}: {'可以' if can_buy else '不可以'}")

    print("\n测试完成 ✓")
