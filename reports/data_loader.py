"""
Data Loader & Processing Module for Reports
營收表 CSV 資料載入與 KPI 計算

Reads UTF-16 TSV revenue CSVs, merges incremental files,
and provides period-based filtering and KPI computation.
"""

import glob
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


class ReportData:
    """Load and process revenue data for reporting."""

    COLUMNS = [
        "r", "日期控制", "Order_ID", "商品ID", "商品名稱", "作者名稱",
        "分類", "銷售方式", "銷售通路", "銷售形式", "售出商品數量", "售出商品營收",
    ]

    BOOK_CATEGORIES = ["紙本書", "電子書"]

    def __init__(self, project_root=None):
        if project_root is None:
            self.project_root = Path(__file__).resolve().parent.parent
        else:
            self.project_root = Path(project_root)

        self._raw_df = None
        self._book_df = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _read_single_csv(self, path: str) -> pd.DataFrame:
        """Read a single UTF-16 TSV revenue CSV and normalise columns."""
        df = pd.read_csv(path, encoding="utf-16", sep="\t", low_memory=False)
        df.columns = self.COLUMNS
        return df

    def load_all_csvs(self) -> pd.DataFrame:
        """Find all 營收表-Rawdata*.csv files, merge, and deduplicate."""
        pattern = str(self.project_root / "營收表-Rawdata*.csv")
        files = sorted(glob.glob(pattern))

        if not files:
            raise FileNotFoundError(
                f"No revenue CSV files found matching: {pattern}"
            )

        frames = []
        for f in files:
            frames.append(self._read_single_csv(f))

        if len(frames) == 1:
            merged = frames[0]
        else:
            merged = pd.concat(frames, ignore_index=True)
            merged = merged.drop_duplicates(
                subset=["r", "Order_ID"], keep="first"
            )

        # Clean numeric columns
        for col in ["售出商品數量", "售出商品營收"]:
            merged[col] = pd.to_numeric(
                merged[col].astype(str).str.replace(",", ""), errors="coerce"
            )

        # Parse dates
        merged["日期"] = pd.to_datetime(
            merged["日期控制"], format="mixed", errors="coerce"
        )

        # Mark returns
        merged["is_return"] = merged["銷售方式"] == "外部(PdReturn)"

        # Derived time columns
        merged["年月"] = merged["日期"].dt.to_period("M")
        merged["年"] = merged["日期"].dt.year
        merged["週"] = merged["日期"].dt.isocalendar().week.astype(int)
        merged["iso_year"] = merged["日期"].dt.isocalendar().year.astype(int)
        merged["季"] = merged["日期"].dt.quarter

        self._raw_df = merged
        self._book_df = None  # reset cached book df
        return merged

    @property
    def raw_df(self) -> pd.DataFrame:
        """Lazy-loaded raw dataframe (all categories)."""
        if self._raw_df is None:
            self.load_all_csvs()
        return self._raw_df

    @property
    def book_df(self) -> pd.DataFrame:
        """Filtered to books only (紙本書 + 電子書)."""
        if self._book_df is None:
            self._book_df = self.raw_df[
                self.raw_df["分類"].isin(self.BOOK_CATEGORIES)
            ].copy()
        return self._book_df

    def get_data(self, start, end) -> pd.DataFrame:
        """Filter book data by date range [start, end]."""
        df = self.book_df
        mask = (df["日期"] >= pd.Timestamp(start)) & (df["日期"] <= pd.Timestamp(end))
        result = df[mask].copy()
        return result if len(result) > 0 else None

    # ------------------------------------------------------------------
    # Period filtering
    # ------------------------------------------------------------------

    def _latest_period_value(self, df: pd.DataFrame, period_type: str) -> str:
        """Determine the latest complete period value from the data."""
        valid = df.dropna(subset=["日期"])
        if valid.empty:
            raise ValueError("No valid dates in data")

        max_date = valid["日期"].max()

        if period_type == "weekly":
            # Go back to the last fully completed week
            iso = max_date.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"

        elif period_type == "monthly":
            return max_date.strftime("%Y-%m")

        elif period_type == "quarterly":
            q = (max_date.month - 1) // 3 + 1
            return f"{max_date.year}-Q{q}"

        raise ValueError(f"Unknown period_type: {period_type}")

    @staticmethod
    def _parse_week(week_str: str):
        """Parse 'YYYY-Www' and return (iso_year, week_number)."""
        parts = week_str.split("-W")
        return int(parts[0]), int(parts[1])

    @staticmethod
    def _prev_week(week_str: str) -> str:
        """Return the previous ISO week string."""
        iso_year, week = ReportData._parse_week(week_str)
        # Use a date in that week, subtract 7 days
        d = datetime.strptime(f"{iso_year}-W{week:02d}-1", "%G-W%V-%u")
        prev = d - timedelta(weeks=1)
        iso = prev.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    @staticmethod
    def _prev_month(month_str: str) -> str:
        """Return previous month string from 'YYYY-MM'."""
        d = datetime.strptime(month_str + "-01", "%Y-%m-%d")
        first_of_month = d.replace(day=1)
        prev = first_of_month - timedelta(days=1)
        return prev.strftime("%Y-%m")

    @staticmethod
    def _prev_quarter(quarter_str: str) -> str:
        """Return previous quarter string from 'YYYY-Qn'."""
        year, q = int(quarter_str[:4]), int(quarter_str[-1])
        if q == 1:
            return f"{year - 1}-Q4"
        return f"{year}-Q{q - 1}"

    def _filter_by_week(self, df: pd.DataFrame, week_str: str) -> pd.DataFrame:
        iso_year, week = self._parse_week(week_str)
        return df[
            (df["iso_year"] == iso_year) & (df["週"] == week)
        ]

    def _filter_by_month(self, df: pd.DataFrame, month_str: str) -> pd.DataFrame:
        target = pd.Period(month_str, freq="M")
        return df[df["年月"] == target]

    def _filter_by_quarter(self, df: pd.DataFrame, quarter_str: str) -> pd.DataFrame:
        year, q = int(quarter_str[:4]), int(quarter_str[-1])
        return df[(df["年"] == year) & (df["季"] == q)]

    def filter_period(
        self, period_type: str, period_value: str = None, books_only: bool = True
    ) -> pd.DataFrame:
        """
        Filter data by period.

        Args:
            period_type: 'weekly', 'monthly', or 'quarterly'
            period_value: e.g. '2026-W15', '2026-03', '2026-Q1'.
                          If None, uses the latest period in data.
            books_only: If True, filter to 紙本書/電子書 only.

        Returns:
            Filtered DataFrame.
        """
        source = self.book_df if books_only else self.raw_df

        if period_value is None:
            period_value = self._latest_period_value(source, period_type)

        if period_type == "weekly":
            return self._filter_by_week(source, period_value)
        elif period_type == "monthly":
            return self._filter_by_month(source, period_value)
        elif period_type == "quarterly":
            return self._filter_by_quarter(source, period_value)

        raise ValueError(f"Unknown period_type: {period_type}")

    def get_previous_period_value(self, period_type: str, period_value: str) -> str:
        """Return the previous period string for comparison."""
        if period_type == "weekly":
            return self._prev_week(period_value)
        elif period_type == "monthly":
            return self._prev_month(period_value)
        elif period_type == "quarterly":
            return self._prev_quarter(period_value)
        raise ValueError(f"Unknown period_type: {period_type}")

    # ------------------------------------------------------------------
    # KPI methods
    # ------------------------------------------------------------------

    def get_summary_kpis(self, df: pd.DataFrame) -> dict:
        """
        Compute summary KPIs from a (filtered) DataFrame.

        Returns dict with:
            total_sales, total_revenue, total_orders, avg_order_value,
            return_qty, net_sales, net_revenue
        """
        if df.empty:
            return {
                "total_sales": 0,
                "total_revenue": 0,
                "total_orders": 0,
                "avg_order_value": 0,
                "return_qty": 0,
                "net_sales": 0,
                "net_revenue": 0,
            }

        sales_rows = df[~df["is_return"]]
        return_rows = df[df["is_return"]]

        gross_qty = sales_rows["售出商品數量"].sum()
        gross_rev = sales_rows["售出商品營收"].sum()
        return_qty = return_rows["售出商品數量"].sum()
        return_rev = return_rows["售出商品營收"].sum()

        net_qty = df["售出商品數量"].sum()  # returns are already negative
        net_rev = df["售出商品營收"].sum()

        total_orders = df["Order_ID"].nunique()
        avg_order = net_rev / total_orders if total_orders > 0 else 0

        return {
            "total_sales": int(gross_qty),
            "total_revenue": round(float(gross_rev), 2),
            "total_orders": int(total_orders),
            "avg_order_value": round(float(avg_order), 2),
            "return_qty": int(abs(return_qty)),
            "net_sales": int(net_qty),
            "net_revenue": round(float(net_rev), 2),
        }

    def get_top_books(self, df: pd.DataFrame, n: int = 10) -> list:
        """
        Top N books by net sales volume.

        Returns list of dicts with: 商品名稱, 作者名稱, 分類, 銷量, 營收
        """
        if df.empty:
            return []

        agg = (
            df.groupby(["商品ID", "商品名稱", "作者名稱", "分類"])
            .agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum"))
            .reset_index()
            .sort_values("銷量", ascending=False)
            .head(n)
        )

        return agg[["商品名稱", "作者名稱", "分類", "銷量", "營收"]].to_dict("records")

    def get_channel_breakdown(self, df: pd.DataFrame) -> dict:
        """
        Sales breakdown by 銷售通路.

        Returns dict mapping channel name -> {銷量, 營收, 佔比}.
        """
        if df.empty:
            return {}

        agg = (
            df.groupby("銷售通路")
            .agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum"))
            .sort_values("銷量", ascending=False)
        )

        total_qty = agg["銷量"].sum()
        result = {}
        for channel, row in agg.iterrows():
            result[channel] = {
                "銷量": int(row["銷量"]),
                "營收": round(float(row["營收"]), 2),
                "佔比": round(float(row["銷量"] / total_qty * 100), 1) if total_qty else 0,
            }
        return result

    def get_book_type_split(self, df: pd.DataFrame) -> dict:
        """
        紙本書 vs 電子書 split.

        Returns dict with keys '紙本書' and '電子書', each containing
        銷量, 營收, 佔比.
        """
        if df.empty:
            return {}

        agg = (
            df.groupby("分類")
            .agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum"))
        )

        total_qty = agg["銷量"].sum()
        total_rev = agg["營收"].sum()
        result = {}
        for cat in self.BOOK_CATEGORIES:
            if cat in agg.index:
                result[cat] = {
                    "銷量": int(agg.loc[cat, "銷量"]),
                    "營收": round(float(agg.loc[cat, "營收"]), 2),
                    "銷量佔比": round(
                        float(agg.loc[cat, "銷量"] / total_qty * 100), 1
                    ) if total_qty else 0,
                    "營收佔比": round(
                        float(agg.loc[cat, "營收"] / total_rev * 100), 1
                    ) if total_rev else 0,
                }
            else:
                result[cat] = {"銷量": 0, "營收": 0, "銷量佔比": 0, "營收佔比": 0}
        return result

    def get_author_breakdown(self, df: pd.DataFrame) -> list:
        """
        Sales breakdown by author, sorted descending.

        Returns list of dicts: 作者名稱, 銷量, 營收, 書數.
        """
        if df.empty:
            return []

        agg = (
            df.groupby("作者名稱")
            .agg(
                銷量=("售出商品數量", "sum"),
                營收=("售出商品營收", "sum"),
                書數=("商品ID", "nunique"),
            )
            .reset_index()
            .sort_values("銷量", ascending=False)
        )

        return agg.to_dict("records")

    def get_period_comparison(
        self, df_current: pd.DataFrame, df_previous: pd.DataFrame
    ) -> dict:
        """
        Growth rates: current vs previous period.

        Returns dict with current/previous values and growth rates for:
        net_sales, net_revenue, total_orders.
        """
        cur = self.get_summary_kpis(df_current)
        prev = self.get_summary_kpis(df_previous)

        def growth(cur_val, prev_val):
            if prev_val == 0:
                return None  # cannot compute
            return round((cur_val - prev_val) / abs(prev_val) * 100, 1)

        return {
            "current": cur,
            "previous": prev,
            "growth": {
                "net_sales": growth(cur["net_sales"], prev["net_sales"]),
                "net_revenue": growth(cur["net_revenue"], prev["net_revenue"]),
                "total_orders": growth(cur["total_orders"], prev["total_orders"]),
                "avg_order_value": growth(
                    cur["avg_order_value"], prev["avg_order_value"]
                ),
            },
        }

    def get_category_trend(self, df: pd.DataFrame) -> dict:
        """
        Monthly trend by 分類 (subcategory).

        Returns dict mapping 分類 -> list of {年月, 銷量, 營收}.
        """
        if df.empty:
            return {}

        agg = (
            df.groupby(["分類", "年月"])
            .agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum"))
            .reset_index()
            .sort_values("年月")
        )

        result = {}
        for cat, group in agg.groupby("分類"):
            result[cat] = [
                {
                    "年月": str(row["年月"]),
                    "銷量": int(row["銷量"]),
                    "營收": round(float(row["營收"]), 2),
                }
                for _, row in group.iterrows()
            ]
        return result

    def get_new_vs_backlist(
        self, df: pd.DataFrame, months_threshold: int = 6
    ) -> dict:
        """
        Classify books as 'new' (first sale < months_threshold ago) vs 'backlist'.

        Uses the earliest sale date across ALL loaded data to determine
        each book's first appearance, then classifies within the given df.

        Returns dict with keys 'new' and 'backlist', each containing
        銷量, 營收, 書數, and a books list.
        """
        if df.empty:
            return {
                "new": {"銷量": 0, "營收": 0, "書數": 0, "books": []},
                "backlist": {"銷量": 0, "營收": 0, "書數": 0, "books": []},
            }

        # Determine first sale date for every book from full dataset
        first_sale = (
            self.book_df.groupby("商品ID")["日期"]
            .min()
            .rename("首次銷售日")
        )

        # Cutoff: if a book's first sale is within the last N months, it's new
        if df["日期"].dropna().empty:
            cutoff = pd.Timestamp.now() - pd.DateOffset(months=months_threshold)
        else:
            ref_date = df["日期"].max()
            cutoff = ref_date - pd.DateOffset(months=months_threshold)

        tagged = df.merge(first_sale, on="商品ID", how="left")
        tagged["is_new"] = tagged["首次銷售日"] >= cutoff

        result = {}
        for label, is_new in [("new", True), ("backlist", False)]:
            subset = tagged[tagged["is_new"] == is_new]
            book_agg = (
                subset.groupby(["商品ID", "商品名稱", "作者名稱"])
                .agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum"))
                .reset_index()
                .sort_values("銷量", ascending=False)
            )
            result[label] = {
                "銷量": int(subset["售出商品數量"].sum()),
                "營收": round(float(subset["售出商品營收"].sum()), 2),
                "書數": int(subset["商品ID"].nunique()),
                "books": book_agg.head(10).to_dict("records"),
            }
        return result

    # ------------------------------------------------------------------
    # Convenience: full period report bundle
    # ------------------------------------------------------------------

    def build_period_report(
        self, period_type: str, period_value: str = None, books_only: bool = True
    ) -> dict:
        """
        One-call convenience method that returns all KPIs for a period.

        Returns dict with: period_type, period_value, kpis, top_books,
        channels, book_type, authors, comparison, category_trend,
        new_vs_backlist.
        """
        source = self.book_df if books_only else self.raw_df

        if period_value is None:
            period_value = self._latest_period_value(source, period_type)

        df_current = self.filter_period(period_type, period_value, books_only)

        prev_value = self.get_previous_period_value(period_type, period_value)
        df_previous = self.filter_period(period_type, prev_value, books_only)

        return {
            "period_type": period_type,
            "period_value": period_value,
            "previous_period_value": prev_value,
            "record_count": len(df_current),
            "kpis": self.get_summary_kpis(df_current),
            "top_books": self.get_top_books(df_current),
            "channels": self.get_channel_breakdown(df_current),
            "book_type": self.get_book_type_split(df_current),
            "authors": self.get_author_breakdown(df_current),
            "comparison": self.get_period_comparison(df_current, df_previous),
            "category_trend": self.get_category_trend(df_current),
            "new_vs_backlist": self.get_new_vs_backlist(df_current),
        }
