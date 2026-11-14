"""Start FinAssist ID at a given commit, in its own git worktree, for one eval run."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout.strip()


def resolve(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--short=12", f"{ref}^{{commit}}")


def corpus_hash(repo: Path, commit: str) -> str:
    """Hash of the corpus files only: docs/*.md with a `source:` line in the front matter, the same rule the app's
    ingest uses. Project notes in docs/ (KNOWN_RISKS.md, SOURCES.md) do not reach the index, so editing them must not
    invalidate cached answers (it did on 2026-11-14 and let sampling noise fail the gate)."""
    blobs = []
    for line in git(repo, "ls-tree", commit, "docs/").splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind != "blob" or not path.endswith(".md"):
            continue
        head = git(repo, "cat-file", "-p", sha)[:2000]
        if head.startswith("---") and "\nsource:" in head.split("\n---", 2)[0] + "\n":
            blobs.append(f"{path}:{sha}")
    return hashlib.sha256("\n".join(sorted(blobs)).encode()).hexdigest()[:12]


def code_hash(repo: Path, commit: str) -> str:
    """Identity of what the eval depends on: the app code tree and the corpus files at that commit."""
    return git(repo, "rev-parse", f"{commit}:app")[:12] + "-" + corpus_hash(repo, commit)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def running_target(repo: Path, commit: str, index_path: Path, python: Path | None = None, env_extra: dict | None = None,
                   startup_timeout: float = 120):
    """Yield the base URL of FinAssist ID running `commit`. The worktree and the server are removed afterwards."""
    repo = repo.resolve()
    work = repo.parent / ".evalplat-worktrees" / commit
    if work.exists():
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(work)], capture_output=True)
    git(repo, "worktree", "add", "--detach", str(work), commit)
    python = python or (repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    port = free_port()
    env = {**os.environ, "INDEX_PATH": str(index_path.resolve()), "DOCS_DIR": str(work / "docs"), "API_KEYS": "",
           "RATE_LIMIT_PER_MIN": "0", "PYTHONUNBUFFERED": "1", **(env_extra or {})}
    log = open(work.parent / f"{commit}.log", "w", encoding="utf-8")
    proc = subprocess.Popen([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + startup_timeout
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"target exited during start-up; see {log.name}")
            try:
                if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.time() > deadline:
                raise RuntimeError(f"target did not start within {startup_timeout}s; see {log.name}")
            time.sleep(0.5)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(work)], capture_output=True)


if __name__ == "__main__":  # manual smoke test: python -m evalplat.target ../finassist-app HEAD
    with running_target(Path(sys.argv[1]), resolve(Path(sys.argv[1]), sys.argv[2]),
                        Path(sys.argv[1]) / "data" / "index.json") as u:
        print(u, httpx.get(f"{u}/health").json())
