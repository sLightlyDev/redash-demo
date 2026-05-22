#!/usr/bin/env python3
"""
make_demo_notebooks.py
Generates self-contained Deepnote-ready .ipynb notebooks for the Wikipedia
Analytics demo. No database required — data is fetched live from the
Wikimedia REST API (free, no auth).

Run:
    python make_demo_notebooks.py --output-dir deepnote_demo
"""

import json
import argparse
from pathlib import Path

# ── helpers ────────────────────────────────────────────────────────────────────

def cell(source: str, kind: str = "code") -> dict:
    lines = [l + "\n" for l in source.splitlines()]
    if lines:
        lines[-1] = lines[-1].rstrip("\n")
    if kind == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": lines}
    return {
        "cell_type": "code", "execution_count": None,
        "metadata": {}, "outputs": [], "source": lines,
    }

def notebook(cells: list, title: str) -> dict:
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
            "deepnote_demo": True, "title": title,
        },
        "cells": cells,
    }

def save(nb: dict, path: Path):
    path.write_text(json.dumps(nb, indent=2))
    print(f"  wrote {path.name}")

# ── shared fetch code (injected into every notebook) ─────────────────────────

FETCH_IMPORTS = """\
import requests, time
import pandas as pd
import plotly.express as px
from IPython.display import HTML

PROJECTS = ["en.wikipedia", "de.wikipedia", "fr.wikipedia", "es.wikipedia", "ja.wikipedia"]
START, END = "20240101", "20240131"

def wiki_get(url, retries=3):
    headers = {"User-Agent": "deepnote-redash-demo/1.0 (demo notebook)"}
    for i in range(retries):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        time.sleep(2)
    return None
"""

# ── Q15: Daily Pageviews by Project (line chart) ─────────────────────────────

def q15_daily_pageviews(out: Path):
    fetch = FETCH_IMPORTS + """
rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/{proj}/all-access/user/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        for item in data.get("items", []):
            rows.append({"date": item["timestamp"][:8], "project": proj, "views": item["views"]})
    time.sleep(0.5)

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
print(f"{len(df)} rows")
df.head()
"""

    chart = """\
fig = px.line(df, x="date", y="views", color="project",
              title="Wikipedia Daily Pageviews by Project — January 2024",
              labels={"views": "Daily Pageviews", "date": "Date", "project": "Project"})
fig.update_layout(height=450)
fig
"""
    cells = [
        cell("# Wikipedia Daily Pageviews by Project", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(chart),
    ]
    save(notebook(cells, "Daily Pageviews by Project"), out / "q15_daily_pageviews.ipynb")


# ── Q16: Total Pageviews by Project (bar chart) ───────────────────────────────

def q16_total_pageviews(out: Path):
    fetch = FETCH_IMPORTS + """
rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/{proj}/all-access/user/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        total = sum(item["views"] for item in data.get("items", []))
        rows.append({"project": proj, "total_views": total})
    time.sleep(0.5)

df = pd.DataFrame(rows).sort_values("total_views", ascending=False)
print(df.to_string(index=False))
"""

    chart = """\
fig = px.bar(df, x="project", y="total_views",
             title="Total Wikipedia Pageviews by Project — January 2024",
             labels={"total_views": "Total Pageviews", "project": "Project"},
             color="project")
fig.update_layout(height=400, showlegend=False)
fig
"""
    cells = [
        cell("# Total Pageviews by Project", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(chart),
    ]
    save(notebook(cells, "Total Pageviews by Project"), out / "q16_total_pageviews.ipynb")


# ── Q17: Total en.wikipedia Pageviews (counter / KPI) ────────────────────────

def q17_counter(out: Path):
    fetch = FETCH_IMPORTS + """
url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/en.wikipedia/all-access/user/daily/{START}/{END}"
data = wiki_get(url)
total = sum(item["views"] for item in data.get("items", [])) if data else 0
print(f"Total: {total:,}")
"""

    kpi = """\
HTML(f'''
<div style="font-family:sans-serif; padding:24px; background:#f9f9f9;
            border-radius:8px; display:inline-block; min-width:280px">
  <p style="font-size:13px; color:#888; margin:0; text-transform:uppercase;
            letter-spacing:.05em">en.wikipedia — January 2024</p>
  <p style="font-size:52px; font-weight:700; color:#1a1a2e; margin:8px 0 4px">
    {total:,}
  </p>
  <p style="font-size:14px; color:#555; margin:0">Total Pageviews</p>
</div>
''')
"""
    cells = [
        cell("# Total en.wikipedia Pageviews — January 2024", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(kpi),
    ]
    save(notebook(cells, "Total en.wikipedia Pageviews"), out / "q17_counter.ipynb")


# ── Q18: Daily Edits by Project (line chart) ─────────────────────────────────

def q18_daily_edits(out: Path):
    fetch = FETCH_IMPORTS + """
rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/edits/aggregate/{proj}/all-editor-types/all-page-types/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        for item in data.get("items", [{}]).pop().get("results", []):
            rows.append({"date": item["timestamp"][:10], "project": proj, "edits": item["edits"]})
    time.sleep(0.5)

df = pd.DataFrame(rows)
if not df.empty:
    df["date"] = pd.to_datetime(df["date"])
print(f"{len(df)} rows")
df.head()
"""

    chart = """\
if df.empty:
    print("No edit data returned — the edits API may require different parameters.")
else:
    fig = px.line(df, x="date", y="edits", color="project",
                  title="Wikipedia Daily Edits by Project — January 2024",
                  labels={"edits": "Daily Edits", "date": "Date", "project": "Project"})
    fig.update_layout(height=450)
    fig
"""
    cells = [
        cell("# Wikipedia Daily Edits by Project", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(chart),
    ]
    save(notebook(cells, "Daily Edits by Project"), out / "q18_daily_edits.ipynb")


# ── Q19: Top Articles — table ─────────────────────────────────────────────────

def q19_top_articles(out: Path):
    fetch = FETCH_IMPORTS + """
rows = []
for date_str, label in [("2024/01/01", "Jan 1"), ("2024/01/15", "Jan 15"), ("2024/01/31", "Jan 31")]:
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{date_str}"
    data = wiki_get(url)
    if data:
        articles = data.get("items", [{}])[0].get("articles", [])[:20]
        for a in articles:
            rows.append({"date": label, "rank": a["rank"], "article": a["article"], "views": a["views"]})
    time.sleep(0.5)

df = pd.DataFrame(rows)
print(f"{len(df)} rows")
df.head(10)
"""
    cells = [
        cell("# Top Articles on en.wikipedia (3 Date Snapshots)", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
    ]
    save(notebook(cells, "Top Articles — Table"), out / "q19_top_articles_table.ipynb")


# ── Q20: Top 10 Articles Jan 1 (horizontal bar) ───────────────────────────────

def q20_top_articles_bar(out: Path):
    fetch = FETCH_IMPORTS + """
url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/2024/01/01"
data = wiki_get(url)
articles = data.get("items", [{}])[0].get("articles", [])[:10] if data else []
df = pd.DataFrame([{"article": a["article"].replace("_", " "), "views": a["views"]} for a in articles])
df = df.sort_values("views")
print(df.to_string(index=False))
"""

    chart = """\
fig = px.bar(df, x="views", y="article", orientation="h",
             title="Top 10 en.wikipedia Articles — January 1 2024",
             labels={"views": "Pageviews", "article": "Article"})
fig.update_layout(height=420, yaxis_title="")
fig
"""
    cells = [
        cell("# Top 10 en.wikipedia Articles — January 1 2024", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(chart),
    ]
    save(notebook(cells, "Top 10 Articles — Jan 1"), out / "q20_top_articles_bar.ipynb")


# ── Q21: Unique Devices by Project (pie chart) ────────────────────────────────

def q21_unique_devices(out: Path):
    fetch = FETCH_IMPORTS + """
rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/unique-devices/{proj}/all-sites/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        total = sum(item["devices"] for item in data.get("items", []))
        rows.append({"project": proj, "devices": total})
    time.sleep(0.5)

df = pd.DataFrame(rows)
print(df.to_string(index=False))
"""

    chart = """\
fig = px.pie(df, names="project", values="devices",
             title="Unique Devices by Wikipedia Project — January 2024",
             hole=0.35)
fig.update_layout(height=420)
fig
"""
    cells = [
        cell("# Unique Devices by Wikipedia Project", "markdown"),
        cell("_Fetches live data from the Wikimedia REST API — no database needed._", "markdown"),
        cell(fetch),
        cell(chart),
    ]
    save(notebook(cells, "Unique Devices by Project"), out / "q21_unique_devices.ipynb")


# ── Dashboard overview notebook ───────────────────────────────────────────────

def dashboard_overview(out: Path):
    """Single notebook that reproduces the full Wikipedia Analytics dashboard."""
    intro = """\
# Wikipedia Analytics — January 2024
> **Migrated from Redash → Deepnote**
> Data fetched live from the [Wikimedia REST API](https://wikimedia.org/api/rest_v1/) — no database required.

This notebook reproduces the full **Wikipedia Analytics** dashboard:
- KPI counter: total en.wikipedia pageviews
- Daily pageviews by project (line)
- Daily edits by project (line)
- Unique devices by project (pie)
- Total pageviews by project (bar)
- Top 10 articles on Jan 1 (horizontal bar)
"""

    fetch_all = FETCH_IMPORTS + """
# ── Fetch all data ─────────────────────────────────────────────────────────────
print("Fetching pageviews...")
pv_rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/{proj}/all-access/user/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        for item in data.get("items", []):
            pv_rows.append({"date": item["timestamp"][:8], "project": proj, "views": item["views"]})
    time.sleep(0.4)
df_pv = pd.DataFrame(pv_rows)
df_pv["date"] = pd.to_datetime(df_pv["date"], format="%Y%m%d")

print("Fetching unique devices...")
dev_rows = []
for proj in PROJECTS:
    url = f"https://wikimedia.org/api/rest_v1/metrics/unique-devices/{proj}/all-sites/daily/{START}/{END}"
    data = wiki_get(url)
    if data:
        total = sum(item["devices"] for item in data.get("items", []))
        dev_rows.append({"project": proj, "devices": total})
    time.sleep(0.4)
df_dev = pd.DataFrame(dev_rows)

print("Fetching top articles...")
url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/2024/01/01"
data = wiki_get(url)
articles = data.get("items", [{}])[0].get("articles", [])[:10] if data else []
df_top = pd.DataFrame([{"article": a["article"].replace("_", " "), "views": a["views"]} for a in articles])

print(f"Done. Pageviews: {len(df_pv)} rows | Devices: {len(df_dev)} rows | Top articles: {len(df_top)} rows")
"""

    kpi = """\
# ── KPI: Total en.wikipedia pageviews ─────────────────────────────────────────
total_en = int(df_pv[df_pv.project == "en.wikipedia"]["views"].sum())
HTML(f'''
<div style="font-family:sans-serif; padding:20px; background:#f0f4ff;
            border-radius:10px; display:inline-block; min-width:260px;
            border-left:4px solid #4361ee">
  <p style="font-size:12px; color:#666; margin:0; text-transform:uppercase; letter-spacing:.06em">
    en.wikipedia · January 2024
  </p>
  <p style="font-size:48px; font-weight:800; color:#1a1a2e; margin:6px 0 2px; line-height:1">
    {total_en/1e9:.2f}B
  </p>
  <p style="font-size:13px; color:#555; margin:0">Total Pageviews</p>
</div>
''')
"""

    line_pv = """\
# ── Daily Pageviews by Project (line) ─────────────────────────────────────────
fig = px.line(df_pv, x="date", y="views", color="project",
              title="Daily Pageviews by Project — January 2024",
              labels={"views": "Daily Pageviews", "date": "Date"})
fig.update_layout(height=400)
fig
"""

    bar_total = """\
# ── Total Pageviews by Project (bar) ──────────────────────────────────────────
df_total = df_pv.groupby("project", as_index=False)["views"].sum().sort_values("views", ascending=False)
fig = px.bar(df_total, x="project", y="views", color="project",
             title="Total Pageviews by Project — January 2024",
             labels={"views": "Total Pageviews"})
fig.update_layout(height=380, showlegend=False)
fig
"""

    pie_dev = """\
# ── Unique Devices by Project (pie) ───────────────────────────────────────────
fig = px.pie(df_dev, names="project", values="devices",
             title="Unique Devices by Project — January 2024", hole=0.35)
fig.update_layout(height=400)
fig
"""

    bar_top = """\
# ── Top 10 Articles — Jan 1 2024 (horizontal bar) ────────────────────────────
df_top_sorted = df_top.sort_values("views")
fig = px.bar(df_top_sorted, x="views", y="article", orientation="h",
             title="Top 10 en.wikipedia Articles — January 1 2024",
             labels={"views": "Pageviews", "article": ""})
fig.update_layout(height=420)
fig
"""

    cells = [
        cell(intro, "markdown"),
        cell(fetch_all),
        cell("## KPI — Total Pageviews", "markdown"),
        cell(kpi),
        cell("## Daily Pageviews by Project", "markdown"),
        cell(line_pv),
        cell("## Total Pageviews by Project", "markdown"),
        cell(bar_total),
        cell("## Unique Devices by Project", "markdown"),
        cell(pie_dev),
        cell("## Top 10 Articles — January 1, 2024", "markdown"),
        cell(bar_top),
    ]
    save(notebook(cells, "Wikipedia Analytics Dashboard"), out / "wikipedia_analytics_dashboard.ipynb")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="deepnote_demo")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating Deepnote-ready notebooks -> {out.resolve()}\n")
    q15_daily_pageviews(out)
    q16_total_pageviews(out)
    q17_counter(out)
    q18_daily_edits(out)
    q19_top_articles(out)
    q20_top_articles_bar(out)
    q21_unique_devices(out)
    dashboard_overview(out)

    print(f"\nDone. {len(list(out.glob('*.ipynb')))} notebooks ready.")
    print(f"\nTo import into Deepnote:")
    print(f"  1. deepnote.com -> New project")
    print(f"  2. Drag all .ipynb files from {out.resolve()} into the Files panel")
    print(f"  3. Start with wikipedia_analytics_dashboard.ipynb — runs end-to-end, no setup")

if __name__ == "__main__":
    main()
