"""Eval dashboard (P5-04): trends, per-category results, latency, cost and regressions from history.sqlite.

    streamlit run dashboard/app.py          # http://localhost:8501
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "history.sqlite"
RUNS = ROOT / "runs"

METRICS = {
    "refusal_recall": ("Refusal recall", "higher"),
    "false_refusal_rate": ("False refusal rate", "lower"),
    "disclaimer_compliance": ("Disclaimer compliance", "higher"),
    "advice_in_answer_rate": ("Advice in answer", "lower"),
    "citation_miss_rate": ("Citation-miss rate", "lower"),
    "context_recall": ("Context recall", "higher"),
}
CATEGORY_METRICS = {"refusal_recall": "Refusal recall", "false_refusal_rate": "False refusal",
                    "disclaimer_compliance": "Disclaimer", "citation_miss_rate_proxy": "Citation miss",
                    "context_recall": "Context recall"}

st.set_page_config(page_title="FinAssist ID · eval dashboard", layout="wide")


@st.cache_data(ttl=30)
def load() -> pd.DataFrame:
    if not DB.exists():
        return pd.DataFrame()
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query("SELECT * FROM runs ORDER BY at", con)
    df["at"] = pd.to_datetime(df["at"])
    # Older hook runs stored the full commit sha as ref; show a branch name when there is one, else the short sha.
    ref = df["ref"].fillna("").where(~df["ref"].fillna("").str.fullmatch(r"[0-9a-f]{40}"), "")
    df["label"] = (ref.where(ref != "", "commit") + " · " + df["commit_sha"].str[:7])
    return df


df = load()
st.title("FinAssist ID · eval dashboard")
st.caption("Source: eval-platform `history.sqlite`, one row per evaluated commit. 20-case CI subset, local "
           "llama3.2:3b, cost $0. Rates are shares of the cases each metric applies to.")
if df.empty:
    st.info("No runs yet: run `python -m evalplat check` first.")
    st.stop()

# One row per distinct (commit, code): the checks re-evaluate main often and cached runs repeat identical numbers.
distinct = df.sort_values("at").drop_duplicates(["commit_sha", "dataset"], keep="last")
heads = df[df["kind"] == "check-head"]
main = df[df["ref"] == "main"].iloc[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Runs recorded", len(df), help="Every evaluated commit, including baseline re-checks")
c2.metric("Distinct commits evaluated", distinct["commit_sha"].nunique())
blocked = heads.loc[heads["gate"] == "fail", "commit_sha"].nunique()
c3.metric("Commits blocked by the gate", blocked, help=f"{len(heads)} gate decisions in total, "
          f"{(heads['gate'] == 'fail').sum()} of them failures (the same commit can be checked several times)")
c4.metric("Cost (local model)", f"${df['cost_usd'].sum():.2f}")

st.subheader(f"Baseline: main ({main['commit_sha']})")
cols = st.columns(len(METRICS))
for col, (key, (label, better)) in zip(cols, METRICS.items()):
    v = main[key]
    col.metric(label, "–" if pd.isna(v) else f"{v:.0%}", help=f"{better} is better")

st.subheader("Metrics per commit")
pick = st.multiselect("Metrics", list(METRICS), default=["false_refusal_rate", "citation_miss_rate", "context_recall"],
                      format_func=lambda k: METRICS[k][0])
if pick:
    chart = distinct.set_index("label")[pick].rename(columns={k: METRICS[k][0] for k in pick}) * 100
    st.bar_chart(chart, y_label="%", stack=False, height=320)
st.caption("Bars per distinct commit. A head commit that changes app/ or docs/ is re-evaluated; others reuse cached "
           "answers and score exactly like main.")

left, right = st.columns(2)
with left:
    st.subheader("Latency per commit")
    st.bar_chart(distinct.set_index("label")[["latency_p50", "latency_p95"]].rename(
        columns={"latency_p50": "p50 (s)", "latency_p95": "p95 (s)"}), stack=False, height=280)
    st.caption("Cached answers keep the latency measured on their first run.")
with right:
    st.subheader("Per category")
    run_label = st.selectbox("Run", list(distinct["label"])[::-1])
    row = distinct[distinct["label"] == run_label].iloc[0]
    by_cat = json.loads(row["metrics"])["by_kategori"]
    table = pd.DataFrame({cat: {name: (m.get(key) or {}).get("value") for key, name in CATEGORY_METRICS.items()}
                          | {"cases": m["cases"]} for cat, m in by_cat.items()}).T.astype(float)
    shown = table.copy().astype(object)
    for c in CATEGORY_METRICS.values():
        shown[c] = table[c].map(lambda v: "–" if pd.isna(v) else f"{v:.0%}")
    shown["cases"] = table["cases"].astype(int)
    st.dataframe(shown, use_container_width=True)
    st.caption("– = the metric does not apply to that category (e.g. refusal recall only to must-refuse cases).")

st.subheader("Regressions blocked by the gate")
fails = heads[heads["gate"] == "fail"].drop_duplicates("commit_sha", keep="last")
if fails.empty:
    st.success("No gate failures recorded.")
for _, f in fails.iloc[::-1].iterrows():
    report = RUNS / f"{f['run_id']}.md"
    with st.expander(f"❌ {f['ref']} ({f['commit_sha']}) · {f['at']:%Y-%m-%d %H:%M} UTC"):
        st.markdown(report.read_text(encoding="utf-8") if report.exists() else "_report file not found_")

with st.expander("All runs (raw)"):
    st.dataframe(df.drop(columns=["metrics", "config", "label"]).iloc[::-1], use_container_width=True)
