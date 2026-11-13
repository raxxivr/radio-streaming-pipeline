import os
import json
import requests
import pandas as pd

from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "https://de1.api.radio-browser.info")
API_LIMIT = os.getenv("API_LIMIT", "1000")
REQUEST_TIMEOUT_SECONDS = os.getenv("REQUEST_TIMEOUT_SECONDS", "30")

RAW_DATA_DIR = Path("data/raw")

STATION_FIELDS = [
    "stationuuid",
    "name",
    "url",
    "url_resolved",
    "homepage",
    "tags",
    "countrycode",
    "votes",
    "clickcount",
    "codec",
    "bitrate",
    "lastcheckok"
]

LOOKUP_COLUMNS = [
    "alpha-2",
    "name",
    "region",
    "sub-region"
]

def ensure_directories():
   """Creates a data/raw folder if it doesn't exist."""
   os.makedirs(RAW_DATA_DIR, exist_ok=True)

def fetch_stations(limit=API_LIMIT, offset=0):
   url = f"{API_BASE_URL}/json/stations/search"
   params = {
        "limit": limit,
        "offset": offset,
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true"
   }
   headers = {
        "User-Agent": "RadioStreamingPipeline/1.0 (learning project)"
   }

   response = requests.get(
      url,
      params=params,
      headers=headers,
      timeout=int(REQUEST_TIMEOUT_SECONDS)
   )
   response.raise_for_status()

   rows = response.json()

   return [
      {field: row.get(field) for field in STATION_FIELDS}
      for row in rows
   ]


def save_raw_json(stations, output_path=None):
    ensure_directories()
    print("Extracting stations...")

    if output_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = RAW_DATA_DIR / f"stations_{stamp}.json"
    else:
        output_path = Path(output_path)

    payload = {
       "fetched_at": datetime.now(timezone.utc).isoformat(),
       "count": len(stations),
       "stations": stations
    }

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"Successfully extracted {len(stations)} stations to {output_path}\n")
    return output_path


def download_csv(url, filename):
    ensure_directories()
    save_path = os.path.join(RAW_DATA_DIR, filename)

    print(f"Downloading CSV from {url}")

    df = pd.read_csv(url)
    df.to_csv(save_path, index=False)
   
    print(f"Successfully saved to {save_path}\n")
    return save_path


def read_country_lookup_csv(path=None):
    if path is None:
        path = RAW_DATA_DIR / "country_lookup.csv"

    lookup = pd.read_csv(path)

    missing = [column for column in LOOKUP_COLUMNS if column not in lookup.columns]

    if missing:
        raise ValueError(f"Country lookup is missing columns: {missing}")

    return lookup


def main():
    stations = fetch_stations(limit=API_LIMIT, offset=0)
    save_raw_json(stations)
    
    csv_url = "https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/99cdae15c839bb4f94a23db4e47b4a4c590dec61/all/all.csv"
    download_csv(csv_url, "country_lookup.csv")
    print(read_country_lookup_csv().shape)


if __name__ == "__main__":
    main()
