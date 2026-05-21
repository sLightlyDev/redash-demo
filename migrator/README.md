# Redash → Notebook Migrator

Migrates Redash queries and dashboards to standard Jupyter notebooks (`.ipynb`) that run anywhere — Jupyter, JupyterLab, Deepnote, Databricks, VS Code, Google Colab, etc.

## What it does

- Fetches all queries from a Redash instance via the REST API (paginated)
- Generates one `.ipynb` notebook per query with:
  - SQL wired up to SQLAlchemy
  - Plotly Express visualization code for every chart
  - Python variables for every parameter (date, date-range, number, enum)
  - `pandasql` stubs for Query Results (QRDS) queries
- Generates a dashboard layout JSON for each Redash dashboard

## Usage

```bash
pip install -r requirements.txt

python migrator.py \
  --host    http://your-redash-instance.com \
  --api-key YOUR_API_KEY \
  --output-dir migrated
```

Optional: migrate a single query or dashboard:
```bash
python migrator.py --host ... --api-key ... --query-id 42
python migrator.py --host ... --api-key ... --dashboard-slug my-dashboard
```

## Output

```
migrated/
  query_8_DAU_Over_Time_by_Channel.ipynb
  query_9_Crash_Rate_by_Channel_and_OS.ipynb
  ...
  dashboard_firefox_telemetry_overview.json
  migration_summary.json
```

## Notes

- **QRDS queries** generate a `pandasql` stub — you need to manually wire in the DataFrame from the referenced notebook
- **API key**: found in Redash under your profile → API Key
- Dashboard JSON preserves grid layout (row/col/sizeX/sizeY) — adaptable to any notebook platform's dashboard format
