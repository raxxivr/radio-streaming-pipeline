# Implementation Plan

Project: Radio Streaming Pipeline
Last updated: 2026-11-13

This is the implementation plan for the current pipeline. It records what is
done, what is next, and the acceptance criteria for each phase.

## Goal

Build a small, reproducible ETL pipeline that turns a Radio Browser API snapshot
plus a local country lookup into two PostgreSQL tables, then answers a fixed set
of analytical questions with SQL.

The pipeline is intentionally batch-oriented for now. It fetches one snapshot,
cleans it, loads it, and runs SQL against the result. A scheduler or continuous
polling loop can be added later.

## Current status

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Repository scaffold and configuration | Done |
| 1 | Extract: API fetch, raw JSON, country CSV | Done |
| 2 | Transform: clean stations and validate country codes | Done |
| 3 | Load: country and stations tables in PostgreSQL | Done |
| 4 | Analytical SQL: five separate query files | Done |
| 5 | Test suite for the ETL stages | Done |
| 6 | Root orchestrator: `run_pipeline.py` | Done |
| 7 | Documentation: README, ERD, plan | Done |

## Phase 0 - Repository scaffold

Done.

- `data/raw/` stores generated JSON and the downloaded country CSV.
- `.env` holds local credentials and is gitignored.
- `.env.example` is committed with placeholder values.
- `requirements.txt` pins the pipeline dependencies.
- No `DECISIONS.md` in this repository.

Acceptance criteria:

- A fresh clone can create a virtual environment and install dependencies.
- `.env` is never committed.
- Generated data under `data/raw/` is never committed.

## Phase 1 - Extract

Done in `scripts/extract.py`.

Responsibilities:

- Fetch up to `API_LIMIT` stations from the Radio Browser API.
- Keep only the fields listed in `STATION_FIELDS`.
- Write a timestamped JSON envelope to `data/raw/stations_<timestamp>.json`.
- Download the ISO-3166 country lookup CSV to `data/raw/country_lookup.csv`.
- Validate that the lookup CSV contains the expected source columns.

Current commands:

```powershell
python -m scripts.extract
```

Acceptance criteria:

- One raw JSON file is written per extract run.
- The JSON envelope contains `fetched_at`, `count`, and `stations`.
- The country lookup CSV can be read and has the expected columns.
- A failed HTTP request raises an error instead of writing a partial file.

## Phase 2 - Transform

Done in `scripts/transform.py`.

Responsibilities:

- Read the newest raw station JSON file.
- Drop rows with a blank `stationuuid` or `name`.
- Remove duplicate `stationuuid` values.
- Strip whitespace from text fields.
- Uppercase `countrycode` and convert blank values to null.
- Convert `votes`, `clickcount`, `bitrate`, and `lastcheckok` to numeric.
- Replace country codes not present in the lookup with null.

Design decision: the transform does **not** merge country metadata onto station
rows. Country metadata stays in the `country` table and is joined in analytical
SQL. This keeps the loaded station data normalized.

Acceptance criteria:

- No duplicate `stationuuid` values.
- No null `name` values.
- Numeric columns have numeric dtypes.
- Invalid country codes become null.
- The returned stations DataFrame and country DataFrame are separate.

## Phase 3 - Load

Done in `scripts/load.py`.

Responsibilities:

- Create the `country` and `stations` tables if they do not exist.
- Load `country` first so the foreign key on `stations.countrycode` is valid.
- Truncate the target tables before loading.
- Verify the loaded row count matches the DataFrame row count.

Current command:

```powershell
python -m scripts.load
```

This command calls `run_transform()` and then `run_load()`, so it performs the
transform and load stages together.

Design decision: each run is a full refresh. The loader truncates the target
tables and appends the current snapshot.

Schema cleanup: the unused `country_name`, `continent`, and `sub_region` columns
were removed from the `stations` DDL. Country metadata now lives only in
`country`. Existing databases created before this change may still contain the
old columns because `CREATE TABLE IF NOT EXISTS` does not alter an existing
table.

Acceptance criteria:

- `country` is loaded before `stations`.
- A row-count mismatch raises an error.
- Reruns do not duplicate rows.
- The `stations.countrycode` foreign key remains valid.

## Phase 4 - Analytical SQL

Done. The five SQL files are implemented, one question per file.

| File | Question |
| --- | --- |
| `sql/stations_by_continent.sql` | Which continents have the most stations? |
| `sql/stations_by_country.sql` | Which countries have the most stations? |
| `sql/codec_distribution.sql` | Which codecs dominate the catalogue? |
| `sql/avg_bitrate_by_codec.sql` | What is the average bitrate by codec? |
| `sql/metadata_completeness.sql` | How much metadata is missing? |

Implementation notes:

- `stations_by_continent.sql` starts from `stations` and left joins `country`,
  so stations with no matched country code, plus matched countries with a blank
  continent, remain in the `Unknown` bucket. The current snapshot returns
  6 rows with `Unknown = 12`.
- `stations_by_country.sql` starts from `stations` and inner joins `country`, so
  it returns only countries with at least one station. The current snapshot
  returns 83 rows covering 996 stations.
- `codec_distribution.sql` normalizes blank codecs and calculates share with a
  window function.
- `avg_bitrate_by_codec.sql` filters to `bitrate > 0` before averaging.
- `metadata_completeness.sql` uses `CROSS JOIN LATERAL` and `COUNT(*) FILTER`
  to return one row per metadata field.

All five files were run successfully against the local `radio_pipeline`
database. `scripts/run_analytics.py` executes them and prints the result sets.

Acceptance criteria:

- [x] Each file runs independently with `psql`.
- [x] Continent and country results use the `country` table, not duplicated
  station columns.
- [x] Missing metadata is counted, not hidden.
- [x] The five queries answer the questions above without manual cleanup.

## Phase 5 - Test suite

Done. The default suite contains unit tests and one PostgreSQL integration test.

`tests/test_pipeline.py` imports the real ETL modules:

- `scripts.extract`
- `scripts.transform`
- `scripts.load`

The unit tests mock `requests.get` and the load functions, so they do not call
the live API and do not modify PostgreSQL.

`tests/test_postgres_integration.py` creates a temporary database, runs
`create_tables()` and `load_dataframe()` against it, verifies the table columns,
loaded timestamps, foreign key, primary key, and `NOT NULL` constraints, then
drops the database. It skips cleanly when PostgreSQL is unavailable.

The committed `data/samples/` fixture is also tested so the transform can be
reproduced without the live API.

Coverage:

- API request parameters and station-field filtering.
- API failure propagation.
- Station cleaning, deduplication, trimming, and numeric casting.
- Invalid country-code handling.
- `run_transform()` returning station and country DataFrames separately.
- `run_load()` loading `country` before `stations`.
- Raw JSON envelope writing.
- Committed sample snapshot transformation.
- Temporary PostgreSQL schema, load, and constraint checks.

Current result: `9 passed` locally. Without PostgreSQL the integration test
skips and the unit result is `8 passed, 1 skipped`.

Acceptance criteria:

- [x] The unit tests run without the live Radio Browser API.
- [x] The integration test skips cleanly without PostgreSQL.
- [x] The integration test covers real database schema, load, and constraints.
- [x] The committed sample fixture reproduces the transform without the live API.
- [x] The suite fails if the transform or load orchestration regresses.

## Phase 6 - Root orchestrator

Done. `run_pipeline.py` runs the full pipeline:

1. `scripts.extract` - fetch the API snapshot and country lookup.
2. `scripts.load` - transform and load both tables.
3. `scripts.run_analytics` - execute and print the five SQL queries.
4. `pytest -q` - run the ETL test suite.

The orchestration uses `python -m` so package imports resolve correctly. It
stops at the first non-zero exit code.

Acceptance criteria:

- [x] `python run_pipeline.py` performs a full refresh and runs analytics.
- [x] The individual stages remain runnable for debugging.
- [x] The pipeline stops at the first failure.

## Phase 7 - Documentation

Done.

- `README.md` describes the pipeline, setup, analytics, and limitations.
- `docs/analytics_results.png` shows the current analytics dashboard.
- `data/samples/` provides a committed reproducible transformation fixture.
- `docs/erd.md` documents the two-table normalized schema and SQL join.
- This file records the implementation plan and current status.

## Data model

```text
country
  country_code (PK)
  country_name
  continent
  sub_region

stations
  stationuuid (PK)
  name
  url
  url_resolved
  homepage
  tags
  countrycode (FK -> country.country_code)
  votes
  clickcount
  codec
  bitrate
  lastcheckok
  loaded_at
```

The analytical join is:

```sql
SELECT
    s.*,
    c.country_name,
    c.continent,
    c.sub_region
FROM stations AS s
LEFT JOIN country AS c
    ON s.countrycode = c.country_code;
```

## Risks and constraints

- The API snapshot is a sample ordered by clickcount, not a full census.
- The API is live, so two extract runs can return different rows.
- `data/raw/` is gitignored; a fresh clone must run extract before transform.
- `country_lookup.csv` is downloaded by extract and is not committed.
- The loader uses `TRUNCATE ... CASCADE` on `country`, which also clears
  `stations`; load `country` first, then `stations`.
- The unit tests mock database writes; the integration test requires a reachable
  PostgreSQL server and `CREATEDB` permission, and skips otherwise.
- Existing databases created before the schema cleanup may still contain the old
  unused country columns; `CREATE TABLE IF NOT EXISTS` does not alter an
  existing table.
- SQL results depend on the current API snapshot and country lookup.
- The committed sample snapshot is synthetic and small; it is for reproducible
  transformation checks, not analysis.
- The analytics dashboard is a point-in-time view; refreshing the snapshot
  changes the numbers.

## Definition of done

- [x] Extract writes raw JSON and downloads the country CSV.
- [x] Transform cleans station rows and validates country codes.
- [x] Load writes `country` and `stations` to PostgreSQL.
- [x] Five analytical SQL files are implemented.
- [x] All five SQL files run successfully against the local database.
- [x] Test suite passes.
- [x] PostgreSQL integration test creates and drops a temporary database.
- [x] Committed sample snapshot reproduces the transform without the live API.
- [x] `run_pipeline.py` runs all stages in order.
- [x] README, ERD, and implementation plan are updated.
- [x] Unused country columns are removed from the `stations` DDL.

## Next actions

1. Optionally add a scheduler or continuous polling loop.
2. Optionally expand the sample fixture or add analytics fixtures.
3. Optionally rebuild the analytics dashboard after a data refresh.
