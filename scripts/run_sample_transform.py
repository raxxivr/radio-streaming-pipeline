from pathlib import Path

from scripts.transform import (
    clean_invalid_country_codes,
    clean_stations,
    load_country_lookup,
    load_raw_stations,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_STATIONS_PATH = REPO_ROOT / "data" / "samples" / "stations_sample.json"
SAMPLE_COUNTRY_PATH = REPO_ROOT / "data" / "samples" / "country_lookup_sample.csv"


def run_sample_transform():
    """Run the transform rules on the committed synthetic snapshot."""
    raw = load_raw_stations(SAMPLE_STATIONS_PATH)
    country = load_country_lookup(SAMPLE_COUNTRY_PATH)
    cleaned = clean_stations(raw)
    valid = clean_invalid_country_codes(cleaned, country)

    valid_codes = set(
        country["country_code"].dropna().str.strip().str.upper()
    )
    valid_codes.discard("")
    invalid_codes = (
        cleaned["countrycode"].notna()
        & ~cleaned["countrycode"].isin(valid_codes)
    )

    print(f"\nRaw rows: {len(raw)}")
    print(f"Rows after cleaning: {len(cleaned)}")
    print(f"Rows after country validation: {len(valid)}")
    print(f"Invalid country codes nulled: {int(invalid_codes.sum())}")

    columns = ["stationuuid", "name", "countrycode", "codec", "bitrate"]
    print("\nTransformed sample:")
    print(valid[columns].to_string(index=False))

    return raw, valid, country


if __name__ == "__main__":
    run_sample_transform()
