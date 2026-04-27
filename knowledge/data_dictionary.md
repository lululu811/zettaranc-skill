# Zettaranc 数据字典（输入）

> 版本: v2.0 | 日期: 2026-04-28
>
> 用途：定义**数据源层**的标准字段。所有外部数据源（Tushare、WebSearch、未来接入的其他 API）必须映射到本字典的字段。
>
> 对应输出信号字典 → `signal_dictionary.md`

---

## 一、核心数据实体

### 1.1 DailyBar（日线行情）

**用途**: 所有技术指标计算的基础数据源，一切分析的起点。

| 字段名 | 类型 | 必填 | 说明 | Tushare 映射 | 示例值 |
|--------|------|------|------|-------------|--------|
| `ts_code` | str | ✅ | 股票代码 | `ts_code` | `000001.SZ` |
| `trade_date` | str | ✅ | 交易日期 YYYYMMDD | `trade_date` | `20260427` |
| `open` | float | ✅ | 开盘价 | `open` | `65.78` |
| `high` | float | ✅ | 最高价 | `high` | `69.52` |
| `low` | float | ✅ | 最低价 | `low` | `63.10` |
| `close` | float | ✅ | 收盘价 | `close` | `71.38` |
| `vol` | float | ✅ | 成交量（手） | `vol` | `2495122.38` |
| `amount` | float | ✅ | 成交额（千元） | `amount` | `176543210` |
| `pct_chg` | float | ✅ | 涨跌幅（%） | `pct_chg` | `2.646` |

**派生字段**（由应用层计算，非数据源直接提供）：

| 字段名 | 类型 | 计算方式 |
|--------|------|---------|
| `prev_close` | float | 前一日 `close` |
| `amplitude` | float | `(high - low) / prev_close * 100` |
| `body_pct` | float | `abs(close - open) / prev_close * 100` |
| `is_yang` | bool | `close > open` |
| `is_yin` | bool | `close < open` |
| `upper_shadow` | float | `high - max(open, close)` |
| `lower_shadow` | float | `min(open, close) - low` |

---

### 1.2 MoneyFlow（资金流向）

**用途**: 主力资金动向分析，需 Tushare 专属接口。

| 字段名 | 类型 | 必填 | 说明 | Tushare 映射 |
|--------|------|------|------|-------------|
| `ts_code` | str | ✅ | 股票代码 | `ts_code` |
| `trade_date` | str | ✅ | 交易日期 | `trade_date` |
| `buy_sm_amount` | float | | 小单买入额 | `buy_sm_amount` |
| `buy_md_amount` | float | | 中单买入额 | `buy_md_amount` |
| `buy_lg_amount` | float | | 大单买入额 | `buy_lg_amount` |
| `buy_elg_amount` | float | | 超大单买入额 | `buy_elg_amount` |
| `sell_sm_amount` | float | | 小单卖出额 | `sell_sm_amount` |
| `sell_md_amount` | float | | 中单卖出额 | `sell_md_amount` |
| `sell_lg_amount` | float | | 大单卖出额 | `sell_lg_amount` |
| `sell_elg_amount` | float | | 超大单卖出额 | `sell_elg_amount` |
| `net_mf` | float | | 净流入额 | `net_mf` |
| `pct_mf` | float | | 净流入占比 | `pct_mf` |

---

### 1.3 StockBasic（股票基本信息）

**用途**: 股票名称、行业、市场属性查询。

| 字段名 | 类型 | 必填 | 说明 | Tushare 映射 |
|--------|------|------|------|-------------|
| `ts_code` | str | ✅ | 股票代码 | `ts_code` |
| `name` | str | | 股票名称 | `name` |
| `area` | str | | 地区 | `area` |
| `industry` | str | | 行业 | `industry` |
| `market` | str | | 市场类型 | `market` |
| `list_date` | str | | 上市日期 | `list_date` |
| `is_hs` | str | | 沪/深港通标识 | `is_hs` |

---

### 1.4 FinancialData（财务数据）

**用途**: 基本面分析、估值判断。

| 字段名 | 类型 | 必填 | 说明 | Tushare 映射 |
|--------|------|------|------|-------------|
| `ts_code` | str | ✅ | 股票代码 | `ts_code` |
| `ann_date` | str | ✅ | 公告日期 | `ann_date` |
| `end_date` | str | ✅ | 报告期 | `end_date` |
| `revenue` | float | | 营业收入 | `revenue` |
| `net_profit` | float | | 净利润 | `net_profit` |
| `total_assets` | float | | 总资产 | `total_assets` |
| `total_liab` | float | | 总负债 | `total_liab` |
| `equity` | float | | 股东权益 | `equity` |
| `pe` | float | | 市盈率 | `pe` |
| `pb` | float | | 市净率 | `pb` |
| `ps` | float | | 市销率 | `ps` |

---

## 二、数据源适配映射

### 2.1 数据源抽象层

所有数据源必须实现以下接口，返回标准 `DailyBar`：

```python
class DataSource(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def get_daily_bars(self, ts_code: str, start_date: str, end_date: str) -> List[DailyBar]:
        """获取日线行情 → 返回标准 DailyBar 列表"""

    @abstractmethod
    def get_moneyflow(self, ts_code: str, trade_date: str) -> Optional[MoneyFlow]:
        """获取资金流向 → 返回标准 MoneyFlow"""

    @abstractmethod
    def get_stock_basic(self, ts_code: str) -> Optional[StockBasic]:
        """获取股票基本信息 → 返回标准 StockBasic"""

    @abstractmethod
    def check_connection(self) -> bool:
        """检查连通性"""
```

### 2.2 当前数据源

| 数据源 | 模式 | 实现类 | 支持实体 |
|--------|------|--------|---------|
| **JNB (Tushare)** | `jnb` | `TushareClient` | DailyBar, MoneyFlow, StockBasic, FinancialData |
| **普通小万 (WebSearch)** | `websearch` | `WebSearchAdapter` (TODO) | StockBasic(部分), 无实时数据 |

### 2.3 字段映射规则

新增数据源时，必须在本文件中添加映射行：

```
| 标准字段名 | Tushare 字段 | WebSearch 字段 | 未来数据源字段 |
|-----------|-------------|---------------|---------------|
| close     | close       | (不支持)      | xxx           |
```

**硬性约束**：
1. 不得在业务代码中直接引用第三方字段名，必须通过适配层映射
2. `DailyBar` 的 9 个必填字段（带 ✅ 标记）是最低要求，缺任何字段的数据源不能用于指标计算
3. 派生字段由应用层统一计算，数据源不得重复提供

---

## 三、数据窗口要求

| 指标 | 最小数据窗口 | 说明 |
|------|-------------|------|
| 基础指标(KDJ/MA/RSI) | 26天 | MACD slow=26 是最长需求 |
| 双线战法 | 115天 | 大哥线需要 MA114 |
| 异动选股 | 65天 | 需要60日均线参考 |
| 黄金碗 | 120天 | 白线+大哥线完整计算 |
| 砖型图趋势 | 115天 | detect_brick_trend |
| **推荐默认** | 100天 | analyze_stock 默认值 |

---

## 四、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-28 | v2.0 | 拆分为输入/输出两文件，本文件只保留数据源输入定义 |
| 2026-04-28 | v1.1 | 清理所有 `_desc` 字段，指标层只输出布尔/数值/枚举 |
| 2026-04-28 | v1.0 | 初始版本，梳理现有全部字段 |
