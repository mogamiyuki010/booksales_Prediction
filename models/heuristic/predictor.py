"""
GEM v1.0 - 智能圖書印量預估模型 (改進版)
三層疊代預測法 Python 實作

改進項目 (相對於 v0.1 prompt 版):
1. 系統性修正係數 (global deflation factor)
2. 收緊中層 CR (3%-8% → 1.5%-4%)
3. 月度軌跡建模 (指數衰退曲線，取代單一年度總量)
4. 區分首印量 vs 首年預測
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 資料結構
# ============================================================

@dataclass
class AuthorProfile:
    """作者基本資料與社群指標"""
    name: str
    author_type: str                    # KOP, KOC, Co-Branding, Debut
    yt_subscribers: int = 0
    ig_followers: int = 0
    fb_followers: int = 0
    course_students: int = 0            # 內層受眾: 付費學員
    app_subscribers: int = 0            # 內層受眾: App 訂閱者
    mentor_historical_sales: int = 0    # Co-Branding 時導師歷史銷量
    engagement_rate: float = 0.0        # 加權互動率 (0-1)

    @property
    def total_social_followers(self) -> int:
        """中層受眾: 全平台社群粉絲總數"""
        return self.yt_subscribers + self.ig_followers + self.fb_followers

    @property
    def inner_audience(self) -> int:
        """內層受眾: 付費學員 + App 訂閱者"""
        return self.course_students + self.app_subscribers


@dataclass
class BookInfo:
    """書籍基本資料"""
    title: str
    subcategory: str                    # 細分主題
    price_ntd: int = 380               # 定價 NT$
    is_sequel: bool = False             # 是否為續作
    nth_book: int = 1                   # 該作者第 N 本書
    format: str = "single"             # single, set, upper_lower


@dataclass
class MonthlySalesCurve:
    """月度銷售曲線"""
    monthly_sales: list = field(default_factory=list)   # 各月銷量

    @property
    def cumulative_sales(self) -> list:
        result = []
        total = 0
        for s in self.monthly_sales:
            total += s
            result.append(total)
        return result

    def total_at_month(self, month: int) -> int:
        cum = self.cumulative_sales
        if month <= 0:
            return 0
        if month >= len(cum):
            return cum[-1] if cum else 0
        return cum[month - 1]


@dataclass
class PredictionResult:
    """預測結果"""
    book_title: str
    author_name: str
    author_type: str
    # 月度曲線
    curve_conservative: MonthlySalesCurve = None
    curve_optimistic: MonthlySalesCurve = None
    # 首印量建議
    print_run_low: int = 0
    print_run_high: int = 0
    # 6 個月預測
    sales_6m_low: int = 0
    sales_6m_high: int = 0
    # 首年預測
    sales_fy_low: int = 0
    sales_fy_high: int = 0
    # 參數快照
    params_used: dict = field(default_factory=dict)


# ============================================================
# 預測引擎
# ============================================================

class GEMPredictor:
    """GEM v1.0 三層疊代預測引擎"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config.yaml"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def predict(self, author: AuthorProfile, book: BookInfo) -> PredictionResult:
        """
        執行三層疊代預測法

        Step 1: 計算各層受眾的承諾銷量
        Step 2: 施加修正係數
        Step 3: 建立月度衰退曲線
        Step 4: 輸出首印量與銷量預測
        """
        cfg = self.config
        at = author.author_type

        # --------------------------------------------------
        # Step 1: 受眾分層與總承諾銷量 (N_Committed)
        # --------------------------------------------------
        cr = cfg["conversion_rates"]

        # 內層: 鐵粉/付費學員
        inner_low = int(author.inner_audience * cr["inner"]["min"])
        inner_high = int(author.inner_audience * cr["inner"]["max"])

        # 中層: 活躍粉絲 (v1.0 已收緊)
        middle_low = int(author.total_social_followers * cr["middle"]["min"])
        middle_high = int(author.total_social_followers * cr["middle"]["max"])

        # 外層: 通路曝光 (簡化: 以中層的 5 倍估算外層觸及人數)
        outer_reach = author.total_social_followers * 5
        outer_low = int(outer_reach * cr["outer"]["min"])
        outer_high = int(outer_reach * cr["outer"]["max"])

        n_committed_low = inner_low + middle_low + outer_low
        n_committed_high = inner_high + middle_high + outer_high

        # --------------------------------------------------
        # Step 2: 施加修正係數
        # --------------------------------------------------
        corrections = cfg["correction_factors"]

        # 全域修正因子
        deflation_low = corrections["global_deflation"]["min"]
        deflation_high = corrections["global_deflation"]["max"]

        n_adjusted_low = n_committed_low * deflation_high   # 保守用較高 deflation
        n_adjusted_high = n_committed_high * deflation_low  # 樂觀用較低 deflation
        # 注意: deflation_high (0.65) > deflation_low (0.55)
        # 保守 = 較小 N_committed × 較大 deflation => 用 low × high
        # 樂觀 = 較大 N_committed × 較大 deflation => 用 high × high
        # 重新調整邏輯:
        n_adjusted_low = n_committed_low * deflation_low
        n_adjusted_high = n_committed_high * deflation_high

        # 續作折扣
        if book.is_sequel:
            sequel_factor = corrections["sequel_discount"]
            n_adjusted_low = int(n_adjusted_low * sequel_factor)
            n_adjusted_high = int(n_adjusted_high * sequel_factor)

        # 高價書加成
        if book.price_ntd >= corrections["high_price_threshold"]:
            price_bonus = corrections["high_price_bonus"]
            n_adjusted_low = int(n_adjusted_low * price_bonus)
            n_adjusted_high = int(n_adjusted_high * price_bonus)

        # 第 N 本書遞減
        if book.nth_book > 1:
            nth_factor = corrections["nth_book_decay"] ** (book.nth_book - 1)
            n_adjusted_low = int(n_adjusted_low * nth_factor)
            n_adjusted_high = int(n_adjusted_high * nth_factor)

        # Co-Branding: 若有導師歷史銷量，取其 60%-70% 作為參考上限
        if at == "Co-Branding" and author.mentor_historical_sales > 0:
            cb_ratio = cfg["print_run"]["cobranding_mentor_ratio"]
            cb_low = int(author.mentor_historical_sales * cb_ratio["min"])
            cb_high = int(author.mentor_historical_sales * cb_ratio["max"])
            # 取兩種方法的較小值作為保守，較大值作為樂觀
            n_adjusted_low = min(n_adjusted_low, cb_low) if n_adjusted_low > 0 else cb_low
            n_adjusted_high = max(n_adjusted_high, cb_high)

        # 趨勢乘數
        trend = cfg["trend_multiplier"].get(at, 1.15)
        n_trended_low = int(n_adjusted_low * trend)
        n_trended_high = int(n_adjusted_high * trend)

        # 加上通路最低鋪貨量
        dist_min = cfg["distribution"]["minimum_stock"]
        total_potential_low = n_trended_low + dist_min
        total_potential_high = n_trended_high + dist_min

        # --------------------------------------------------
        # Step 3: 月度衰退曲線建模
        # --------------------------------------------------
        decay_config = cfg["decay_rates"].get(at, cfg["decay_rates"]["Debut"])
        monthly_decay = decay_config["monthly_decay"]
        retention = 1.0 - monthly_decay

        # 計算首月銷量 (peak)，使 12 個月加總等於 total_potential
        # 等比級數和: S = peak × (1 - r^12) / (1 - r)
        if retention == 1.0:
            geometric_sum_factor = 12.0
        else:
            geometric_sum_factor = (1.0 - retention ** 12) / (1.0 - retention)

        peak_low = total_potential_low / geometric_sum_factor
        peak_high = total_potential_high / geometric_sum_factor

        # 產出月度曲線
        curve_low = MonthlySalesCurve(
            monthly_sales=[max(1, int(peak_low * retention ** (t - 1))) for t in range(1, 13)]
        )
        curve_high = MonthlySalesCurve(
            monthly_sales=[max(1, int(peak_high * retention ** (t - 1))) for t in range(1, 13)]
        )

        # --------------------------------------------------
        # Step 4: 輸出預測結果
        # --------------------------------------------------
        target_months_print = cfg["print_run"]["target_months"]

        result = PredictionResult(
            book_title=book.title,
            author_name=author.name,
            author_type=at,
            curve_conservative=curve_low,
            curve_optimistic=curve_high,
            # 首印量: 前 N 個月銷量
            print_run_low=curve_low.total_at_month(target_months_print),
            print_run_high=curve_high.total_at_month(target_months_print),
            # 6 個月預測
            sales_6m_low=curve_low.total_at_month(6),
            sales_6m_high=curve_high.total_at_month(6),
            # 首年預測
            sales_fy_low=curve_low.total_at_month(12),
            sales_fy_high=curve_high.total_at_month(12),
            # 參數快照
            params_used={
                "model_version": "v1.0",
                "author_type": at,
                "cr_middle": [cr["middle"]["min"], cr["middle"]["max"]],
                "deflation": [deflation_low, deflation_high],
                "monthly_decay": monthly_decay,
                "trend_multiplier": trend,
                "n_committed": [n_committed_low, n_committed_high],
                "n_adjusted": [n_adjusted_low, n_adjusted_high],
                "total_potential_fy": [total_potential_low, total_potential_high],
            },
        )

        return result

    def format_report(self, result: PredictionResult) -> str:
        """產出 C-Level 決策報告"""
        r = result
        lines = [
            f"{'='*60}",
            f"  GEM v1.0 圖書銷量預測報告",
            f"{'='*60}",
            f"",
            f"  書名:     {r.book_title}",
            f"  作者:     {r.author_name}",
            f"  作者類型: {r.author_type}",
            f"",
            f"  --- 首印量建議 (基於前 3 個月預估) ---",
            f"  保守: {r.print_run_low:,} 本",
            f"  樂觀: {r.print_run_high:,} 本",
            f"",
            f"  --- 首 6 個月銷量預測 (主要指標) ---",
            f"  保守: {r.sales_6m_low:,} 本",
            f"  樂觀: {r.sales_6m_high:,} 本",
            f"",
            f"  --- 首年銷量預測 ---",
            f"  保守: {r.sales_fy_low:,} 本",
            f"  樂觀: {r.sales_fy_high:,} 本",
            f"",
            f"  --- 月度銷售曲線 (保守) ---",
        ]

        curve = r.curve_conservative
        for i, (monthly, cum) in enumerate(
            zip(curve.monthly_sales, curve.cumulative_sales), 1
        ):
            bar = "#" * max(1, monthly // 100)
            lines.append(f"  月{i:2d}: {monthly:>6,} 本 (累計 {cum:>7,}) {bar}")

        lines.extend([
            f"",
            f"  --- 模型參數 ---",
            f"  N_Committed: {r.params_used.get('n_committed', 'N/A')}",
            f"  修正後 N:    {r.params_used.get('n_adjusted', 'N/A')}",
            f"  月衰退率:    {r.params_used.get('monthly_decay', 'N/A')}",
            f"  趨勢乘數:    {r.params_used.get('trend_multiplier', 'N/A')}",
            f"{'='*60}",
        ])

        return "\n".join(lines)
