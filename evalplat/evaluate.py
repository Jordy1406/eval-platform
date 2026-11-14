"""Evaluate one FinAssist ID commit on a dataset, with the llm-eval-harness metrics (same definitions as P2)."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

HARNESS = Path(os.getenv("HARNESS_PATH", Path(__file__).resolve().parents[2] / "llm-eval-harness"))
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from harness.metrics import aggregate, check_case  # noqa: E402
from harness.retrieval import Retriever  # noqa: E402
from harness.schema import Case  # noqa: E402

from evalplat.cache import ResponseCache  # noqa: E402
from evalplat.target import code_hash, running_target  # noqa: E402


@dataclass
class Settings:
    target_repo: Path
    index: Path
    cache_dir: Path
    model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    top_k: int = int(os.getenv("TOP_K", "4"))
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    embed_model: str = os.getenv("EMBED_MODEL", "nomic-embed-text")
    timeout: float = 300


def load_cases(path: Path) -> list[Case]:
    return [Case.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def evaluate_commit(commit: str, cases: list[Case], s: Settings, cache: ResponseCache, log=print) -> dict:
    """Return {"commit", "code_hash", "rows", "metrics", "cache": {...}, "seconds"}; starts the target only if needed."""
    chash = code_hash(s.target_repo, commit)
    index_id = file_sha(s.index)
    keys = {c.id: cache.key(chash, s.model, s.top_k, c.pertanyaan) for c in cases}
    rkeys = {c.id: cache.key("retrieval-" + index_id, s.embed_model, s.top_k, c.pertanyaan) for c in cases}
    cached = {cid: cache.get(k) for cid, k in keys.items()}
    missing = [c for c in cases if cached[c.id] is None]
    t0 = time.time()

    if missing:
        log(f"  {commit}: {len(missing)} of {len(cases)} cases not cached, starting the target ...")
        with running_target(s.target_repo, commit, s.index, env_extra={"OLLAMA_MODEL": s.model, "TOP_K": str(s.top_k)}) as url, \
                httpx.Client(base_url=url, timeout=s.timeout) as http:
            for c in missing:
                start = time.time()
                r = http.post("/chat", json={"message": c.pertanyaan})
                r.raise_for_status()
                value = {"response": r.json(), "latency_s": round(time.time() - start, 2)}
                cache.put(keys[c.id], value)
                cached[c.id] = value
                log(f"    {c.id} {value['latency_s']:.1f}s")
    else:
        log(f"  {commit}: all {len(cases)} cases served from cache")

    retriever = None
    rows = []
    for c in cases:
        ret = cache.get(rkeys[c.id])
        if ret is None:
            retriever = retriever or Retriever(s.index, s.ollama_host, s.embed_model, s.top_k)
            ret = {"ids": [h.id for h in retriever.search(c.pertanyaan)]}
            cache.put(rkeys[c.id], ret)
        rows.append(check_case(c, cached[c.id]["response"], ret["ids"], cached[c.id]["latency_s"]))
    return {"commit": commit, "code_hash": chash, "rows": rows, "metrics": aggregate(rows),
            "cache": {"cases_from_cache": len(cases) - len(missing), "cases_run": len(missing)},
            "seconds": round(time.time() - t0, 1)}
