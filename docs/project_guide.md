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
| 4 | Analytical SQL: five separate query files | Next |
| 5 | Integration test: one end-to-end check | Next |
| 6 | Root orchestrator: `run_pipeline.py` | Later |
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

Follow-up task: remove the unused `country_name`, `continent`, and `sub_region`
columns from the `stations` DDL. The normalized schema keeps those fields only in
`country`.

Acceptance criteria:

- `country` is loaded before `stations`.
- A row-count mismatch raises an error.
- Reruns do not duplicate rows.
- The `stations.countrycode` foreign key remains valid.

## Phase 4 - Analytical SQL

Next. Create five separate SQL files, one question per file.

| File | Question |
| --- | --- |
| `sql/stations_by_continent.sql` | Which continents have the most stations? |
| `sql/stations_by_country.sql` | Which countries have the most stations? |
| `sql/codec_distribution.sql` | Which codecs dominate the catalogue? |
| `sql/avg_bitrate_by_codec.sql` | What is the average bitrate by codec? |
| `sql/metadata_completeness.sql` | How much metadata is missing? |

Each query should join `stations` to `country` on:

```sql
stations.countrycode = country.country_code
```

Use a left join so stations with a blank or unknown country code still appear in
metadata-quality results.

Acceptance criteria:

- Each file runs independently with `psql`.
- Continent and country results use the `country` table, not duplicated station
  columns.
- Missing metadata is counted, not hidden.
- The five queries answer the questions above without manual cleanup.

## Phase 5 - Integration test

Next. `tests/test_pipeline.py` is intentionally blank for now.

The test should:

- Use dummy station records and a small dummy country lookup.
- Avoid the live API.
- Run the pipeline stages.
- Assert that the PostgreSQL `stations` table receives rows without raising an
  exception.

Acceptance criteria:

- The test runs against a reachable PostgreSQL database configured through
  `.env`.
- The test does not call the live Radio Browser API.
- The test fails if the load stage stops writing rows.

## Phase 6 - Root orchestrator

Later. `run_pipeline.py` is currently a placeholder.

The orchestrator should:

- Run extract, transform, and load in order.
- Stop at the first failure.
- Return a non-zero exit code on failure.

Acceptance criteria:

- `python run_pipeline.py` performs a full refresh in one command.
- The individual stages remain runnable for debugging.

## Phase 7 - Documentation

Done.

- `README.md` describes the pipeline, setup, analytics, and limitations.
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
- `run_pipeline.py`, the analytical SQL files, and the integration test are
  placeholders at this stage.
- The `stations` DDL still contains unused country columns; analytics should use
  the `country` table.

## Definition of done

- [x] Extract writes raw JSON and downloads the country CSV.
- [x] Transform cleans station rows and validates country codes.
- [x] Load writes `country` and `stations` to PostgreSQL.
- [ ] Five analytical SQL files are implemented.
- [ ] Integration test passes.
- [ ] `run_pipeline.py` runs all stages in order.
- [x] README, ERD, and implementation plan are updated.
- [ ] Unused country columns are removed from `stations`.

## Next actions

1. Implement the five SQL files in `sql/`.
2. Implement the integration test in `tests/test_pipeline.py`.
3. Run the SQL files and capture sample results for the README.
4. Wire `run_pipeline.py`.
5. Remove the unused country columns from the `stations` DDL.
