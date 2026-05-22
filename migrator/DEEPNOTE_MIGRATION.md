# Redash → Deepnote Migration: What Needs to Be Built

## What This Is

A working proof-of-concept migration from a real Redash instance to Deepnote.
Source: Wikipedia Analytics dashboard built on live Wikimedia REST API data.

The migrator script (`migrator.py`) already handles the mechanical extraction.
This document captures what the *output* needs to look like in Deepnote, and
every gap between what we generate today vs. what Deepnote actually needs.

---

## Source: What We Have in Redash

### Data
Real data from the public Wikimedia REST API — no auth required:
- `wiki_pageviews` — daily pageviews for en/de/fr/es/ja Wikipedia, Jan 2024
- `wiki_edits` — daily edit counts per project
- `wiki_devices` — daily unique device counts per project
- `wiki_top_articles` — top 20 articles on en.wikipedia, 3 date snapshots

### Queries (7 total)
| ID | Name | Viz Type | SQL Pattern |
|----|------|----------|-------------|
| 15 | Daily Pageviews by Project | Line (multi-series) | `SELECT date, project, views … ORDER BY date` |
| 16 | Total Pageviews by Project | Column bar | `SELECT project, SUM(views) … GROUP BY project` |
| 17 | Total en.wikipedia Pageviews | Counter | `SELECT SUM(views) AS total_views …` |
| 18 | Daily Edits by Project | Line (multi-series) | `SELECT date, project, edits … ORDER BY date` |
| 19 | Top Articles (table) | Table | `SELECT date, rank, article, views …` |
| 20 | Top 10 Articles Jan 1 | Horizontal bar | `SELECT article, views … LIMIT 10` |
| 21 | Unique Devices by Project | Pie | `SELECT project, SUM(devices) … GROUP BY project` |

### Dashboard: "Wikipedia Analytics — January 2024"
7 widgets in a 6-column grid:
```
[ Text header (3×4)    ][ Counter: 11.8B views (3×4) ]
[ Line: daily pageviews by project        (6×8)       ]
[ Line: daily edits (3×8) ][ Pie: devices (3×8)       ]
[ Bar: total views (3×8)  ][ Bar: top articles (3×8)  ]
```

---

## What the Migrator Generates Today

For each query, `migrator.py` produces a `.ipynb` with:
1. A markdown header cell
2. A SQLAlchemy connection cell (needs credentials filled in)
3. A `query = """..."""` cell with the SQL
4. A `pd.read_sql(text(query), conn)` cell
5. One cell per visualization with Plotly Express code

For the dashboard, it produces a `dashboard_*.json` with widget positions
and notebook filenames.

### Example — generated Plotly for the line chart (Q15):
```python
import plotly.express as px
fig = px.line(df, x='date', y='views', color='project',
              title='Daily Pageviews by Project')
fig.show()
```

### Example — generated counter cell (Q17):
```python
_val = df['total_views'].iloc[0]
print(f'Total Views: {_val:,}')
```

---

## Gaps: What Deepnote Needs That We Don't Generate Yet

### 1. Data Connection
**Current:** Generic SQLAlchemy string that the user has to fill in manually.
```python
engine = create_engine("postgresql://user:pass@host:5432/dbname")
```
**Deepnote needs:** An integration block using Deepnote's built-in database
integrations. The notebook should reference a named integration, not hardcoded creds.
```python
# Deepnote: use the "PostgreSQL" integration configured in workspace settings
import deepnote  # or however Deepnote exposes its integration context
```
**Fix needed:** Detect the data source type from Redash, emit a comment block
explaining which Deepnote integration to set up, and reference it by name.

---

### 2. Plotly in Deepnote
**Current:** `fig.show()` — works in Jupyter but Deepnote renders it differently.
**Deepnote needs:** `fig` as the last line of the cell (no `.show()`) — Deepnote
auto-renders the last expression.
```python
# Current (generic Jupyter):
fig.show()

# Should be (Deepnote):
fig   # Deepnote renders last expression automatically
```
**Fix needed:** One-line change in `viz_to_code()` — swap `fig.show()` for `fig`.

---

### 3. Dashboard Layout
**Current:** We output a JSON file like:
```json
{
  "dashboard_name": "Wikipedia Analytics — January 2024",
  "cells": [
    { "type": "notebook", "notebook": "query_15_Daily_Pageviews.ipynb",
      "col": 0, "row": 4, "sizeX": 6, "sizeY": 8 }
  ]
}
```
**Deepnote needs:** Deepnote dashboards are configured inside the Deepnote UI —
there's no import-from-JSON API yet. The JSON is useful as a *spec* for manually
recreating the layout, but can't be auto-applied.
**Fix needed:** Either (a) wait for Deepnote dashboard import API, or (b) generate
step-by-step instructions from the JSON: "Create a dashboard, add notebook X at
position col=0 row=4".

---

### 4. Multi-Series Charts
**Current:** Works correctly for line and bar. Example for daily pageviews:
```python
fig = px.line(df, x='date', y='views', color='project')
```
The `color='project'` correctly groups by project — this is the bug we fixed
by reading `columnMapping.series` instead of `seriesOptions`.
**Status: Works ✅**

---

### 5. Counter Visualization
**Current:** Prints to stdout with `print(f'...')`.
**Deepnote needs:** A rendered number block. Deepnote doesn't have a native
counter widget — best option is a styled HTML output:
```python
from IPython.display import HTML
HTML(f'<h1 style="font-size:48px; color:#333">{_val:,}</h1><p>Total Views</p>')
```
**Fix needed:** Update `viz_to_code()` for COUNTER type to emit HTML display
instead of print.

---

### 6. Parameters
**Current:** Python variables at the top of the notebook:
```python
date_range__start = "2024-01-01"
date_range__end   = "2024-03-31"
channel = "release"
```
**Deepnote needs:** Deepnote has native "Input" blocks that render as interactive
form fields. These should be connected to the variables.
**Fix needed:** Detect Deepnote environment and emit variable declarations that
work with Deepnote's input block system (if/when Deepnote exposes this in notebooks).
For now, plain variables work — user just edits them manually.

---

### 7. QRDS (Query Results Data Source)
**Current:** Generates a `pandasql` stub:
```python
import pandasql as ps
cached_query_8 = pd.DataFrame()  # TODO: load from notebook 8
df = ps.sqldf(qrds_sql, locals())
```
**Deepnote needs:** Cross-notebook data sharing isn't a native feature.
Real options:
- Export the upstream query result to a CSV, load it in the downstream notebook
- Use a shared database table instead of QRDS
**Fix needed:** Add a note in the generated cell explaining the two options,
and optionally generate the CSV export code for the upstream notebook.

---

## Migration Effort Estimate

| Query type | Auto-migrated? | Manual work needed |
|---|---|---|
| Simple SELECT → line/bar/pie | ✅ Yes | Change `fig.show()` → `fig` |
| Counter | Partial | Replace `print` with `HTML()` |
| Parameterized query | ✅ Yes | None — variables work as-is |
| QRDS | Stub only | Wire up upstream DataFrame manually |
| Dashboard layout | JSON spec only | Recreate in Deepnote UI manually |
| DB connection | Generic SQLAlchemy | Set up Deepnote integration, update string |

**Rough estimate for a 50-query Redash instance:**
- Automated migration: ~2 minutes (run the script)
- Manual fixes per notebook: ~5 min average
- Dashboard recreation: ~15 min per dashboard
- DB integration setup: one-time, ~10 min

---

## Recommended Next Steps

1. **Fix `fig.show()` → `fig`** in `migrator.py` — one line, unblocks all charts
2. **Fix Counter** to emit `HTML()` — makes KPI widgets actually look right
3. **Test in real Deepnote** — import one generated notebook, verify it runs end-to-end
4. **Talk to Mozilla** — request a read-only STMO API key to run against a real 500-query instance
5. **Build the Deepnote dashboard import** — this is the biggest missing piece for
   a polished migration experience

---

## How to Reproduce This Demo

```bash
git clone https://github.com/sLightlyDev/redash-demo
cd redash-demo
docker compose -f docker-compose.demo.yml up
# → http://localhost:5000  |  admin@demo.com / demo1234
```

Data sources are seeded automatically. The Wikipedia dashboard is pre-built.
To re-run the migrator:
```bash
cd migrator
pip install -r requirements.txt
python migrator.py \
  --host http://localhost:5000 \
  --api-key etU4dy90YxbNaEJsgnCoD99bOJyLQ9BencVphkgh \
  --output-dir migrated
```
