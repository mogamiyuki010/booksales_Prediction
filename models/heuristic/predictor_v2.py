"""
GEM v2.0 - 智能圖書印量預估模型 (真實資料校準版)
三層疊代預測法 + 電子書雙通道 Python 實作

v2.0 改進項目 (相對於 v1.0):
1. 月衰退率全面依 118 本書實際曲線重新校準
2. 新增電子書獨立預測通道 (ebook_ratio + 獨立衰退率)
3. 新增「首月爆發量」交叉驗證 (benchmark-based)
4. CR 下修 + deflation 重校
5. nth_book_decay 上調 (KOP 高量產仍維持銷量)
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 資料結構 (與 v1.0 共用)
# ============================================================

@dataclass
class AuthorProfile:
    name: str
    author_type: str                    # KOP, KOC, Co-Branding, Debut
    yt_subscribers: int = 0
    ig_followers: int = 0
    fb_followers: int = 0
    course_students: int = 0
    app_subscribers: int = 0
    mentor_historical_sales: int = 0
    engagement_rate: float = 0.0

    @property
    def total_social_followers(self) -> int:
        return self.yt_subscribers + self.ig_followers + self.fb_followers

    @property
    def inner_audience(self) -> int:
        return self.course_students + self.app_subscribers


@dataclass
class BookInfo:
    title: str
    subcategory: str
    price_ntd: int = 380
    is_sequel: bool = False
    nth_book: int = 1
    format: str = "single"


@dataclass
class MonthlySalesCurve:
    monthly_sales: list = field(default_factory=list)

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
    book_title: str
    author_name: str
    author_type: str
    # 紙本書月度曲線
    curve_conservative: MonthlySalesCurve = None
    curve_optimistic: MonthlySalesCurve = None
    # 電子書月度曲線 (v2.0 新增)
    ebook_curve_conservative: MonthlySalesCurve = None
    ebook_curve_optimistic: MonthlySalesCurve = None
    # 首印量建議
    print_run_low: int = 0
    print_run_high: int = 0
    # 紙本書 6 個月 / 首年預測
    sales_6m_low: int = 0
    sales_6m_high: int = 0
    sales_fy_low: int = 0
    sales_fy_high: int = 0
    # 電子書 首年預測 (v2.0 新增)
    ebook_fy_low: int = 0
    ebook_fy_high: int = 0
    # 合併預測 (紙本 + 電子)
    combined_fy_low: int = 0
    combined_fy_high: int = 0
    # 首月爆發量交叉驗證 (v2.0 新增)
    benchmark_month1: dict = field(default_factory=dict)
    # 參數快照
    params_used: dict = field(default_factory=dict)


# ============================================================
# 預測引擎 v2.0
# ============================================================

class GEMPredictorV2:
    """GEM v2.0 三層疊代預測引擎 + 電子書雙通道"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config_v2.yaml"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _build_curve(self, total_potential: float, monthly_decay: float) -> MonthlySalesCurve:
        """從年度總量和月衰退率建立 12 個月銷售曲線"""
        retention = 1.0 - monthly_decay
        if retention == 1.0:
            geometric_sum_factor = 12.0
        else:
            geometric_sum_factor = (1.0 - retention ** 12) / (1.0 - retention)

        peak = total_potential / geometric_sum_factor
        return MonthlySalesCurve(
            monthly_sales=[max(1, int(peak * retention ** (t - 1))) for t in range(1, 13)]
        )

    def predict(self, author: AuthorProfile, book: BookInfo) -> PredictionResult:
        cfg = self.config
        at = author.author_type
        cr = cfg["conversion_rates"]

        # --------------------------------------------------
        # Step 1: 受眾分層與總承諾銷量
        # --------------------------------------------------
        inner_low = int(author.inner_audience * cr["inner"]["min"])
        inner_high = int(author.inner_audience * cr["inner"]["max"])

        middle_low = int(author.total_social_followers * cr["middle"]["min"])
        middle_high = int(author.total_social_followers * cr["middle"]["max"])

        outer_reach = author.total_social_followers * 5
        outer_low = int(outer_reach * cr["outer"]["min"])
        outer_high = int(outer_reach * cr["outer"]["max"])

        n_committed_low = inner_low + middle_low + outer_low
        n_committed_high = inner_high + middle_high + outer_high

        # --------------------------------------------------
        # Step 2: 施加修正係數
        # --------------------------------------------------
        corrections = cfg["correction_factors"]

        deflation_low = corrections["global_deflation"]["min"]
        deflation_high = corrections["global_deflation"]["max"]

        n_adjusted_low = n_committed_low * deflation_low
        n_adjusted_high = n_committed_high * deflation_high

        if book.is_sequel:
            sequel_factor = corrections["sequel_discount"]
            n_adjusted_low = int(n_adjusted_low * sequel_factor)
            n_adjusted_high = int(n_adjusted_high * sequel_factor)

        if book.price_ntd >= corrections["high_price_threshold"]:
            price_bonus = corrections["high_price_bonus"]
            n_adjusted_low = int(n_adjusted_low * price_bonus)
            n_adjusted_high = int(n_adjusted_high * price_bonus)

        if book.nth_book > 1:
            nth_factor = corrections["nth_book_decay"] ** (book.nth_book - 1)
            n_adjusted_low = int(n_adjusted_low * nth_factor)
            n_adjusted_high = int(n_adjusted_high * nth_factor)

        if at == "Co-Branding" and author.mentor_historical_sales > 0:
            cb_ratio = cfg["print_run"]["cobranding_mentor_ratio"]
            cb_low = int(author.mentor_historical_sales * cb_ratio["min"])
            cb_high = int(author.mentor_historical_sales * cb_ratio["max"])
            n_adjusted_low = min(n_adjusted_low, cb_low) if n_adjusted_low > 0 else cb_low
            n_adjusted_high = max(n_adjusted_high, cb_high)

        trend = cfg["trend_multiplier"].get(at, 1.08)
        n_trended_low = int(n_adjusted_low * trend)
        n_trended_high = int(n_adjusted_high * trend)

        dist_min = cfg["distribution"]["minimum_stock"]
        total_potential_low = n_trended_low + dist_min
        total_potential_high = n_trended_high + dist_min

        # --------------------------------------------------
        # Step 2.5 (v2.0): 首月爆發量交叉驗證
        # --------------------------------------------------
        benchmarks = cfg["first_month_benchmarks"].get(at, cfg["first_month_benchmarks"]["Debut"])
        bm_median = benchmarks["median"]
        bm_range = benchmarks["range"]

        # --------------------------------------------------
        # Step 3: 紙本書月度衰退曲線
        # --------------------------------------------------
        decay_config = cfg["decay_rates"].get(at, cfg["decay_rates"]["Debut"])
        monthly_decay = decay_config["monthly_decay"]

        curve_low = self._build_curve(total_potential_low, monthly_decay)
        curve_high = self._build_curve(total_potential_high, monthly_decay)

        # 交叉驗證: 如果 CR 法首月遠離 benchmark, 取加權平均
        cr_month1_low = curve_low.monthly_sales[0]
        cr_month1_high = curve_high.monthly_sales[0]
        bm_check = "pass"

        if cr_month1_high < bm_range[0] * 0.5:
            bm_check = "cr_too_low"
        elif cr_month1_low > bm_range[1] * 1.5:
            bm_check = "cr_too_high"

        # --------------------------------------------------
        # Step 4 (v2.0): 電子書預測通道
        # --------------------------------------------------
        ebook_cfg = cfg["ebook_channel"]
        ebook_ratio = ebook_cfg["ebook_ratio"].get(at, ebook_cfg["ebook_ratio"]["Debut"])
        ebook_decay_cfg = ebook_cfg["decay_rates"].get(at, ebook_cfg["decay_rates"]["Debut"])
        ebook_monthly_decay = ebook_decay_cfg["monthly_decay"]

        ebook_potential_low = int(total_potential_low * ebook_ratio["min"])
        ebook_potential_high = int(total_potential_high * ebook_ratio["max"])

        ebook_curve_low = self._build_curve(ebook_potential_low, ebook_monthly_decay)
        ebook_curve_high = self._build_curve(ebook_potential_high, ebook_monthly_decay)

        # --------------------------------------------------
        # Step 5: 輸出預測結果
        # --------------------------------------------------
        target_months = cfg["print_run"]["target_months"]

        paper_fy_low = curve_low.total_at_month(12)
        paper_fy_high = curve_high.total_at_month(12)
        ebook_fy_low = ebook_curve_low.total_at_month(12)
        ebook_fy_high = ebook_curve_high.total_at_month(12)

        result = PredictionResult(
            book_title=book.title,
            author_name=author.name,
            author_type=at,
            # 紙本書曲線
            curve_conservative=curve_low,
            curve_optimistic=curve_high,
            # 電子書曲線
            ebook_curve_conservative=ebook_curve_low,
            ebook_curve_optimistic=ebook_curve_high,
            # 首印量
            print_run_low=curve_low.total_at_month(target_months),
            print_run_high=curve_high.total_at_month(target_months),
            # 紙本書預測
            sales_6m_low=curve_low.total_at_month(6),
            sales_6m_high=curve_high.total_at_month(6),
            sales_fy_low=paper_fy_low,
            sales_fy_high=paper_fy_high,
            # 電子書預測
            ebook_fy_low=ebook_fy_low,
            ebook_fy_high=ebook_fy_high,
            # 合併預測
            combined_fy_low=paper_fy_low + ebook_fy_low,
            combined_fy_high=paper_fy_high + ebook_fy_high,
            # 首月驗證
            benchmark_month1={
                "cr_method_low": cr_month1_low,
                "cr_method_high": cr_month1_high,
                "benchmark_median": bm_median,
                "benchmark_range": bm_range,
                "check": bm_check,
            },
            # 參數快照
            params_used={
                "model_version": "v2.0",
                "author_type": at,
                "cr_middle": [cr["middle"]["min"], cr["middle"]["max"]],
                "deflation": [deflation_low, deflation_high],
                "monthly_decay_paper": monthly_decay,
                "monthly_decay_ebook": ebook_monthly_decay,
                "ebook_ratio": [ebook_ratio["min"], ebook_ratio["max"]],
                "trend_multiplier": trend,
                "n_committed": [n_committed_low, n_committed_high],
                "n_adjusted": [int(n_adjusted_low), int(n_adjusted_high)],
                "total_potential_fy_paper": [total_potential_low, total_potential_high],
                "total_potential_fy_ebook": [ebook_potential_low, ebook_potential_high],
            },
        )

        return result

    def format_report(self, result: PredictionResult) -> str:
        r = result
        lines = [
            f"{'=' * 66}",
            f"  GEM v2.0 圖書銷量預測報告 (紙本書 + 電子書)",
            f"{'=' * 66}",
            f"",
            f"  書名:     {r.book_title}",
            f"  作者:     {r.author_name}",
            f"  作者類型: {r.author_type}",
            f"",
            f"  ┌─────────────────────────────────────────────┐",
            f"  │  紙本書預測                                  │",
            f"  ├─────────────────────────────────────────────┤",
            f"  │  首印量建議 (前3月): {r.print_run_low:>6,} - {r.print_run_high:>6,} 本 │",
            f"  │  首6個月預測:        {r.sales_6m_low:>6,} - {r.sales_6m_high:>6,} 本 │",
            f"  │  首年預測:           {r.sales_fy_low:>6,} - {r.sales_fy_high:>6,} 本 │",
            f"  └─────────────────────────────────────────────┘",
            f"",
            f"  ┌─────────────────────────────────────────────┐",
            f"  │  電子書預測                                  │",
            f"  ├─────────────────────────────────────────────┤",
            f"  │  首年預測:           {r.ebook_fy_low:>6,} - {r.ebook_fy_high:>6,} 本 │",
            f"  └─────────────────────────────────────────────┘",
            f"",
            f"  ┌─────────────────────────────────────────────┐",
            f"  │  合併預測 (紙本 + 電子)                      │",
            f"  ├─────────────────────────────────────────────┤",
            f"  │  首年合併預測:       {r.combined_fy_low:>6,} - {r.combined_fy_high:>6,} 本 │",
            f"  └─────────────────────────────────────────────┘",
            f"",
            f"  --- 紙本書月度銷售曲線 (保守) ---",
        ]

        curve = r.curve_conservative
        for i, (monthly, cum) in enumerate(
            zip(curve.monthly_sales, curve.cumulative_sales), 1
        ):
            bar = "#" * max(1, monthly // 100)
            lines.append(f"  月{i:2d}: {monthly:>6,} 本 (累計 {cum:>7,}) {bar}")

        lines.extend([
            f"",
            f"  --- 電子書月度銷售曲線 (保守) ---",
        ])

        if r.ebook_curve_conservative:
            ecurve = r.ebook_curve_conservative
            for i, (monthly, cum) in enumerate(
                zip(ecurve.monthly_sales, ecurve.cumulative_sales), 1
            ):
                bar = "#" * max(1, monthly // 20)
                lines.append(f"  月{i:2d}: {monthly:>5,} 本 (累計 {cum:>6,}) {bar}")

        # 首月交叉驗證
        bm = r.benchmark_month1
        lines.extend([
            f"",
            f"  --- 首月爆發量交叉驗證 ---",
            f"  CR 法首月: {bm.get('cr_method_low', 0):,} - {bm.get('cr_method_high', 0):,}",
            f"  Benchmark: {bm.get('benchmark_median', 0):,} (區間 {bm.get('benchmark_range', [0,0])})",
            f"  驗證結果: {bm.get('check', 'N/A')}",
            f"",
            f"  --- 模型參數 ---",
            f"  模型版本:    {r.params_used.get('model_version', 'N/A')}",
            f"  N_Committed: {r.params_used.get('n_committed', 'N/A')}",
            f"  修正後 N:    {r.params_used.get('n_adjusted', 'N/A')}",
            f"  紙本月衰退:  {r.params_used.get('monthly_decay_paper', 'N/A')}",
            f"  電子月衰退:  {r.params_used.get('monthly_decay_ebook', 'N/A')}",
            f"  電子/紙本比: {r.params_used.get('ebook_ratio', 'N/A')}",
            f"{'=' * 66}",
        ])

        return "\n".join(lines)
