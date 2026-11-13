import pandas as pd
import json

from pathlib import Path

RAW_DATA_DIR = Path("data/raw")
COUNTRY_LOOKUP_CSV = Path("data/raw/country_lookup.csv")

COUNTRY_COLUMN_MAPPING= {
  "alpha-2": "country_code",
  "name": "country_name",
  "region": "continent",
  "sub-region": "sub_region"
}


def load_raw_stations(raw_path=None):
  """Load the raw stations data from a JSON file into a DataFrame."""
  if raw_path is None:
    files = sorted(RAW_DATA_DIR.glob("stations_*.json"))
    if not files:
      raise FileNotFoundError(f"No JSON files found in {RAW_DATA_DIR}")
    raw_path = files[-1]

  with Path(raw_path).open(encoding="utf-8") as fh:
    payload = json.load(fh)

  return pd.DataFrame(payload["stations"])


def load_country_lookup(csv_path=COUNTRY_LOOKUP_CSV):
  """Load the country lookup data from a CSV file into a DataFrame."""
  df = pd.read_csv(csv_path, keep_default_na=False)

  lookup_df = df[list(COUNTRY_COLUMN_MAPPING.keys())].rename(columns=COUNTRY_COLUMN_MAPPING)

  print(lookup_df.head(5))
  return lookup_df


def clean_invalid_country_codes(stations_df, country_df):
  """Replaces country codes not found in the country lookup into NULL"""
  df = stations_df.copy()

  valid_codes = set(
      country_df["country_code"].dropna().str.strip().str.upper()
  )
  valid_codes.discard("")

  is_invalid = df["countrycode"].notna() & ~df["countrycode"].isin(valid_codes)

  df.loc[is_invalid, "countrycode"] = pd.NA

  return df


def clean_stations(stations):
  """Clean and transform the stations DataFrame."""
  df = stations.copy()

  df = df.dropna(subset=["stationuuid", "name"])
  df = df.drop_duplicates(subset=["stationuuid"], keep="first")

  text_columns = [
    "stationuuid", "name", "url", "url_resolved",
    "homepage", "tags", "codec",
  ]

  for col in text_columns:
    df[col] = df[col].astype("string").str.strip()

  df["countrycode"] = (
    df["countrycode"].astype("string").str.strip().str.upper()
  )

  df.loc[df["countrycode"] == "", "countrycode"] = pd.NA

  numeric_columns = ["votes", "clickcount", "bitrate", "lastcheckok"]

  for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

  return df.reset_index(drop=True)


def run_transform():
  stations = load_raw_stations(raw_path=None)
  country = load_country_lookup()
  cleaned_stations = clean_stations(stations)
  print(cleaned_stations.head(5))

  valid_stations = clean_invalid_country_codes(cleaned_stations, country)

  return valid_stations, country


if __name__ == "__main__":
  run_transform()