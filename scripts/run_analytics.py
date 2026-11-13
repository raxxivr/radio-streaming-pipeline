from pathlib import Path

import pandas as pd
from sqlalchemy import text

from scripts.load import engine

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = REPO_ROOT / "sql"

ANALYTICS = [
    ("Stations by continent", "stations_by_continent.sql"),
    ("Top countries by station count", "stations_by_country.sql"),
    ("Codec distribution", "codec_distribution.sql"),
    ("Average bitrate by codec", "avg_bitrate_by_codec.sql"),
    ("Metadata completeness", "metadata_completeness.sql"),
]


def run_analytics():
    """Run each analytical SQL file and print its result set."""
    results = {}

    for title, filename in ANALYTICS:
        sql_path = SQL_DIR / filename
        query = sql_path.read_text(encoding="utf-8").strip()

        if query.endswith(";"):
            query = query[:-1]

        with engine.connect() as conn:
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = result.fetchall()

        df = pd.DataFrame(rows, columns=columns)
        results[filename] = df

        print(f"\n>>> {title}")
        print(f"Rows returned: {len(df)}")
        print(df.head(10).to_string(index=False))

        if len(df) > 10:
            print(f"... {len(df) - 10} more rows")

    print("\nAll analytical queries completed successfully.")
    return results


if __name__ == "__main__":
    run_analytics()
