"""Run history in SQLite (P5-03): every evaluated commit is one row; `trend` prints how the metrics moved."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,              -- check-base | check-head | scheduled | manual
  ref TEXT, commit_sha TEXT NOT NULL, code_hash TEXT NOT NULL,
  dataset TEXT NOT NULL, cases INTEGER NOT NULL,
  config TEXT NOT NULL,            -- JSON: model, top_k, embed_model
  metrics TEXT NOT NULL,           -- JSON: overall + per category + per difficulty
  refusal_recall REAL, false_refusal_rate REAL, disclaimer_compliance REAL,
  citation_miss_rate REAL, context_recall REAL,
  latency_p50 REAL, latency_p95 REAL,
  cost_usd REAL NOT NULL,          -- 0 for the local model
  cases_from_cache INTEGER, gate TEXT  -- gate result for check-head rows: pass | fail
);
"""
COLS = ["refusal_recall", "false_refusal_rate", "disclaimer_compliance", "citation_miss_rate_proxy", "context_recall"]


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def record(con: sqlite3.Connection, run: dict, kind: str, ref: str, dataset: str, config: dict,
           gate: str | None = None, cost_usd: float = 0.0) -> str:
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = f"{at.replace(':', '').replace('-', '')[:15]}-{kind}-{run['commit']}"
    o = run["metrics"]["overall"]
    vals = [(o.get(c) or {}).get("value") for c in COLS]
    con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, at, kind, ref, run["commit"], run["code_hash"], dataset, len(run["rows"]),
                 json.dumps(config), json.dumps(run["metrics"]), *vals,
                 o["latency_s"]["p50"], o["latency_s"]["p95"], cost_usd, run["cache"]["cases_from_cache"], gate))
    con.commit()
    return run_id


def trend(con: sqlite3.Connection, limit: int = 20) -> str:
    rows = con.execute("SELECT at, kind, ref, commit_sha, cases, refusal_recall, false_refusal_rate, disclaimer_compliance,"
                       " citation_miss_rate, context_recall, latency_p50, latency_p95, gate FROM runs"
                       " ORDER BY at DESC LIMIT ?", (limit,)).fetchall()[::-1]

    def p(v):
        return "–" if v is None else f"{v:.0%}"

    out = ["| When (UTC) | Kind | Ref | Commit | n | Refusal recall | False refusal | Disclaimer | Citation miss "
           "| Context recall | p50/p95 s | Gate |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for at, kind, ref, sha, n, rr, fr, dc, cm, cr, p50, p95, gate in rows:
        out.append(f"| {at[:16]} | {kind} | {ref or ''} | {sha} | {n} | {p(rr)} | {p(fr)} | {p(dc)} | {p(cm)} | {p(cr)} "
                   f"| {p50}/{p95} | {gate or ''} |")
    return "\n".join(out)
