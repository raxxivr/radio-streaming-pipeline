# Reproducible sample snapshot

These files are a small, synthetic snapshot committed for reproducible tests and
inspection. They are not live API data and do not contain real station records.

- `stations_sample.json` contains 10 raw station rows. It includes a duplicate
  UUID, a missing name, whitespace, blank and invalid country codes, and invalid
  or zero bitrates so the cleaning rules can be inspected.
- `country_lookup_sample.csv` contains a small subset of the ISO-3166 lookup.

Run the transformation without the live API or PostgreSQL:

```powershell
python -m scripts.run_sample_transform
```

The sample is also exercised by `pytest -q`.
