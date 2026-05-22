#!/usr/bin/env python3
"""
redash_migrator.py — Migrates Redash queries/dashboards → Jupyter notebooks (.ipynb).

Usage:
    python migrator.py --host http://localhost:5000 --api-key YOUR_KEY [--query-id 42] [--dashboard-slug my-dash]

Handles:
  - All viz types: line, column/bar, pie, scatter, counter, table, area
  - All param types: date, date-range, number, enum, text
  - QRDS (Query Results Data Source) detection → pandasql stub
  - Pagination over full query list
  - Dashboard → grid-positioned JSON manifest
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import requests

# ── QRDS detection ─────────────────────────────────────────────────────────────
QRDS_RE = re.compile(r"cached_query_(\d+)", re.IGNORECASE)


def is_qrds(data_source_type: str, query_text: str) -> list[int]:
    """Return list of referenced query IDs if this is a QRDS query, else []."""
    if data_source_type == "results":
        return [int(m) for m in QRDS_RE.findall(query_text)]
    return []


# ── Parameter handling ──────────────────────────────────────────────────────────

def params_to_python(parameters: list) -> tuple[str, dict]:
    """
    Convert Redash parameter definitions to:
      - Python variable declarations (for the notebook params cell)
      - A substitution map {placeholder: varname}
    """
    lines = ["# Query parameters — edit these values and re-run"]
    subs = {}  # placeholder_in_sql -> python_varname

    for p in parameters:
        name = p["name"]
        ptype = p.get("type", "text")
        value = p.get("value", "")

        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)

        if ptype == "date":
            default = json.dumps(value or "2024-01-01")
            lines.append(f'{safe_name} = {default}  # date YYYY-MM-DD')
            subs[f"{{{{{name}}}}}"] = safe_name

        elif ptype == "date-range":
            start = value.get("start", "2024-01-01") if isinstance(value, dict) else "2024-01-01"
            end   = value.get("end",   "2024-03-31") if isinstance(value, dict) else "2024-03-31"
            lines.append(f'{safe_name}__start = "{start}"  # date-range start')
            lines.append(f'{safe_name}__end   = "{end}"    # date-range end')
            subs[f"{{{{{name}.start}}}}"] = f"{safe_name}__start"
            subs[f"{{{{{name}.end}}}}"]   = f"{safe_name}__end"

        elif ptype == "number":
            default = value if isinstance(value, (int, float)) else 0
            lines.append(f'{safe_name} = {default}  # number')
            subs[f"{{{{{name}}}}}"] = safe_name

        elif ptype == "enum":
            opts = p.get("enumOptions", "").split("\n")
            default = json.dumps(value or (opts[0] if opts else ""))
            opts_repr = json.dumps(opts)
            lines.append(f'{safe_name} = {default}  # enum — options: {opts_repr}')
            subs[f"{{{{{name}}}}}"] = safe_name

        else:  # text / query
            default = json.dumps(str(value or ""))
            lines.append(f'{safe_name} = {default}  # text param')
            subs[f"{{{{{name}}}}}"] = safe_name

    return "\n".join(lines), subs


def build_parameterized_query(sql: str, subs: dict) -> str:
    """Replace {{param}} placeholders with Python f-string variables."""
    result = sql
    for placeholder, varname in subs.items():
        result = result.replace(placeholder, f"{{{varname}}}")
    # Wrap in f-string if there are substitutions
    if subs:
        # Escape existing braces that aren't substitutions by doubling them
        # (We've already replaced our subs so remaining { } need escaping)
        result = result.replace("{", "{{").replace("}", "}}")
        # Now un-escape our substituted vars
        for varname in subs.values():
            result = result.replace(f"{{{{{varname}}}}}", f"{{{varname}}}")
        return f'query = f"""\n{result}\n"""'
    return f'query = """\n{result}\n"""'


# ── Visualization code generation ───────────────────────────────────────────────

def viz_to_code(viz: dict, df_var: str = "df") -> str:
    """Convert a Redash visualization definition to Plotly Express Python code."""
    vtype = viz.get("type", "TABLE")
    opts  = viz.get("options", {})
    name  = viz.get("name", "Chart")

    if vtype == "TABLE":
        return f"# Table visualization\n{df_var}"

    if vtype == "COUNTER":
        col = opts.get("counterColName") or (f"{df_var}.columns[0]")
        return (
            f"# Counter\n"
            f"from IPython.display import HTML\n"
            f"_val = {df_var}['{col}'].iloc[0] if '{col}' in {df_var}.columns else {df_var}.iloc[0, 0]\n"
            f"HTML(f'<div style=\"font-family:sans-serif;padding:16px\">"
            f"<p style=\"font-size:14px;color:#888;margin:0\">{name}</p>"
            f"<p style=\"font-size:48px;font-weight:bold;color:#333;margin:4px 0\">{{_val:,}}</p></div>')"
        )

    if vtype == "CHART":
        series_type = opts.get("globalSeriesType", "line")
        col_map     = opts.get("columnMapping", {})

        # Resolve x, y, series from columnMapping
        x_col      = next((c for c, r in col_map.items() if r == "x"), None)
        y_cols     = [c for c, r in col_map.items() if r == "y"]
        series_col = next((c for c, r in col_map.items() if r == "series"), None)

        y_col = y_cols[0] if y_cols else None

        imports = "import plotly.express as px\n"

        if series_type == "pie":
            if not x_col or not y_col:
                return f"{imports}# pie — no column mapping found\npx.pie({df_var})"
            return (
                f"{imports}"
                f"fig = px.pie({df_var}, names='{x_col}', values='{y_col}', title='{name}')\n"
                f"fig"
            )

        if series_type in ("line", "area"):
            px_type = "line" if series_type == "line" else "area"
            color   = f", color='{series_col}'" if series_col else ""
            if not x_col or not y_col:
                return f"{imports}# {px_type} — no column mapping\npx.{px_type}({df_var})"
            return (
                f"{imports}"
                f"fig = px.{px_type}({df_var}, x='{x_col}', y='{y_col}'{color}, title='{name}')\n"
                f"fig"
            )

        if series_type in ("column", "bar"):
            # BUG FIX: groupBy comes from columnMapping 'series', NOT from seriesOptions
            color = f", color='{series_col}'" if series_col else ""
            orientation = "h" if series_type == "bar" else ""
            orient_arg  = ", orientation='h'" if orientation else ""
            if not x_col or not y_col:
                return f"{imports}# bar — no column mapping\npx.bar({df_var})"
            if orientation:
                return (
                    f"{imports}"
                    f"fig = px.bar({df_var}, x='{y_col}', y='{x_col}'{color}{orient_arg}, title='{name}')\n"
                    f"fig"
                )
            return (
                f"{imports}"
                f"fig = px.bar({df_var}, x='{x_col}', y='{y_col}'{color}, title='{name}')\n"
                f"fig"
            )

        if series_type == "scatter":
            x_s = x_col or (y_cols[0] if len(y_cols) > 0 else None)
            y_s = y_cols[1] if len(y_cols) > 1 else (y_cols[0] if y_cols else None)
            color = f", color='{series_col}'" if series_col else ""
            if not x_s or not y_s:
                return f"{imports}# scatter — need at least 2 y columns\npx.scatter({df_var})"
            return (
                f"{imports}"
                f"fig = px.scatter({df_var}, x='{x_s}', y='{y_s}'{color}, title='{name}')\n"
                f"fig"
            )

        # fallback
        return f"{imports}fig = px.line({df_var}, title='{name}')  # unknown series type: {series_type}\nfig"

    return f"# Unsupported viz type: {vtype}\n{df_var}"


# ── Notebook builder ────────────────────────────────────────────────────────────

def make_cell(source: str, cell_type: str = "code") -> dict:
    lines = [l + "\n" for l in source.splitlines()]
    if lines:
        lines[-1] = lines[-1].rstrip("\n")
    if cell_type == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": lines}
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines,
    }


def query_to_notebook(query: dict, ds_type: str) -> dict:
    """Convert a single Redash query (with visualizations) to a .ipynb dict."""
    cells = []

    title    = query.get("name", "Untitled")
    sql      = query.get("query", "")
    params   = query.get("options", {}).get("parameters", [])
    vizs     = query.get("visualizations", [])
    qrds_ids = is_qrds(ds_type, sql)

    # ── Header
    cells.append(make_cell(f"# {title}", "markdown"))

    # ── Install deps
    cells.append(make_cell(
        "# Install dependencies (run once)\n"
        "# !pip install pandas plotly psycopg2-binary pandasql sqlalchemy"
    ))

    # ── DB connection (skip for QRDS and CSV)
    if ds_type not in ("results", "csv"):
        cells.append(make_cell(
            "import pandas as pd\nfrom sqlalchemy import create_engine, text\n\n"
            "# ← Update connection string\n"
            'engine = create_engine("postgresql://user:pass@host:5432/dbname")\n'
        ))

    # ── Parameters
    if params:
        param_code, subs = params_to_python(params)
        cells.append(make_cell(param_code))
        query_cell = build_parameterized_query(sql, subs)
    else:
        subs = {}
        query_cell = f'query = """\n{sql}\n"""'

    # ── QRDS stub
    if qrds_ids:
        qrds_comment = ", ".join(f"query_{i}" for i in qrds_ids)
        cells.append(make_cell(
            f"# ⚠️  QRDS query — references: {qrds_comment}\n"
            f"# Replace the DataFrames below with the actual outputs from those notebooks.\n"
            f"import pandasql as ps\n\n"
            + "\n".join(f"# cached_query_{i} = run_notebook_and_get_df('query_{i}.ipynb')" for i in qrds_ids)
            + "\n\n"
            + "\n".join(f"cached_query_{i} = pd.DataFrame()  # TODO: load from notebook {i}" for i in qrds_ids)
        ))
        cells.append(make_cell(
            f'# QRDS SQL (uses pandasql)\n'
            f'qrds_sql = """\n{sql}\n"""\n'
            f"df = ps.sqldf(qrds_sql, locals())"
        ))
    elif ds_type == "csv":
        cells.append(make_cell(
            "import pandas as pd, io, requests\n\n"
            f'csv_url = "{sql.strip()}"\n'
            "# If url: YAML, extract the URL\n"
            "import yaml as _yaml\n"
            "_cfg = _yaml.safe_load(csv_url) if csv_url.strip().startswith('url') else {'url': csv_url}\n"
            "df = pd.read_csv(_cfg['url'])\n"
            "df.head()"
        ))
    else:
        cells.append(make_cell(query_cell))
        cells.append(make_cell(
            "with engine.connect() as conn:\n"
            "    df = pd.read_sql(text(query), conn)\n"
            "print(f'{len(df)} rows')\n"
            "df.head()"
        ))

    # ── One cell per visualization
    non_table_vizs = [v for v in vizs if v.get("type") != "TABLE"]
    if non_table_vizs:
        for viz in non_table_vizs:
            cells.append(make_cell(f"## Visualization: {viz.get('name', '')}", "markdown"))
            cells.append(make_cell(viz_to_code(viz)))
    else:
        # Just show the table
        cells.append(make_cell("df"))

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
            "redash_query_id": query.get("id"),
            "redash_query_name": title,
        },
        "cells": cells,
    }


# ── Dashboard migrator ──────────────────────────────────────────────────────────

def migrate_dashboard(dashboard: dict, query_notebook_map: dict) -> dict:
    """
    Convert a Redash dashboard to a Deepnote dashboard JSON.
    query_notebook_map: {visualization_id: notebook_filename}
    """
    widgets = dashboard.get("widgets", [])
    cells = []

    for w in widgets:
        viz  = w.get("visualization")
        text = w.get("text", "")
        pos  = w.get("options", {}).get("position", {})

        cell = {
            "id": f"widget_{w.get('id', 0)}",
            "col": pos.get("col", 0),
            "row": pos.get("row", 0),
            "sizeX": pos.get("sizeX", 3),
            "sizeY": pos.get("sizeY", 8),
        }

        if viz:
            vid = viz.get("id")
            cell["type"] = "notebook"
            cell["notebook"] = query_notebook_map.get(vid, f"unknown_viz_{vid}.ipynb")
            cell["viz_type"] = viz.get("type")
            cell["viz_name"] = viz.get("name")
        else:
            cell["type"] = "text"
            cell["content"] = text

        cells.append(cell)

    # Sort by row then col for readability
    cells.sort(key=lambda c: (c["row"], c["col"]))

    return {
        "dashboard_name": dashboard.get("name"),
        "slug": dashboard.get("slug"),
        "cells": cells,
    }


# ── API client ──────────────────────────────────────────────────────────────────

class RedashClient:
    def __init__(self, host: str, api_key: str):
        self.host    = host.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Key {api_key}"

    def get(self, path: str, **params):
        r = self.session.get(f"{self.host}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def get_query(self, query_id: int) -> dict:
        """Fetch a single query WITH visualizations."""
        return self.get(f"/api/queries/{query_id}")

    def get_all_queries(self) -> list:
        """Paginate through all queries. Each query fetched individually to get visualizations."""
        page, page_size = 1, 25
        all_queries = []
        print("Fetching query list...", flush=True)
        while True:
            data = self.get("/api/queries", page=page, page_size=page_size)
            results = data.get("results", [])
            total   = data.get("count", 0)
            print(f"  page {page}: {len(results)} queries (total={total})", flush=True)
            # Fetch each query individually to get visualizations (not included in list endpoint)
            for q in results:
                full = self.get_query(q["id"])
                all_queries.append(full)
            if page * page_size >= total:
                break
            page += 1
        return all_queries

    def get_data_source(self, ds_id: int) -> dict:
        return self.get(f"/api/data_sources/{ds_id}")

    def get_dashboard(self, id_or_slug) -> dict:
        """Fetch a dashboard by numeric ID (preferred) or slug.
        The list endpoint returns widgets=null; fetch by ID to get full widget data."""
        return self.get(f"/api/dashboards/{id_or_slug}")

    def get_all_dashboards(self) -> list:
        data = self.get("/api/dashboards")
        results = data.get("results", [])
        # Use numeric ID — slug lookup broken in Redash 10 (casts slug to int)
        full = []
        for d in results:
            try:
                full.append(self.get_dashboard(d["id"]))
            except Exception as e:
                print(f"  [WARN] Could not fetch dashboard {d['id']} ({d['name']}): {e}", flush=True)
        return full


# ── Migration runner ────────────────────────────────────────────────────────────

def run_migration(host: str, api_key: str, output_dir: Path,
                  query_id: int = None, dashboard_slug: str = None):
    client = RedashClient(host, api_key)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Cache data source types
    ds_cache: dict[int, str] = {}
    def get_ds_type(ds_id):
        if ds_id not in ds_cache:
            try:
                ds = client.get_data_source(ds_id)
                ds_cache[ds_id] = ds.get("type", "unknown")
            except Exception:
                ds_cache[ds_id] = "unknown"
        return ds_cache[ds_id]

    # Collect queries to migrate
    if query_id:
        queries = [client.get_query(query_id)]
    else:
        queries = client.get_all_queries()

    print(f"\nMigrating {len(queries)} queries...", flush=True)
    viz_to_notebook: dict[int, str] = {}  # visualization_id → notebook filename
    results_summary = []

    for q in queries:
        qid      = q["id"]
        ds_id    = q.get("data_source_id")
        ds_type  = get_ds_type(ds_id) if ds_id else "unknown"
        vizs     = q.get("visualizations", [])
        qrds_ids = is_qrds(ds_type, q.get("query", ""))
        safe_name = re.sub(r"[^\w]", "_", q.get("name", f"query_{qid}"))
        nb_filename = f"query_{qid}_{safe_name}.ipynb"

        qrds_note = f"  QRDS->{qrds_ids}" if qrds_ids else ""
        print(f"  [{qid}] {q['name'][:50]:<50} ds={ds_type:<10} "
              f"vizs={len(vizs)} params={len(q.get('options',{}).get('parameters',[]))}"
              f"{qrds_note}", flush=True)

        try:
            nb = query_to_notebook(q, ds_type)
            nb_path = output_dir / nb_filename
            nb_path.write_text(json.dumps(nb, indent=2))

            for v in vizs:
                viz_to_notebook[v["id"]] = nb_filename

            results_summary.append({
                "query_id": qid, "name": q["name"], "notebook": nb_filename,
                "ds_type": ds_type, "is_qrds": bool(qrds_ids),
                "viz_count": len(vizs), "param_count": len(q.get("options", {}).get("parameters", [])),
                "status": "ok",
            })
        except Exception as e:
            print(f"    ✗ ERROR: {e}", flush=True)
            results_summary.append({"query_id": qid, "name": q["name"], "status": f"error: {e}"})

    # Migrate dashboards
    if dashboard_slug:
        dashboards = [client.get_dashboard(dashboard_slug)]
    elif not query_id:
        dashboards = client.get_all_dashboards()
    else:
        dashboards = []

    print(f"\nMigrating {len(dashboards)} dashboards...", flush=True)
    for dash in dashboards:
        safe_slug = re.sub(r"[^\w]", "_", dash.get("slug", "dashboard"))
        dash_json  = migrate_dashboard(dash, viz_to_notebook)
        dash_path  = output_dir / f"dashboard_{safe_slug}.json"
        dash_path.write_text(json.dumps(dash_json, indent=2))
        print(f"  Dashboard: {dash['name']} -> {dash_path.name} ({len(dash_json['cells'])} widgets)", flush=True)

    # Write summary
    summary_path = output_dir / "migration_summary.json"
    summary_path.write_text(json.dumps(results_summary, indent=2))

    # Print stats
    ok  = sum(1 for r in results_summary if r.get("status") == "ok")
    err = len(results_summary) - ok
    qrds_count = sum(1 for r in results_summary if r.get("is_qrds"))
    print(f"\n{'='*60}")
    print(f"[OK]   Migrated : {ok} queries")
    print(f"[ERR]  Errors   : {err} queries")
    print(f"[QRDS] Stubs    : {qrds_count} queries need pandasql stubs")
    print(f"[OUT]  Output   : {output_dir.resolve()}")
    print(f"{'='*60}")


# ── CLI ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Redash → Jupyter notebooks")
    parser.add_argument("--host",           default="http://localhost:5000")
    parser.add_argument("--api-key",        required=True)
    parser.add_argument("--output-dir",     default="migrated")
    parser.add_argument("--query-id",       type=int, default=None)
    parser.add_argument("--dashboard-slug", default=None,
                        help="Dashboard slug or numeric ID")
    args = parser.parse_args()

    run_migration(
        host           = args.host,
        api_key        = args.api_key,
        output_dir     = Path(args.output_dir),
        query_id       = args.query_id,
        dashboard_slug = args.dashboard_slug,
    )
