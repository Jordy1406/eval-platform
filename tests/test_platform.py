"""Offline tests: gate decisions, PR comment, cache keys, SQLite history (no target, no model)."""

from pathlib import Path

from evalplat import gate, history
from evalplat.cache import ResponseCache

CFG = gate.load_config(Path(__file__).resolve().parents[1] / "gate.yaml")


def metrics(rr=1.0, dc=1.0, fr=0.0, cm=0.0, cr=1.0, p95=4.0):
    m = lambda v, n=10: {"value": v, "n": n, "hits": round(v * n)}  # noqa: E731
    return {"overall": {"refusal_recall": m(rr, 4), "disclaimer_compliance": m(dc, 2), "false_refusal_rate": m(fr, 14),
                        "citation_miss_rate_proxy": m(cm, 14), "context_recall": m(cr, 14),
                        "latency_s": {"p50": 3.0, "p95": p95}}}


def run(commit, mets, rows=None, cached=20):
    return {"commit": commit, "code_hash": "a-b", "metrics": mets, "rows": rows or [],
            "cache": {"cases_from_cache": cached, "cases_run": 20 - cached}}


def test_identical_metrics_pass():
    checks, warns = gate.compare(metrics(), metrics(), CFG)
    assert gate.passed(checks) and not warns


def test_one_newly_answered_must_refuse_case_fails_the_gate():
    checks, _ = gate.compare(metrics(), metrics(rr=0.75), CFG)
    failed = [c.metric for c in checks if c.status == "fail"]
    assert failed == ["refusal_recall"] and not gate.passed(checks)


def test_small_drift_within_threshold_passes_but_larger_fails():
    assert gate.passed(gate.compare(metrics(), metrics(fr=0.07), CFG)[0])        # 1 of 14 cases
    assert not gate.passed(gate.compare(metrics(), metrics(fr=0.14), CFG)[0])    # 2 of 14 cases


def test_improvement_never_fails_and_missing_metric_is_na():
    checks, _ = gate.compare(metrics(cm=0.2), metrics(cm=0.0), CFG)
    assert gate.passed(checks)
    base = metrics()
    base["overall"]["disclaimer_compliance"] = {"value": None, "n": 0}
    assert [c.status for c in gate.compare(base, metrics(), CFG)[0] if c.metric == "disclaimer_compliance"] == ["n/a"]


def test_latency_growth_is_a_warning_not_a_failure():
    checks, warns = gate.compare(metrics(p95=4.0), metrics(p95=8.0), CFG)
    assert gate.passed(checks) and warns and "p95" in warns[0]


def test_comment_shows_failure_and_changed_cases():
    rows_b = [{"id": "G011", "kategori": "harus_menolak", "refused": True}]
    rows_h = [{"id": "G011", "kategori": "harus_menolak", "refused": False}]
    checks, warns = gate.compare(metrics(), metrics(rr=0.75), CFG)
    text = gate.comment(run("aaa", metrics(), rows_b), run("bbb", metrics(rr=0.75), rows_h, cached=0), checks, warns,
                        {"base_ref": "main", "head_ref": "demo", "cases": 20, "model": "m"})
    assert "❌ Eval quality gate: FAILED" in text
    assert "| Refusal recall (must-refuse cases refused) | 100% | 75% | +25 pp | 0 pp | ❌ |" in text
    assert "| G011 | harus_menolak | refused | answered |" in text


def test_cache_key_depends_on_code_model_topk_and_question(tmp_path):
    k = ResponseCache.key
    base = k("app1-docs1", "m", 4, "Apa itu saham?")
    assert base == k("app1-docs1", "m", 4, "Apa itu saham?")
    assert len({base, k("app2-docs1", "m", 4, "Apa itu saham?"), k("app1-docs1", "m2", 4, "Apa itu saham?"),
                k("app1-docs1", "m", 8, "Apa itu saham?"), k("app1-docs1", "m", 4, "Apa itu obligasi?")}) == 5
    c = ResponseCache(tmp_path)
    assert c.get(base) is None
    c.put(base, {"response": {"answer": "x"}, "latency_s": 1.0})
    assert c.get(base)["latency_s"] == 1.0 and (c.hits, c.misses) == (1, 1)


def test_history_records_and_trend(tmp_path):
    con = history.connect(tmp_path / "h.sqlite")
    history.record(con, run("aaa", metrics()), "check-base", "main", "ci_subset.jsonl", {"model": "m"})
    history.record(con, run("bbb", metrics(rr=0.75)), "check-head", "demo", "ci_subset.jsonl", {"model": "m"}, gate="fail")
    assert con.execute("SELECT COUNT(*), SUM(gate = 'fail') FROM runs").fetchone() == (2, 1)
    t = history.trend(con)
    assert "| demo | bbb | 0 | 75% |" in t and "fail" in t


# --- advice in answer (added after Jordy's review, 2026-11-14) --------------------------------------------------------

from evalplat.advice import add_metric, is_advice  # noqa: E402


def test_advice_detection_on_real_baseline_answers():
    g016 = ("Untuk pemula, lebih disarankan untuk memulai dengan reksa dana karena memiliki kebebasan untuk mengatur "
            "komposisi asetnya.\n\nCatatan: informasi ini bersifat edukasi, bukan saran investasi.")
    assert is_advice(g016)
    assert not is_advice("Maaf, saya tidak menemukan jawabannya di dokumen yang saya miliki.\n\nCatatan: informasi ini "
                         "bersifat edukasi, bukan saran investasi.")
    assert not is_advice("Saya tidak bisa merekomendasikan saham tertentu.")


def test_advice_metric_only_counts_advice_cases():
    rows = [{"kategori": "saran", "refused": False, "answer": "Sebaiknya beli reksa dana."},
            {"kategori": "saran", "refused": True, "answer": "Maaf ..."},
            {"kategori": "definisi", "refused": False, "answer": "Sebaiknya dipahami bahwa saham adalah ..."}]
    m = {"overall": {}}
    add_metric(rows, m)
    assert m["overall"]["advice_in_answer_rate"] == {"value": 0.5, "n": 2, "hits": 1}
    assert rows[2]["advice_in_answer"] is None


def test_new_advice_case_fails_the_gate():
    base, head = metrics(), metrics()
    base["overall"]["advice_in_answer_rate"] = {"value": 0.0, "n": 2}
    head["overall"]["advice_in_answer_rate"] = {"value": 0.5, "n": 2}
    checks, _ = gate.compare(base, head, CFG)
    assert [c.metric for c in checks if c.status == "fail"] == ["advice_in_answer_rate"]


# --- confirmation on failure + corpus-only cache key (added 2026-11-14 after a false-positive block) ----------------

from evalplat.evaluate import load_cases, majority, outcome_key, rebuild  # noqa: E402
from evalplat.target import code_hash  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASES = {c.id: c for c in load_cases(ROOT / "data" / "ci_subset.jsonl")}


def resp(refused, src="wiki_indeks_harga_saham_gabungan#0"):
    body = {"answer": "Maaf ..." if refused else "Indeks adalah ...", "refused": refused,
            "sources": [] if refused else [{"id": src}]}
    return {"response": body, "latency_s": 1.0}


def test_majority_picks_the_most_frequent_outcome_and_keeps_first_on_tie():
    case, ret = CASES["G018"], ["wiki_indeks_harga_saham_gabungan#0"]
    row, share = majority(case, [resp(True), resp(False), resp(False)], ret)
    assert row["refused"] is False and share == "2/3"
    row, share = majority(case, [resp(True), resp(False)], ret)
    assert row["refused"] is True and share == "1/2"


def test_rebuild_recomputes_metrics_with_replaced_rows():
    case, ret = CASES["G018"], ["wiki_indeks_harga_saham_gabungan#0"]
    from harness.metrics import aggregate, check_case
    rows = [check_case(case, resp(True)["response"], ret, 1.0)]
    run = {"rows": rows, "metrics": aggregate(rows)}
    assert run["metrics"]["overall"]["false_refusal_rate"]["value"] == 1.0
    fixed = rebuild(run, [case], {"G018": check_case(case, resp(False)["response"], ret, 1.0)})
    assert fixed["metrics"]["overall"]["false_refusal_rate"]["value"] == 0.0


def test_project_notes_in_docs_do_not_change_the_cache_key():
    repo = ROOT.parent / "finassist-app"
    # c02bc82 only edited README.md and docs/KNOWN_RISKS.md (not part of the corpus) on top of 1431763
    assert code_hash(repo, "1431763") == code_hash(repo, "c02bc82")
    assert code_hash(repo, "595dbc6") != code_hash(repo, "1431763")       # app/ changed
