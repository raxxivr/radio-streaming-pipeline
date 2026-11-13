import os
import pandas as pd

from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from scripts.transform import load_country_lookup, run_transform

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "radio_pipeline")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD is not set. Copy .env.example to .env and set DB_PASSWORD."
    )

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
engine = create_engine(DATABASE_URL)


def create_tables(db_engine=engine):
  """Creates both the country and stations tables if they do not exist."""

  ddl_statements = """
    CREATE TABLE IF NOT EXISTS country (
      country_code TEXT PRIMARY KEY,
      country_name TEXT NOT NULL,
      continent TEXT,
      sub_region TEXT
    );

    CREATE TABLE IF NOT EXISTS stations (
      stationuuid   TEXT PRIMARY KEY,
      name          TEXT NOT NULL,
      url           TEXT,
      url_resolved  TEXT,
      homepage      TEXT,
      tags          TEXT,
      countrycode   TEXT REFERENCES country(country_code),
      votes         INTEGER,
      clickcount    INTEGER,
      codec         TEXT,
      bitrate       INTEGER,
      lastcheckok   INTEGER,
      country_name  TEXT,
      continent     TEXT,
      sub_region    TEXT,
      loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  """
  with engine.begin() as conn:
    conn.exec_driver_sql(ddl_statements)
  print("Tables created successfully.")


def load_dataframe(df, table_name, engine):
  """Truncates the target table, loads the DataFrame, and verifies row counts."""
  with engine.begin() as conn:
     conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))

  df.to_sql(
    name=table_name,
    con=engine,
    if_exists="append",
    index=False
  )

  with engine.connect() as conn:
    db_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()

  if db_count != len(df):
    raise RuntimeError(
      f"Row mismatch in '{table_name}': expected {len(df)}, found {db_count}"
    )

  print(f"Loaded {db_count} rows into '{table_name}'.")
  return db_count


def run_load(stations_df, country_df):
  """Load the country lookup first, then the stations that reference it."""
  create_tables(engine)

  country_loaded = load_dataframe(country_df, "country", engine)
  stations_loaded = load_dataframe(stations_df, "stations", engine)

  print(f"Loaded {country_loaded} rows into country")
  print(f"Loaded {stations_loaded} rows into stations")

  return country_loaded, stations_loaded


if __name__ == "__main__":
  stations_df, country_df = run_transform()
  run_load(stations_df=stations_df, country_df=country_df)