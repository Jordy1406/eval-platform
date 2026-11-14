"""Quality gate (P5-02): compare a candidate run with the baseline and render the PR comment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

LABELS = {
    "refusal_recall": "Refusal recall (must-refuse cases refused)",
    "disclaimer_compliance": "Disclaimer compliance (advice cases)",
    "advice_in_answer_rate": "Advice in answer (advice cases answered with a recommendation)",
    "false_refusal_rate": "False refusal rate (answerable cases refused)",
    "citation_miss_rate_proxy": "Citation-miss rate (answered, no required document cited)",
    "context_recall": "Context recall (required document retrieved)",
}


@dataclass
class Check:
    metric: str
    base: float | None
    head: float | None
    regression: float | None     # > 0 means worse
    threshold: float
    status: str                  # pass | fail | n/a

    @property
    def label(self) -> str:
        return LABELS.get(self.metric, self.metric)


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def value(metrics: dict, name: str) -> float | None:
    m = metrics["overall"].get(name)
    return None if m is None else m.get("value")


def compare(base: dict, head: dict, cfg: dict) -> tuple[list[Check], list[str]]:
    checks = []
    for name, rule in cfg["metrics"].items():
        b, h = value(base, name), value(head, name)
        if b is None or h is None:
            checks.append(Check(name, b, h, None, rule["max_regression"], "n/a"))
            continue
        regression = round((b - h) if rule["better"] == "higher" else (h - b), 4)
        checks.append(Check(name, b, h, regression, rule["max_regression"],
                            "fail" if regression > rule["max_regression"] + 1e-9 else "pass"))
    warnings = []
    ratio = cfg.get("latency", {}).get("p95_max_increase_ratio")
    bp, hp = base["overall"]["latency_s"]["p95"], head["overall"]["latency_s"]["p95"]
    if ratio is not None and bp and hp and hp > bp * (1 + ratio):
        warnings.append(f"p95 latency {bp:.1f}s → {hp:.1f}s (+{(hp / bp - 1):.0%}, warning threshold +{ratio:.0%})")
    return checks, warnings


def passed(checks: list[Check]) -> bool:
    return not any(c.status == "fail" for c in checks)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def comment(base_run: dict, head_run: dict, checks: list[Check], warnings: list[str], meta: dict) -> str:
    ok = passed(checks)
    lines = [
        f"## {'✅' if ok else '❌'} Eval quality gate: {'PASSED' if ok else 'FAILED'}", "",
        f"`{meta['head_ref']}` ({head_run['commit']}) vs baseline `{meta['base_ref']}` ({base_run['commit']}) · "
        f"{meta['cases']} cases · model {meta['model']} · thresholds `gate.yaml`", "",
        "| Metric | Baseline | This change | Regression | Allowed | |", "|---|---:|---:|---:|---:|:---:|",
    ]
    for c in checks:
        mark = {"pass": "✅", "fail": "❌", "n/a": "–"}[c.status]
        reg = "n/a" if c.regression is None else f"{c.regression * 100:+.0f} pp"
        lines.append(f"| {c.label} | {_pct(c.base)} | {_pct(c.head)} | {reg} | {c.threshold * 100:.0f} pp | {mark} |")
    bl, hl = base_run["metrics"]["overall"]["latency_s"], head_run["metrics"]["overall"]["latency_s"]
    lines += ["", f"Latency p50/p95: {bl['p50']}/{bl['p95']} s → {hl['p50']}/{hl['p95']} s"
                  f" (answers served from cache keep their first measured latency)."]
    for w in warnings:
        lines.append(f"⚠️ {w}")
    changed = changed_cases(base_run["rows"], head_run["rows"])
    if changed:
        lines += ["", "<details><summary>Cases whose outcome changed</summary>", "",
                  "| Case | Category | Baseline | This change |", "|---|---|---|---|"]
        lines += [f"| {cid} | {cat} | {b} | {h} |" for cid, cat, b, h in changed]
        lines += ["", "</details>"]
    lines += ["", f"Cache: baseline {base_run['cache']['cases_from_cache']}/{meta['cases']}, "
                  f"this change {head_run['cache']['cases_from_cache']}/{meta['cases']} cases reused."]
    if meta.get("confirmation"):
        lines += ["", "**Confirmation run:** " + meta["confirmation"]]
    return "\n".join(lines) + "\n"


def outcome(row: dict) -> str:
    if row["refused"]:
        return "refused"
    if row.get("citation_miss"):
        return "answered, required doc not cited"
    if row.get("advice_in_answer"):
        return "answered with advice"
    if row.get("disclaimer_ok") is False:
        return "answered, no disclaimer"
    return "answered" + (", disclaimer" if row.get("disclaimer_ok") else "")


def changed_cases(base_rows: list[dict], head_rows: list[dict]) -> list[tuple[str, str, str, str]]:
    b = {r["id"]: r for r in base_rows}
    return [(r["id"], r["kategori"], outcome(b[r["id"]]), outcome(r)) for r in head_rows
            if r["id"] in b and outcome(b[r["id"]]) != outcome(r)]
