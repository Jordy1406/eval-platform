"""Response cache for identical inputs (P5-01).

Key = (code hash of app/ and docs/ at the commit, model, TOP_K, question). The same question against the same code
and model is not sent to the model again. This makes repeated checks fast and keeps the baseline stable: a branch
that does not touch app/ or docs/ reuses main's answers exactly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ResponseCache:
    def __init__(self, root: Path):
        self.root = root
        self.hits = self.misses = 0

    @staticmethod
    def key(code_hash: str, model: str, top_k: int, question: str) -> str:
        raw = json.dumps([code_hash, model, top_k, question], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if p.exists():
            self.hits += 1
            return json.loads(p.read_text(encoding="utf-8"))
        self.misses += 1
        return None

    def put(self, key: str, value: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
