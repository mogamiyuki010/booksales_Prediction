"""初始化 SQLite 資料庫：建立 schema 並載入種子資料"""
import sqlite3
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "booksales.db")
SCHEMA_PATH = os.path.join(DB_DIR, "schema.sql")
SEED_PATH = os.path.join(DB_DIR, "seed_cases.sql")


def init_database():
    # 若已存在則刪除重建
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 載入 schema
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    # 載入種子資料
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    conn.commit()

    # 驗證
    print("=== Authors ===")
    for row in cursor.execute("SELECT author_id, name, author_type FROM authors"):
        print(f"  {row}")

    print("\n=== Books ===")
    for row in cursor.execute("SELECT book_id, title, price_ntd, author_type_at_publish FROM books"):
        print(f"  {row}")

    print("\n=== Predictions (原始模型 vs 實際) ===")
    for row in cursor.execute(
        "SELECT b.title, p.sales_fy_low, p.sales_fy_high, p.actual_fy_sales, p.error_pct_fy "
        "FROM predictions p JOIN books b ON p.book_id = b.book_id"
    ):
        title, low, high, actual, err = row
        mid = (low + high) / 2
        print(f"  {title}: 預測 {low:,}-{high:,} (中位 {mid:,.0f}), 實際 {actual:,}, 誤差 {err}%")

    conn.close()
    print(f"\n資料庫建立完成: {DB_PATH}")


if __name__ == "__main__":
    init_database()
