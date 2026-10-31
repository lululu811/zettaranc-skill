"""股票分析相关 Pydantic 模型"""

from typing import Any
from pydantic import BaseModel


# ── 指标详情 ──


class KDJDetail(BaseModel):
    k: float = 0
    d: float = 0
    j: float = 0


class MACDDetail(BaseModel):
    dif: float = 0
    dea: float = 0
    hist: float = 0
    veto: bool = False
    gold_cross: bool = False
    dead_cross: bool = False
    top_divergence: bool = False
    bottom_divergence: bool = False


class RSIDetail(BaseModel):
    rsi6: float = 0
    rsi12: float = 0
    rsi24: float = 0


class BollingerDetail(BaseModel):
    mid: float = 0
    upper: float = 0
    lower: float = 0
    width: float = 0
    position: float = 0


class MADetail(BaseModel):
    ma5: float = 0
    ma10: float = 0
    ma20: float = 0
    ma60: float = 0
    high_52w: float = 0
    high_52w_dist: float = 0


class DoubleLineDetail(BaseModel):
    white: float = 0
    yellow: float = 0
    is_gold_cross: bool = False
    is_dead_cross: bool = False


class BrickDetail(BaseModel):
    value: float = 0
    trend: str = "NEUTRAL"
    count: int = 0
    trend_up: bool = False
    is_fanbao: bool = False


class DMIDetail(BaseModel):
    plus: float = 0
    minus: float = 0
    adx: float = 0


class IndicatorDetail(BaseModel):
    kdj: KDJDetail = KDJDetail()
    macd: MACDDetail = MACDDetail()
    bbi: float = 0
    rsi: RSIDetail = RSIDetail()
    bollinger: BollingerDetail = BollingerDetail()
    ma: MADetail = MADetail()
    wr: dict[str, float] = {}
    vol_ratio: float = 0
    double_line: DoubleLineDetail = DoubleLineDetail()
    brick: BrickDetail = BrickDetail()
    dmi: DMIDetail = DMIDetail()
    signal: str = "WATCH"
    sell_score: int = 0
    sell_items: dict[str, bool] = {}


# ── 战法信号 ──


class StrategySignalResponse(BaseModel):
    strategy: str
    date: str
    confidence: float
    action: str
    description: str
    priority: str = "OBSERVE"
    target_price: float | None = None
    stop_loss: float | None = None


# ── 评分 ──


class ScoreDetail(BaseModel):
    total: float = 0
    b1_score: float = 0
    trend_score: float = 0
    volume_score: float = 0
    risk_score: float = 0
    rating: str = ""
    reasons: list[str] = []
    warnings: list[str] = []


# ── 诊断摘要 ──


class DiagnosisSummary(BaseModel):
    price_position: str = ""
    trend_status: str = ""
    sell_score: int = 0
    sell_score_desc: str = ""
    kirin_phase: str = ""
    bull_rope: str = ""
    sandglass_score: float = 0
    is_centipede: bool = False
    risk_level: str = "UNKNOWN"
    recommendation: str = ""


# ── 主力阶段 ──


class WaveInfo(BaseModel):
    wave: str = "未知"
    confidence: float = 0
    suggestion: str = ""


class KirinInfo(BaseModel):
    phase: str = "未知"
    sub_type: str = "未知"
    confidence: float = 0
    operation: str = ""


# ── 完整分析响应 ──


class StockAnalysisResponse(BaseModel):
    ts_code: str
    name: str = ""
    price: float = 0
    prev_close: float = 0
    pct_chg: float = 0
    trade_date: str = ""
    indicators: IndicatorDetail = IndicatorDetail()
    waves: WaveInfo | None = None
    kirin: KirinInfo | None = None
    signals: list[StrategySignalResponse] = []
    score: ScoreDetail = ScoreDetail()
    diagnosis: DiagnosisSummary = DiagnosisSummary()


# ── K 线图表数据 ──


class SignalMarker(BaseModel):
    date: str
    type: str
    price: float
    action: str  # BUY / SELL


class ChartOverlays(BaseModel):
    ma5: list[float | None] = []
    ma10: list[float | None] = []
    ma20: list[float | None] = []
    ma60: list[float | None] = []
    bbi: list[float | None] = []
    boll_upper: list[float | None] = []
    boll_mid: list[float | None] = []
    boll_lower: list[float | None] = []
    white_line: list[float | None] = []
    yellow_line: list[float | None] = []


class KdjSeries(BaseModel):
    k: list[float | None] = []
    d: list[float | None] = []
    j: list[float | None] = []


class MacdSeries(BaseModel):
    dif: list[float | None] = []
    dea: list[float | None] = []
    hist: list[float | None] = []


class BrickSeries(BaseModel):
    values: list[float | None] = []
    colors: list[int | None] = []


class KlineChartResponse(BaseModel):
    ts_code: str
    name: str = ""
    dates: list[str] = []
    ohlc: list[list[float]] = []
    volumes: list[float] = []
    pct_chgs: list[float] = []
    overlays: ChartOverlays = ChartOverlays()
    signal_markers: list[SignalMarker] = []
    kdj: KdjSeries = KdjSeries()
    macd: MacdSeries = MacdSeries()
    brick: BrickSeries = BrickSeries()
    waves_sequence: list[str] = []
    kirin_sequence: list[str] = []
    breathing_wave: list[float] = []


# ── 全量指标（供前端 IndicatorPanel 展示）──


class FullIndicatorResponse(BaseModel):
    ts_code: str
    trade_date: str = ""
    data: dict[str, Any] = {}
