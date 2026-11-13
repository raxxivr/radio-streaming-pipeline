import os
import sys
import uuid
from pathlib import Path

import pandas as pd
import psycopg2
import pytest
from dotenv import dotenv_values
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ENV_PATH = PROJECT_ROOT / ".env"


def _db_config():
    file_values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}

    def pick(key, default=None):
        return file_values.get(key) or os.getenv(key) or default

    return {
        "host": pick("DB_HOST", "localhost"),
        "port": int(pick("DB_PORT", "5432")),
        "user": pick("DB_USER", "postgres"),
        "password": pick("DB_PASSWORD"),
    }


def _admin_connection(config):
    return psycopg2.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        dbname="postgres",
        connect_timeout=3,
    )


@pytest.mark.integration
def test_postgres_schema_load_and_constraints():
    config = _db_config()
    if not config["password"]:
        pytest.skip("DB_PASSWORD is not configured; skipping PostgreSQL test.")

    try:
        admin_conn = _admin_connection(config)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL is not available: {exc}")

    admin_conn.autocommit = True
    temp_db = f"radio_pipeline_test_{uuid.uuid4().hex[:12]}"
    test_engine = None
    database_created = False

    try:
        with admin_conn.cursor() as cursor:
            try:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temp_db))
                )
                database_created = True
            except psycopg2.Error as exc:
                pytest.skip(f"Could not create temporary database: {exc}")

        os.environ["DB_PASSWORD"] = config["password"]
        from scripts import load

        test_engine = create_engine(
            URL.create(
                "postgresql+psycopg2",
                username=config["user"],
                password=config["password"],
                host=config["host"],
                port=config["port"],
                database=temp_db,
            )
        )

        load.create_tables(test_engine)

        country_df = pd.DataFrame(
            [
                {
                    "country_code": "US",
                    "country_name": "United States of America",
                    "continent": "Americas",
                    "sub_region": "Northern America",
                }
            ]
        )
        stations_df = pd.DataFrame(
            [
                {
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
            ]
        )

        assert load.load_dataframe(country_df, "country", test_engine) == 1
        assert load.load_dataframe(stations_df, "stations", test_engine) == 1

        with test_engine.connect() as conn:
            assert (
                conn.execute(text("SELECT COUNT(*) FROM country")).scalar_one()
                == 1
            )
            assert (
                conn.execute(text("SELECT COUNT(*) FROM stations")).scalar_one()
                == 1
            )

            columns = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'stations'"
                    )
                )
                .scalars()
                .all()
            )
            assert {"stationuuid", "name", "countrycode", "loaded_at"} <= columns
            assert "country_name" not in columns

            fk_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.table_constraints "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'stations' "
                    "AND constraint_type = 'FOREIGN KEY'"
                )
            ).scalar_one()
            assert fk_count == 1

            loaded_at = conn.execute(
                text("SELECT loaded_at FROM stations")
            ).scalar_one()
            assert loaded_at is not None

        with pytest.raises(IntegrityError):
            with test_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO stations (stationuuid, name, countrycode) "
                        "VALUES ('bad-fk', 'Bad FK', 'ZZ')"
                    )
                )

        with pytest.raises(IntegrityError):
            with test_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO stations (stationuuid, name) "
                        "VALUES ('station-1', 'Duplicate UUID')"
                    )
                )

        with pytest.raises(IntegrityError):
            with test_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO stations (stationuuid, name) "
                        "VALUES ('no-name', NULL)"
                    )
                )

    finally:
        if test_engine is not None:
            test_engine.dispose()

        try:
            if database_created:
                with admin_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (temp_db,),
                    )
                    cursor.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {}").format(
                            sql.Identifier(temp_db)
                        )
                    )
        finally:
            admin_conn.close()
