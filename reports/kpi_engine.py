"""
KPI 計算引擎：從處理後的 DataFrame 計算各項營運指標
供週報、月報、季報使用
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional


class KPIEngine:
    """核心 KPI 計算引擎，接收清洗後的 DataFrame，輸出結構化指標"""

    # ------------------------------------------------------------------ #
    #  1. 銷售總覽
    # ------------------------------------------------------------------ #
    def compute_sales_overview(self, df: pd.DataFrame,
                               df_prev: Optional[pd.DataFrame] = None) -> dict:
        """
        計算銷售總覽 KPI
        Args:
            df: 當期資料（已清洗，包含 售出商品數量, 售出商品營收, Order_ID 等欄位）
            df_prev: 前期資料（可選），用於計算成長率
        Returns:
            dict: total_units, total_revenue, total_orders, avg_order_value
                  若有前期: units_growth_pct, revenue_growth_pct, orders_growth_pct
        """
        # 排除退貨行計算淨值
        net = df[df["銷售方式"] != "外部(PdReturn)"] if "銷售方式" in df.columns else df

        total_units = int(net["售出商品數量"].sum())
        total_revenue = int(net["售出商品營收"].sum())
        total_orders = int(net["Order_ID"].nunique())
        avg_order_value = round(total_revenue / total_orders, 1) if total_orders > 0 else 0

        # 退貨統計
        returns = df[df["銷售方式"] == "外部(PdReturn)"] if "銷售方式" in df.columns else pd.DataFrame()
        return_units = int(abs(returns["售出商品數量"].sum())) if len(returns) > 0 else 0
        return_rate = round(return_units / (total_units + return_units) * 100, 1) if (total_units + return_units) > 0 else 0

        result = {
            "total_units": total_units,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "avg_order_value": avg_order_value,
            "return_units": return_units,
            "return_rate_pct": return_rate,
        }

        if df_prev is not None and len(df_prev) > 0:
            net_prev = df_prev[df_prev["銷售方式"] != "外部(PdReturn)"] if "銷售方式" in df_prev.columns else df_prev
            prev_units = int(net_prev["售出商品數量"].sum())
            prev_revenue = int(net_prev["售出商品營收"].sum())
            prev_orders = int(net_prev["Order_ID"].nunique())

            result["prev_units"] = prev_units
            result["prev_revenue"] = prev_revenue
            result["prev_orders"] = prev_orders
            result["units_growth_pct"] = self._growth_pct(total_units, prev_units)
            result["revenue_growth_pct"] = self._growth_pct(total_revenue, prev_revenue)
            result["orders_growth_pct"] = self._growth_pct(total_orders, prev_orders)

        return result

    # ------------------------------------------------------------------ #
    #  2. 暢銷書 Top N
    # ------------------------------------------------------------------ #
    def compute_top_books(self, df: pd.DataFrame, n: int = 10) -> list[dict]:
        """
        按銷量排名 Top N 書籍
        Returns:
            list[dict]: title, author, units, revenue, category, rank
        """
        net = self._exclude_returns(df)
        grouped = net.groupby(["商品名稱", "作者名稱", "分類"]).agg(
            units=("售出商品數量", "sum"),
            revenue=("售出商品營收", "sum"),
        ).reset_index().sort_values("units", ascending=False).head(n)

        results = []
        for rank, (_, row) in enumerate(grouped.iterrows(), 1):
            results.append({
                "rank": rank,
                "title": row["商品名稱"],
                "author": row["作者名稱"],
                "category": row["分類"],
                "units": int(row["units"]),
                "revenue": int(row["revenue"]),
            })
        return results

    # ------------------------------------------------------------------ #
    #  3. 通路分佈
    # ------------------------------------------------------------------ #
    def compute_channel_mix(self, df: pd.DataFrame) -> dict:
        """
        按銷售通路統計
        Returns:
            dict: labels, units[], revenue[], unit_pcts[], revenue_pcts[]
        """
        net = self._exclude_returns(df)
        if "銷售通路" not in net.columns:
            return {"labels": [], "units": [], "revenue": [],
                    "unit_pcts": [], "revenue_pcts": []}

        grouped = net.groupby("銷售通路").agg(
            units=("售出商品數量", "sum"),
            revenue=("售出商品營收", "sum"),
        ).sort_values("units", ascending=False)

        total_units = grouped["units"].sum()
        total_revenue = grouped["revenue"].sum()

        return {
            "labels": grouped.index.tolist(),
            "units": grouped["units"].astype(int).tolist(),
            "revenue": grouped["revenue"].astype(int).tolist(),
            "unit_pcts": (grouped["units"] / total_units * 100).round(1).tolist() if total_units > 0 else [],
            "revenue_pcts": (grouped["revenue"] / total_revenue * 100).round(1).tolist() if total_revenue > 0 else [],
        }

    # ------------------------------------------------------------------ #
    #  4. 紙本書 vs 電子書
    # ------------------------------------------------------------------ #
    def compute_book_type_split(self, df: pd.DataFrame) -> dict:
        """
        紙本書 vs 電子書比例
        Returns:
            dict: paper_units, ebook_units, paper_revenue, ebook_revenue, ebook_unit_ratio, ebook_revenue_ratio
        """
        net = self._exclude_returns(df)
        paper = net[net["分類"] == "紙本書"]
        ebook = net[net["分類"] == "電子書"]

        paper_units = int(paper["售出商品數量"].sum())
        ebook_units = int(ebook["售出商品數量"].sum())
        paper_revenue = int(paper["售出商品營收"].sum())
        ebook_revenue = int(ebook["售出商品營收"].sum())
        total_units = paper_units + ebook_units
        total_revenue = paper_revenue + ebook_revenue

        return {
            "paper_units": paper_units,
            "ebook_units": ebook_units,
            "paper_revenue": paper_revenue,
            "ebook_revenue": ebook_revenue,
            "total_units": total_units,
            "total_revenue": total_revenue,
            "ebook_unit_ratio": round(ebook_units / total_units * 100, 1) if total_units > 0 else 0,
            "ebook_revenue_ratio": round(ebook_revenue / total_revenue * 100, 1) if total_revenue > 0 else 0,
        }

    # ------------------------------------------------------------------ #
    #  5. 作者排名
    # ------------------------------------------------------------------ #
    def compute_author_ranking(self, df: pd.DataFrame, n: int = 15) -> list[dict]:
        """
        作者銷量排名
        Returns:
            list[dict]: rank, name, units, revenue, book_count, top_book
        """
        net = self._exclude_returns(df)
        author_agg = net.groupby("作者名稱").agg(
            units=("售出商品數量", "sum"),
            revenue=("售出商品營收", "sum"),
            book_count=("商品名稱", "nunique"),
        ).sort_values("units", ascending=False).head(n)

        # 找到每位作者的最暢銷書
        top_book_per_author = (
            net.groupby(["作者名稱", "商品名稱"])["售出商品數量"]
            .sum().reset_index()
            .sort_values("售出商品數量", ascending=False)
            .drop_duplicates(subset=["作者名稱"], keep="first")
            .set_index("作者名稱")["商品名稱"]
        )

        results = []
        for rank, (author, row) in enumerate(author_agg.iterrows(), 1):
            results.append({
                "rank": rank,
                "name": author,
                "units": int(row["units"]),
                "revenue": int(row["revenue"]),
                "book_count": int(row["book_count"]),
                "top_book": top_book_per_author.get(author, ""),
            })
        return results

    # ------------------------------------------------------------------ #
    #  6. 新書 vs 長銷書
    # ------------------------------------------------------------------ #
    def compute_new_vs_backlist(self, df: pd.DataFrame,
                                cutoff_months: int = 6) -> dict:
        """
        新書（上市 N 個月內）vs 長銷書
        Args:
            cutoff_months: 新書定義：上市後幾個月內算新書
        Returns:
            dict: new_units, new_pct, backlist_units, backlist_pct,
                  new_titles, backlist_titles, new_books[], backlist_top[]
        """
        net = self._exclude_returns(df)
        if "日期" not in net.columns:
            net = net.copy()
            net["日期"] = pd.to_datetime(net["日期控制"], format="mixed", errors="coerce")

        # 每本書的首次出現日
        first_sale = net.groupby("商品名稱")["日期"].min().reset_index()
        first_sale.columns = ["商品名稱", "首次銷售日"]

        period_end = net["日期"].max()
        cutoff_date = period_end - pd.DateOffset(months=cutoff_months)

        new_titles = first_sale[first_sale["首次銷售日"] >= cutoff_date]["商品名稱"].tolist()

        net_with_flag = net.copy()
        net_with_flag["is_new"] = net_with_flag["商品名稱"].isin(new_titles)

        new_df = net_with_flag[net_with_flag["is_new"]]
        back_df = net_with_flag[~net_with_flag["is_new"]]

        new_units = int(new_df["售出商品數量"].sum())
        back_units = int(back_df["售出商品數量"].sum())
        total = new_units + back_units

        # 新書明細
        new_books = (
            new_df.groupby(["商品名稱", "作者名稱"])
            .agg(units=("售出商品數量", "sum"))
            .reset_index().sort_values("units", ascending=False)
            .head(10)
        )
        new_books_list = [
            {"title": r["商品名稱"], "author": r["作者名稱"], "units": int(r["units"])}
            for _, r in new_books.iterrows()
        ]

        return {
            "new_units": new_units,
            "backlist_units": back_units,
            "new_pct": round(new_units / total * 100, 1) if total > 0 else 0,
            "backlist_pct": round(back_units / total * 100, 1) if total > 0 else 0,
            "new_title_count": len(new_titles),
            "backlist_title_count": int(net_with_flag[~net_with_flag["is_new"]]["商品名稱"].nunique()),
            "new_books": new_books_list,
        }

    # ------------------------------------------------------------------ #
    #  7. 每日趨勢
    # ------------------------------------------------------------------ #
    def compute_daily_trend(self, df: pd.DataFrame) -> dict:
        """
        每日銷售趨勢線
        Returns:
            dict: dates[], units[], revenue[], orders[]
        """
        net = self._exclude_returns(df)
        if "日期" not in net.columns:
            net = net.copy()
            net["日期"] = pd.to_datetime(net["日期控制"], format="mixed", errors="coerce")

        daily = net.groupby(net["日期"].dt.date).agg(
            units=("售出商品數量", "sum"),
            revenue=("售出商品營收", "sum"),
            orders=("Order_ID", "nunique"),
        ).sort_index()

        return {
            "dates": [str(d) for d in daily.index],
            "units": daily["units"].astype(int).tolist(),
            "revenue": daily["revenue"].astype(int).tolist(),
            "orders": daily["orders"].astype(int).tolist(),
        }

    # ------------------------------------------------------------------ #
    #  8. 異常警示
    # ------------------------------------------------------------------ #
    def compute_alerts(self, df: pd.DataFrame,
                       df_prev: Optional[pd.DataFrame] = None) -> list[dict]:
        """
        偵測異常：大幅下滑、異常高峰、退貨率過高等
        Returns:
            list[dict]: level (warning/danger/info), message, detail
        """
        alerts = []

        # (a) 退貨率警示
        overview = self.compute_sales_overview(df, df_prev)
        if overview["return_rate_pct"] > 10:
            alerts.append({
                "level": "warning",
                "title": "退貨率偏高",
                "message": f"本期退貨率 {overview['return_rate_pct']}%，超過 10% 警戒線",
                "detail": f"退貨數量: {overview['return_units']:,} 冊",
            })

        # (b) 與前期比較
        if df_prev is not None and len(df_prev) > 0:
            # 整體下滑
            if overview.get("units_growth_pct", 0) < -20:
                alerts.append({
                    "level": "danger",
                    "title": "銷量大幅下滑",
                    "message": f"本期銷量較前期下滑 {abs(overview['units_growth_pct'])}%",
                    "detail": f"本期 {overview['total_units']:,} 冊 vs 前期 {overview.get('prev_units', 0):,} 冊",
                })
            elif overview.get("units_growth_pct", 0) < -10:
                alerts.append({
                    "level": "warning",
                    "title": "銷量下滑",
                    "message": f"本期銷量較前期下滑 {abs(overview['units_growth_pct'])}%",
                    "detail": f"本期 {overview['total_units']:,} 冊 vs 前期 {overview.get('prev_units', 0):,} 冊",
                })

            # 整體成長 > 50% 也值得關注
            if overview.get("units_growth_pct", 0) > 50:
                alerts.append({
                    "level": "info",
                    "title": "銷量大幅成長",
                    "message": f"本期銷量較前期成長 {overview['units_growth_pct']}%",
                    "detail": "建議確認是否有特殊促銷活動或新書效應",
                })

            # (c) 個別書籍大幅下滑 (>50%)
            book_alerts = self._detect_book_decline(df, df_prev, threshold_pct=50)
            alerts.extend(book_alerts)

        # (d) 單日異常高峰
        daily_alerts = self._detect_daily_spikes(df)
        alerts.extend(daily_alerts)

        # 依嚴重度排序: danger > warning > info
        level_order = {"danger": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: level_order.get(a["level"], 3))

        return alerts

    # ------------------------------------------------------------------ #
    #  9. 經營摘要
    # ------------------------------------------------------------------ #
    def generate_executive_summary(self, kpis: dict) -> dict:
        """
        根據 KPI 資料自動生成經營摘要
        Args:
            kpis: 包含 overview, top_books, channel_mix, book_type, alerts 等 key
        Returns:
            dict: highlights (list[str]), concerns (list[str]), actions (list[str])
        """
        highlights = []
        concerns = []
        actions = []

        overview = kpis.get("overview", {})
        top_books = kpis.get("top_books", [])
        book_type = kpis.get("book_type", {})
        alerts = kpis.get("alerts", [])

        # --- 亮點 ---
        # 營收成長
        rev_growth = overview.get("revenue_growth_pct")
        if rev_growth is not None and rev_growth > 20:
            highlights.append(
                f"營收較前期大幅成長 {rev_growth}%，"
                f"達 ${overview['total_revenue']:,}"
            )
        elif rev_growth is not None and rev_growth > 0:
            highlights.append(
                f"營收較前期成長 {rev_growth}%，"
                f"達 ${overview['total_revenue']:,}"
            )

        # 暢銷書表現
        if top_books:
            best = top_books[0]
            highlights.append(
                f"本期冠軍《{best['title']}》（{best['author']}）"
                f"售出 {best['units']:,} 冊，營收 ${best['revenue']:,}"
            )

        # 電子書比例
        ebook_ratio = book_type.get("ebook_unit_ratio", 0)
        if ebook_ratio > 15:
            highlights.append(
                f"電子書佔比 {ebook_ratio}%，持續成長"
            )

        # 訂單數
        units_growth = overview.get("units_growth_pct")
        if units_growth is not None and units_growth > 10:
            highlights.append(
                f"銷量成長 {units_growth}%，共售出 {overview['total_units']:,} 冊"
            )

        # 確保至少 3 個亮點
        if len(highlights) < 3:
            highlights.append(
                f"本期共 {overview.get('total_orders', 0):,} 筆訂單，"
                f"平均客單價 ${overview.get('avg_order_value', 0):,}"
            )
        if len(highlights) < 3 and len(top_books) >= 3:
            top3_names = "、".join(
                f"《{b['title'][:10]}》" for b in top_books[:3]
            )
            highlights.append(f"暢銷 TOP3: {top3_names}")

        highlights = highlights[:3]

        # --- 警示 / 關注 ---
        if rev_growth is not None and rev_growth < -10:
            concerns.append(
                f"營收較前期下滑 {abs(rev_growth)}%，需關注原因"
            )
        if units_growth is not None and units_growth < -10:
            concerns.append(
                f"銷量較前期下滑 {abs(units_growth)}%"
            )
        if overview.get("return_rate_pct", 0) > 8:
            concerns.append(
                f"退貨率 {overview['return_rate_pct']}%，偏高"
            )

        danger_alerts = [a for a in alerts if a["level"] == "danger"]
        for a in danger_alerts[:2]:
            concerns.append(a["message"])

        # --- 行動建議 ---
        if rev_growth is not None and rev_growth < -10:
            actions.append("檢視通路促銷策略，評估是否需要加強行銷投放")
        if overview.get("return_rate_pct", 0) > 8:
            actions.append("與退貨率偏高的通路溝通，了解退貨原因並調整鋪貨策略")
        if ebook_ratio < 10:
            actions.append("電子書佔比偏低，建議加強電子書行銷與上架速度")
        if not actions:
            if top_books:
                actions.append(
                    f"持續推動暢銷書《{top_books[0]['title'][:15]}》的行銷力道"
                )
            actions.append("維持現有策略，關注下期新書上市表現")

        actions = actions[:2]

        return {
            "highlights": highlights,
            "concerns": concerns,
            "actions": actions,
        }

    # ------------------------------------------------------------------ #
    #  10. 分類趨勢（月報用）
    # ------------------------------------------------------------------ #
    def compute_category_trend(self, df: pd.DataFrame) -> dict:
        """
        按銷售形式/分類的月度趨勢（月報、季報使用）
        Returns:
            dict: months[], categories{category: units[]}
        """
        net = self._exclude_returns(df).copy()
        if "日期" not in net.columns:
            net["日期"] = pd.to_datetime(net["日期控制"], format="mixed", errors="coerce")

        net["年月"] = net["日期"].dt.to_period("M")
        monthly = net.groupby(["年月", "分類"])["售出商品數量"].sum().unstack(fill_value=0)

        months = [str(m) for m in monthly.index]
        categories = {}
        for col in monthly.columns:
            categories[col] = monthly[col].astype(int).tolist()

        return {"months": months, "categories": categories}

    # ------------------------------------------------------------------ #
    #  11. 全部 KPI 一次計算
    # ------------------------------------------------------------------ #
    def compute_all(self, df: pd.DataFrame,
                    df_prev: Optional[pd.DataFrame] = None,
                    report_type: str = "weekly") -> dict:
        """
        一次計算所有 KPI，回傳完整字典
        Args:
            df: 當期資料
            df_prev: 前期資料
            report_type: weekly / monthly / quarterly
        """
        kpis = {
            "overview": self.compute_sales_overview(df, df_prev),
            "top_books": self.compute_top_books(df, n=10),
            "channel_mix": self.compute_channel_mix(df),
            "book_type": self.compute_book_type_split(df),
            "daily_trend": self.compute_daily_trend(df),
            "alerts": self.compute_alerts(df, df_prev),
        }

        if report_type in ("monthly", "quarterly"):
            kpis["author_ranking"] = self.compute_author_ranking(df, n=15)
            kpis["new_vs_backlist"] = self.compute_new_vs_backlist(df)
            kpis["category_trend"] = self.compute_category_trend(df)
            kpis["top_books"] = self.compute_top_books(df, n=20)

        if report_type == "quarterly":
            kpis["top_books"] = self.compute_top_books(df, n=30)

        # 最後生成經營摘要
        kpis["executive_summary"] = self.generate_executive_summary(kpis)

        return kpis

    # ================================================================== #
    #  Private helpers
    # ================================================================== #
    @staticmethod
    def _exclude_returns(df: pd.DataFrame) -> pd.DataFrame:
        """排除退貨行"""
        if "銷售方式" in df.columns:
            return df[df["銷售方式"] != "外部(PdReturn)"]
        return df

    @staticmethod
    def _growth_pct(current: float, previous: float) -> float:
        """計算成長率百分比"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - previous) / abs(previous) * 100, 1)

    def _detect_book_decline(self, df: pd.DataFrame,
                             df_prev: pd.DataFrame,
                             threshold_pct: float = 50) -> list[dict]:
        """偵測個別書籍大幅下滑"""
        alerts = []
        net = self._exclude_returns(df)
        net_prev = self._exclude_returns(df_prev)

        curr_by_book = net.groupby("商品名稱")["售出商品數量"].sum()
        prev_by_book = net_prev.groupby("商品名稱")["售出商品數量"].sum()

        # 只看前期有一定銷量的書
        significant_prev = prev_by_book[prev_by_book >= 20]

        for title, prev_units in significant_prev.items():
            curr_units = curr_by_book.get(title, 0)
            decline_pct = (prev_units - curr_units) / prev_units * 100
            if decline_pct >= threshold_pct:
                alerts.append({
                    "level": "warning",
                    "title": "單書銷量大幅下滑",
                    "message": f"《{title[:20]}》銷量下滑 {decline_pct:.0f}%",
                    "detail": f"前期 {int(prev_units)} 冊 → 本期 {int(curr_units)} 冊",
                })

        # 最多回傳 5 筆
        return sorted(alerts, key=lambda a: a["message"])[:5]

    def _detect_daily_spikes(self, df: pd.DataFrame) -> list[dict]:
        """偵測單日異常高峰或低谷"""
        alerts = []
        trend = self.compute_daily_trend(df)
        if len(trend["units"]) < 3:
            return alerts

        units = np.array(trend["units"], dtype=float)
        mean_val = units.mean()
        std_val = units.std()

        if std_val == 0:
            return alerts

        for i, (date, val) in enumerate(zip(trend["dates"], units)):
            z_score = (val - mean_val) / std_val
            if z_score > 2.5:
                alerts.append({
                    "level": "info",
                    "title": "單日銷量異常高峰",
                    "message": f"{date} 銷量 {int(val):,} 冊，為平均的 {val/mean_val:.1f} 倍",
                    "detail": "建議確認是否有促銷活動或系統異常",
                })
            elif z_score < -2.0 and val >= 0:
                alerts.append({
                    "level": "info",
                    "title": "單日銷量異常低谷",
                    "message": f"{date} 銷量僅 {int(val):,} 冊，低於平均值 2 個標準差",
                    "detail": "可能為假日、系統問題或通路異常",
                })

        return alerts[:3]
