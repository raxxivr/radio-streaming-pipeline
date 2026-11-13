import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# scripts.load creates an engine at import time but does not connect to it.
# Set a dummy value first so the tests do not require a real database password.
os.environ.setdefault("DB_PASSWORD", "test-password")

from scripts import extract, load, transform  # noqa: E402


def make_station(**overrides):
    row = {
        "stationuuid": "station-1",
        "name": "Station One",
        "url": "https://example.com/stream",
        "url_resolved": "https://example.com/stream",
        "homepage": "https://example.com",
        "tags": "news",
        "countrycode": "US",
        "votes": 1,
        "clickcount": 1,
        "codec": "MP3",
        "bitrate": 128,
        "lastcheckok": 1,
    }
    row.update(overrides)
    return row


@pytest.fixture
def raw_stations():
    return [
        make_station(
            stationuuid="s1",
            name=" Station A ",
            countrycode=" ph ",
            tags=" news ",
            votes="10",
            clickcount="5",
            bitrate="128",
            lastcheckok="1",
        ),
        # Duplicate UUID: clean_stations keeps the first row.
        make_station(stationuuid="s1", name="Duplicate", countrycode="US", bitrate="256"),
        # Missing name: dropped by clean_stations.
        make_station(stationuuid="s2", name=None, countrycode="US"),
        # Blank country code and non-numeric bitrate.
        make_station(
            stationuuid="s3",
            name="Station C",
            countrycode="",
            bitrate="not-a-number",
            votes="3",
        ),
    ]


@pytest.fixture
def country_lookup():
    return pd.DataFrame(
        [
            {
                "country_code": "PH",
                "country_name": "Philippines",
                "continent": "Asia",
                "sub_region": "South-eastern Asia",
            }
        ]
    )


def test_fetch_stations_requests_the_api_and_keeps_station_fields(monkeypatch):
    response = Mock()
    response.json.return_value = [
        make_station(stationuuid="api-1", extra_field="this should be removed")
    ]
    response.raise_for_status.return_value = None

    get = Mock(return_value=response)
    monkeypatch.setattr(extract.requests, "get", get)

    stations = extract.fetch_stations(limit=10, offset=5)

    assert len(stations) == 1
    assert set(stations[0]) == set(extract.STATION_FIELDS)
    assert stations[0]["stationuuid"] == "api-1"
    assert "extra_field" not in stations[0]

    args, kwargs = get.call_args
    assert args[0] == f"{extract.API_BASE_URL}/json/stations/search"
    assert kwargs["params"]["limit"] == 10
    assert kwargs["params"]["offset"] == 5
    assert kwargs["params"]["hidebroken"] == "true"
    assert kwargs["params"]["order"] == "clickcount"
    assert kwargs["params"]["reverse"] == "true"
    assert kwargs["timeout"] == int(extract.REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status.assert_called_once_with()


def test_fetch_stations_propagates_api_failure(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("API down")
    monkeypatch.setattr(extract.requests, "get", Mock(return_value=response))

    with pytest.raises(RuntimeError, match="API down"):
        extract.fetch_stations()


def test_clean_stations_deduplicates_trims_and_casts(raw_stations):
    cleaned = transform.clean_stations(pd.DataFrame(raw_stations))

    assert cleaned["stationuuid"].tolist() == ["s1", "s3"]
    assert cleaned.loc[0, "name"] == "Station A"
    assert cleaned.loc[0, "countrycode"] == "PH"
    assert cleaned.loc[0, "tags"] == "news"
    assert cleaned.loc[0, "votes"] == 10
    assert cleaned.loc[0, "bitrate"] == 128
    assert pd.isna(cleaned.loc[1, "countrycode"])
    assert pd.isna(cleaned.loc[1, "bitrate"])


def test_clean_invalid_country_codes_nulls_unmatched_codes(country_lookup):
    stations = pd.DataFrame(
        [
            make_station(stationuuid="s1", countrycode="PH"),
            make_station(stationuuid="s2", countrycode="ZZ"),
            make_station(stationuuid="s3", countrycode=None),
        ]
    )

    cleaned = transform.clean_invalid_country_codes(stations, country_lookup)

    assert cleaned.loc[0, "countrycode"] == "PH"
    assert pd.isna(cleaned.loc[1, "countrycode"])
    assert pd.isna(cleaned.loc[2, "countrycode"])


def test_run_transform_returns_country_data_separately(
    monkeypatch, raw_stations, country_lookup
):
    monkeypatch.setattr(
        transform,
        "load_raw_stations",
        lambda raw_path=None: pd.DataFrame(raw_stations),
    )
    monkeypatch.setattr(transform, "load_country_lookup", lambda: country_lookup)

    stations, lookup = transform.run_transform()

    assert stations["stationuuid"].tolist() == ["s1", "s3"]
    assert "country_name" not in stations.columns
    assert "continent" not in stations.columns
    pd.testing.assert_frame_equal(lookup, country_lookup)
    assert stations.loc[0, "countrycode"] == "PH"
    assert pd.isna(stations.loc[1, "countrycode"])


def test_run_load_loads_country_before_stations(monkeypatch):
    stations = pd.DataFrame([make_station(stationuuid="s1")])
    country = pd.DataFrame(
        [
            {
                "country_code": "US",
                "country_name": "United States of America",
                "continent": "Americas",
                "sub_region": "Northern America",
            }
        ]
    )
    calls = []
    create_tables = Mock()

    def fake_load_dataframe(df, table_name, engine):
        calls.append((table_name, df, engine))
        return len(df)

    monkeypatch.setattr(load, "create_tables", create_tables)
    monkeypatch.setattr(load, "load_dataframe", fake_load_dataframe)

    result = load.run_load(stations_df=stations, country_df=country)

    assert [call[0] for call in calls] == ["country", "stations"]
    assert calls[0][1] is country
    assert calls[1][1] is stations
    assert result == (1, 1)
    create_tables.assert_called_once_with(load.engine)


def test_save_raw_json_writes_expected_envelope(tmp_path):
    output_path = tmp_path / "stations.json"

    saved_path = extract.save_raw_json(
        [make_station(stationuuid="s1")],
        output_path=output_path,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved_path == output_path
    assert payload["count"] == 1
    assert payload["stations"][0]["stationuuid"] == "s1"
    assert "fetched_at" in payload


def test_committed_sample_snapshot_transforms_reproducibly():
    sample_dir = PROJECT_ROOT / "data" / "samples"

    raw = transform.load_raw_stations(sample_dir / "stations_sample.json")
    country = transform.load_country_lookup(
        sample_dir / "country_lookup_sample.csv"
    )
    cleaned = transform.clean_stations(raw)
    valid = transform.clean_invalid_country_codes(cleaned, country)

    assert len(raw) == 10
    assert len(cleaned) == 8
    assert len(valid) == 8

    assert valid["stationuuid"].tolist() == [
        "sample-0001",
        "sample-0002",
        "sample-0003",
        "sample-0006",
        "sample-0007",
        "sample-0008",
        "sample-0009",
        "sample-0010",
    ]
    assert valid.loc[2, "name"] == "Sample Classical"
    assert valid.loc[2, "countrycode"] == "DE"
    assert pd.isna(valid.loc[4, "countrycode"])
    assert pd.isna(valid.loc[4, "bitrate"])
    assert pd.isna(valid.loc[5, "countrycode"])
    assert pd.isna(valid.loc[5, "bitrate"])
    assert valid.loc[3, "bitrate"] == 0
