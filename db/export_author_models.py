"""從 SQLite 匯出作者預估模型校對資料 -> data/author_models.json + data/config_v2.json"""
import argparse
import sqlite3
import subprocess
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError(
        "pyyaml is required. Install it with: pip install pyyaml\n"
        "Or: pip install -r requirements.txt"
    )

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "booksales.db"
OUT_PATH = ROOT / "data" / "author_models.json"
CONFIG_YAML_PATH = ROOT / "models" / "heuristic" / "config_v2.yaml"
CONFIG_JSON_PATH = ROOT / "data" / "config_v2.json"


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    authors = [row_to_dict(r) for r in cur.execute("SELECT * FROM authors ORDER BY author_id").fetchall()]
    books = [row_to_dict(r) for r in cur.execute("SELECT * FROM books ORDER BY author_id, publish_date").fetchall()]
    metrics = [row_to_dict(r) for r in cur.execute("SELECT * FROM author_metrics_history ORDER BY author_id, snapshot_date").fetchall()]
    predictions = [row_to_dict(r) for r in cur.execute("SELECT * FROM predictions ORDER BY book_id").fetchall()]
    params = [row_to_dict(r) for r in cur.execute("SELECT * FROM model_parameters ORDER BY param_id").fetchall()]

    author_map = {a["author_id"]: a for a in authors}
    for a in authors:
        a["mentor_name"] = author_map[a["mentor_author_id"]]["name"] if a.get("mentor_author_id") else None
        a["books"] = []
        a["metrics_history"] = [m for m in metrics if m["author_id"] == a["author_id"]]

    pred_by_book = {p["book_id"]: p for p in predictions}
    for b in books:
        b["prediction"] = pred_by_book.get(b["book_id"])
        if b["author_id"] in author_map:
            author_map[b["author_id"]]["books"].append(b)

    out = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "db_path": str(DB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "authors": authors,
        "model_parameters": params,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[author_models] Exported {len(authors)} authors, {len(books)} books, {len(metrics)} metric snapshots -> {OUT_PATH}")

    # --- Export config_v2.yaml as JSON ---
    export_config_v2()


def export_config_v2():
    """Read config_v2.yaml -> data/config_v2.json with predictor_extensions."""
    if not CONFIG_YAML_PATH.exists():
        print(f"[config_v2] WARNING: {CONFIG_YAML_PATH} not found, skipping.")
        return

    with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Add predictor-specific calibrations not present in the YAML
    config["predictor_extensions"] = {
        "cmoney_conversion_rate": {"min": 0.15, "max": 0.28},
        "category_multiplier": {
            "finance": 1.00,
            "growth": 0.60,
            "business": 0.75,
        },
    }

    CONFIG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_JSON_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    top_keys = list(config.keys())
    print(f"[config_v2] Exported {len(top_keys)} sections -> {CONFIG_JSON_PATH}")
    print(f"            Sections: {', '.join(top_keys)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="匯出作者模型資料為靜態 JSON")
    parser.add_argument("--push", action="store_true", help="匯出後自動 git add + commit + push")
    args = parser.parse_args()

    main()

    if args.push:
        subprocess.run(["git", "add", str(OUT_PATH), str(CONFIG_JSON_PATH)], cwd=str(ROOT))
        subprocess.run(["git", "commit", "-m", "data: update author_models.json + config_v2.json"], cwd=str(ROOT))
        subprocess.run(["git", "push"], cwd=str(ROOT))
        print("Pushed to remote.")
