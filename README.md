# Radio Streaming Pipeline

A reproducible batch ETL pipeline for live radio station metadata. It fetches a
snapshot from the [Radio Browser API](https://api.radio-browser.info/), downloads
an ISO-3166 country lookup, cleans the station records, and loads both the
country lookup and the station rows into PostgreSQL. Analytical SQL joins the
two tables.

## Status

Extract, transform, and load are implemented. All five analytical SQL queries
are implemented and were run against the local `radio_pipeline` database. The
test suite is implemented and passes: `7 passed`.

`run_pipeline.py` is the only remaining implementation step and is intentionally
left as an empty placeholder. Run the stages individually until it is wired. The
tests mock the API and database writes, so they do not require a live PostgreSQL
connection.

## Problem

The Radio Browser API is a live, messy catalogue of internet radio stations.
Answering basic questions about the catalogue requires cleaning blank country
codes, zero bitrates, inconsistent codecs, duplicate station UUIDs, and
comma-separated tags.

The pipeline answers five questions:

| Question | SQL file |
| --- | --- |
| Which continents have the most stations? | `sql/stations_by_continent.sql` |
| Which countries have the most stations? | `sql/stations_by_country.sql` |
| Which codecs dominate the catalogue? | `sql/codec_distribution.sql` |
| What is the average bitrate by codec? | `sql/avg_bitrate_by_codec.sql` |
| How much metadata is missing? | `sql/metadata_completeness.sql` |

The country lookup is loaded into its own table. The station table keeps only a
`countrycode` foreign key, and the analytical queries join the two tables. The
pipeline does not duplicate country metadata on every station row.

## Data sources

| Source | Type | Location | Used by |
| --- | --- | --- | --- |
| Radio Browser API | Live REST API | `https://de1.api.radio-browser.info` | `scripts/extract.py` |
| Country lookup | Local CSV download | `data/raw/country_lookup.csv` (gitignored) | `scripts/extract.py` and `scripts/transform.py` |

The country lookup is downloaded by `scripts/extract.py` from a pinned ISO-3166
source. It is not committed because `data/raw/` is gitignored. A fresh clone
must run the extract stage before the transform stage.

## Architecture

```text
Radio Browser API
        |
        v
data/raw/stations_<timestamp>.json   (gitignored)
        |
        v
scripts/transform.py
  clean -> type-cast -> validate country codes
        |
        v
scripts/load.py
  country table  +  stations table
        |
        v
analytical SQL
  stations LEFT JOIN country ON countrycode = country_code
```

`scripts/load.py` calls `run_transform()` and then `run_load()`, so the load
command performs the transform and load stages together.

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL running locally
- A PostgreSQL user that can create tables

### 1. Create the database

```sql
CREATE DATABASE radio_pipeline;
```

If the database already exists, skip this step.

### 2. Clone and install

```powershell
git clone https://github.com/raxxivr/radio-streaming-pipeline.git
cd radio-streaming-pipeline

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On bash:

```bash
git clone https://github.com/raxxivr/radio-streaming-pipeline.git
cd radio-streaming-pipeline

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure the environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `DB_PASSWORD`:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=radio_pipeline
DB_USER=postgres
DB_PASSWORD=your-password
```

`.env` is gitignored. Only `.env.example` with placeholder values is committed.

### 4. Run the ETL stages

Run the extract stage first:

```powershell
python -m scripts.extract
```

This writes a timestamped JSON file and downloads `country_lookup.csv` into
`data/raw/`.

Then run the transform and load stages:

```powershell
python -m scripts.load
```

`scripts/load.py` calls `run_transform()` and loads both tables. The transform
stage can also be run alone for debugging:

```powershell
python -m scripts.transform
```

`run_pipeline.py` is the planned one-command entry point and is the final
remaining implementation step. Until it is wired, use the stage commands above.

### 5. Run the tests

```powershell
pytest -q
```

The tests import the real ETL modules but mock `requests.get` and the database
write functions. They do not call the live API or modify PostgreSQL.

## Analytics

The five SQL files are implemented. Run each one on its own:

```powershell
psql -U postgres -d radio_pipeline -f sql/stations_by_continent.sql
psql -U postgres -d radio_pipeline -f sql/stations_by_country.sql
psql -U postgres -d radio_pipeline -f sql/codec_distribution.sql
psql -U postgres -d radio_pipeline -f sql/avg_bitrate_by_codec.sql
psql -U postgres -d radio_pipeline -f sql/metadata_completeness.sql
```

The queries use two join patterns:

- `stations_by_continent.sql` starts from `stations` and left joins `country`, so
  stations without a matched country code stay in the `Unknown` bucket.
- `stations_by_country.sql` starts from `stations` and joins `country`, so it
  returns only countries with at least one station.

The generic analytical join is:

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

### Sample results

Current snapshot: 1,000 stations.

| Query | Current result |
| --- | --- |
| Continent | Europe 441, Asia 278, Americas 133, Africa 132, Unknown 14, Oceania 2 |
| Country | 77 countries; DE 105, US 88, TR 62 |
| Codec | MP3 68.6%, AAC 13.7%, AAC+ 11.1% |
| Avg bitrate | OGG 422.25 kbps over 4 stations |
| Metadata | tags 22.9% missing, bitrate 17.1% missing |

## Reruns and raw data

Each run is a full refresh:

- `extract.py` writes one new timestamped JSON file per run.
- `load.py` truncates `country` and `stations` before loading the current
  snapshot.
- `country` is truncated with `CASCADE`, so it also clears `stations`; the
  loader fills `country` first and `stations` second to satisfy the foreign key.
- Reruns do not append duplicate rows.

`data/raw/` is gitignored. Only `extract.py` writes there; the transform and load
stages only read from it.

## Project layout

```text
radio-streaming-pipeline/
|-- data/
|   `-- raw/                      # generated JSON + downloaded country CSV (gitignored)
|-- docs/
|   |-- erd.md                    # normalized ERD and SQL joins
|   `-- project_guide.md          # implementation plan and current status
|-- scripts/
|   |-- extract.py                # API fetch + country CSV download
|   |-- transform.py              # clean stations and validate country codes
|   `-- load.py                   # create tables and load PostgreSQL
|-- sql/
|   |-- stations_by_continent.sql
|   |-- stations_by_country.sql
|   |-- codec_distribution.sql
|   |-- avg_bitrate_by_codec.sql
|   `-- metadata_completeness.sql
|-- tests/
|   `-- test_pipeline.py          # ETL tests (API and DB writes mocked)
|-- .env                          # local values (gitignored)
|-- .env.example
|-- .gitignore
|-- README.md
|-- requirements.txt
`-- run_pipeline.py               # final entry point; to be implemented
```

## Limitations

- The snapshot is a sample ordered by clickcount, not a full census of all
  stations.
- The API is live, so two extract runs can return different rows.
- There is no scheduler or continuous polling loop yet.
- `run_pipeline.py` is not implemented yet; run the stages individually for now.
- The test suite mocks database writes, so it does not verify live PostgreSQL
  connectivity.
- Existing databases created before the schema cleanup may still contain the old
  unused `country_name`, `continent`, and `sub_region` columns on `stations`;
  `CREATE TABLE IF NOT EXISTS` does not alter an existing table.
- Raw data is not committed, so a fresh clone must run extract before transform.

## Implementation plan

See [`docs/project_guide.md`](docs/project_guide.md) for the phase-by-phase plan,
current status, acceptance criteria, and next actions.
