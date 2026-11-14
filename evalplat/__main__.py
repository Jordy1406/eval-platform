"""Command line.

    python -m evalplat check [--base main] [--head HEAD]   # PR check: subset eval on base and head, quality gate
    python -m evalplat run [--ref main] [--dataset FILE]   # one evaluation (e.g. the scheduled full eval)
    python -m evalplat trend                               # run history from SQLite

`check` exits 1 when the gate fails, so it can block a push (hooks/pre-push) or a PR (GitHub Actions).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from evalplat import gate, history
from evalplat.cache import ResponseCache
from evalplat.evaluate import Settings, evaluate_commit, load_cases, majority, rebuild, resample
from evalplat.target import resolve

ROOT = Path(__file__).resolve().parents[1]


def settings(args) -> Settings:
    repo = Path(args.target_repo)
    return Settings(target_repo=repo, index=Path(args.index or repo / "data" / "index.json"),
                    cache_dir=Path(args.cache_dir))


def common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dataset", type=Path, default=ROOT / "data" / "ci_subset.jsonl")
    p.add_argument("--target-repo", default=os.getenv("TARGET_REPO", str(ROOT.parent / "finassist-app")))
    p.add_argument("--index", default=None, help="vector index (default <target-repo>/data/index.json)")
    p.add_argument("--cache-dir", default=str(ROOT / "cache"))
    p.add_argument("--db", type=Path, default=ROOT / "history.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "runs")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evalplat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="PR check with quality gate")
    common(c)
    c.add_argument("--base", default="main")
    c.add_argument("--head", default="HEAD")
    c.add_argument("--gate", type=Path, default=ROOT / "gate.yaml")
    c.add_argument("--confirm", type=int, default=2,
                   help="extra samples per changed case when the gate fails (majority of 1+N); 0 = no confirmation")
    r = sub.add_parser("run", help="evaluate one ref")
    common(r)
    r.add_argument("--ref", default="main")
    r.add_argument("--kind", default="manual", help="manual | scheduled")
    t = sub.add_parser("trend", help="print run history")
    t.add_argument("--db", type=Path, default=ROOT / "history.sqlite")
    t.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    if args.cmd == "trend":
        print(history.trend(history.connect(args.db), args.limit))
        return 0

    s = settings(args)
    cases = load_cases(args.dataset)
    cache = ResponseCache(Path(args.cache_dir))
    con = history.connect(args.db)
    config = {"model": s.model, "top_k": s.top_k, "embed_model": s.embed_model}
    args.out.mkdir(parents=True, exist_ok=True)

    if args.cmd == "run":
        commit = resolve(s.target_repo, args.ref)
        print(f"Evaluating {args.ref} ({commit}) on {len(cases)} cases")
        run = evaluate_commit(commit, cases, s, cache)
        rid = history.record(con, run, args.kind, args.ref, args.dataset.name, config)
        (args.out / f"{rid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: (v or {}).get("value") if isinstance(v, dict) else v
                          for k, v in run["metrics"]["overall"].items()}, indent=1, default=str))
        return 0

    base, head = resolve(s.target_repo, args.base), resolve(s.target_repo, args.head)
    print(f"Quality gate: {args.head} ({head}) vs {args.base} ({base}), {len(cases)} cases")
    base_run = evaluate_commit(base, cases, s, cache)
    head_run = base_run if head == base else evaluate_commit(head, cases, s, cache)
    cfg = gate.load_config(args.gate)
    checks, warnings = gate.compare(base_run["metrics"], head_run["metrics"], cfg)
    ok = gate.passed(checks)
    meta = {"base_ref": args.base, "head_ref": args.head, "cases": len(cases), "model": s.model}
    if not ok and head != base and args.confirm > 0:
        # A single sample per case can flip on model noise (2026-11-14: identical /chat code failed the gate).
        # Re-sample only the cases whose outcome changed, on both commits, and judge by majority.
        changed_ids = [cid for cid, *_ in gate.changed_cases(base_run["rows"], head_run["rows"])]
        if changed_ids:
            subset = [c for c in cases if c.id in changed_ids]
            print(f"Gate failed on first sample; confirming {len(subset)} changed case(s) with {args.confirm} more "
                  f"sample(s) on each commit ...")
            lines = []
            new_runs = []
            for run in (base_run, head_run):
                extra = resample(run["commit"], subset, s, args.confirm, cache)
                replaced = {}
                for c in subset:
                    row, share = majority(c, [run["responses"][c.id], *extra[c.id]], run["retrieved"][c.id])
                    replaced[c.id] = row
                    lines.append(f"{run['commit']} {c.id}: majority outcome {gate.outcome(row)} ({share})")
                new_runs.append(rebuild(run, cases, replaced))
            base_run, head_run = new_runs
            checks, warnings = gate.compare(base_run["metrics"], head_run["metrics"], cfg)
            ok = gate.passed(checks)
            meta["confirmation"] = (f"First sample failed the gate; {len(subset)} changed case(s) re-sampled "
                                    f"{args.confirm + 1}× on both commits, majority used. Final: "
                                    f"{'PASSED' if ok else 'FAILED'}.\n\n" + "\n".join(f"- {l}" for l in lines))
    text = gate.comment(base_run, head_run, checks, warnings, meta)
    history.record(con, base_run, "check-base", args.base, args.dataset.name, config)
    rid = history.record(con, head_run, "check-head", args.head, args.dataset.name, config, gate="pass" if ok else "fail")
    (args.out / f"{rid}.md").write_text(text, encoding="utf-8")
    (args.out / "latest_comment.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
