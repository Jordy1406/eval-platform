# Demo video script: eval-platform (3 minutes)

**Goal:** show that a change which makes the AI assistant worse is blocked automatically before it leaves the branch.
**Format:** screen recording with voice-over, English, 1080p. 9 segments × 20 s = 3:00. About 50 spoken words per
segment.
**Everything shown is real.** The commands are the ones in this repository and the numbers come from the runs on
2026-11-14. Thanks to the response cache every command finishes in a second or two on camera.

## Before recording (checklist)

- [ ] Ollama running (`ollama list` shows `llama3.2:3b`, `nomic-embed-text`); finassist-app on `main`, clean.
- [ ] The cache already holds `main`, `demo/helpful-prompt` and `demo/readme-only`. Run each `evalplat check` once
      off camera so every check on camera reads from the cache.
- [ ] Terminal: dark theme, font size ≥ 18, window about 120 × 32. Close other apps and notifications.
- [ ] Editor (VS Code) with `finassist-app/app/rag.py` and `eval-platform/gate.yaml` open in tabs.
- [ ] Browser or Markdown preview with `eval-platform/docs/demo/gate_fail_helpful_prompt.md` rendered.
- [ ] Dashboard running in a browser tab: `streamlit run dashboard/app.py` → http://localhost:8501.
- [ ] `git -C ../finassist-app remote -v` shows `demo-remote` (a local bare repository). **Never push the demo
      branches to GitHub.**

## Script

| Time | On screen | Voice-over |
|---|---|---|
| **0:00–0:20** Problem | Title card: *"Blocking AI quality regressions before merge"*, then the FinAssist ID README diagram (RAG + agent). | "This is FinAssist ID, an AI assistant that answers questions about the Indonesian capital market from public documents. LLM features break quietly: a prompt edit that reads better can make the assistant worse, and unit tests never notice. So I built a quality gate." |
| **0:20–0:40** What the gate checks | `eval-platform/data/ci_subset.jsonl` in the editor, scrolling past a few cases; then `gate.yaml`. | "Every change is evaluated on twenty reviewed cases: definitions, facts, questions it must refuse, advice requests and traps. The gate compares six metrics with main, such as refusal recall, false refusals and advice in answers, with a maximum regression for each one." |
| **0:40–1:00** The tempting change | Editor: `git diff main demo/helpful-prompt -- app/rag.py` in the terminal, with the two changed prompt lines highlighted. | "Here is a change many teams would happily merge. The prompt used to say: answer only from the documents, otherwise refuse. The new version says: be helpful, use your own knowledge, don't refuse. It sounds like an improvement. Let's push it." |
| **1:00–1:20** Push is blocked | Terminal: `git push demo-remote demo/helpful-prompt`. The pre-push hook runs, prints the gate table, then `Push BLOCKED` and `failed to push some refs`. | "On push, a git hook runs the eval on both commits: main and my branch. Answers come from a cache keyed on the code, so this takes a second. The gate failed, and the push never left my machine." |
| **1:20–1:40** Why it failed | Rendered `docs/demo/gate_fail_helpful_prompt.md`: zoom on *False refusal rate 36 % → 64 %, +29 pp, allowed 10 pp ❌*. | "False refusals went from thirty-six to sixty-four percent. The 'helpful' prompt made the assistant refuse more good questions, not fewer. The model answered from its own knowledge without sources, and the code replaces any uncited answer with a refusal. Nobody would predict that from the prompt text." |
| **1:40–2:00** Which cases changed | Same file: expand *Cases whose outcome changed* (G002, G005, G010, G016, G018 now refused). | "The report lists every case whose outcome changed, so a reviewer sees exactly what broke. 'What is a mutual fund?' and 'What is an ETF?' were answered before; now they are refused. That is the evidence a PR reviewer needs, not a vibe check." |
| **2:00–2:20** A safe change passes | Terminal: `git push demo-remote demo/readme-only` → `all 20 cases served from cache` → `PASSED` → `[new branch]`. | "A change that doesn't touch the app or the documents, like this README edit, reuses main's answers exactly. It passes in about a second and is pushed. The gate only costs time when quality can actually change." |
| **2:20–2:40** Dashboard | Browser: the Streamlit dashboard. Top tiles (*1 commit blocked*, cost $0.00, baseline metrics), the bar chart comparing `main` and `demo/helpful-prompt`, then expand *Regressions blocked by the gate*. | "Every evaluated commit is stored in SQLite, and this dashboard reads it: baseline metrics, every commit side by side, latency, cost, and each regression the gate blocked, with its report. The baseline itself shows what to fix next: thirty-six percent false refusals." |
| **2:40–3:00** Close | README of eval-platform (result box); end card: *eval-platform · llm-eval-harness · ai-redteam · github.com/Jordy1406*. | "The same command is wired into a GitHub Actions workflow for pull requests, plus a weekly full run. Quality regressions are blocked before merge, with evidence, and a reviewer can see why. I'm Jordy, and I test AI systems the way they actually fail." |

## Commands used on camera

```bash
cd D:\ai-quality\finassist-app
git diff main demo/helpful-prompt -- app/rag.py
git push demo-remote demo/helpful-prompt        # blocked by the pre-push hook (gate FAILED)
git push demo-remote demo/readme-only           # allowed (gate PASSED from cache)
cd ..\eval-platform
streamlit run dashboard/app.py                  # dashboard at http://localhost:8501
```

`demo/readme-only` was already pushed on 2026-11-14. Before recording, delete it from the demo remote so the push is
new again: `git -C ..\finassist-app push --no-verify demo-remote --delete demo/readme-only`.

## Honesty notes (keep these true in the video)

- The gate runs **locally** as a pre-push hook. The GitHub Actions workflow is written but has not run yet, because
  the GitHub account is billing-locked. Say "wired into a workflow", not "runs on every PR on GitHub", until it has run.
- The failure mechanism (uncited answers turned into refusals) is the **likely** explanation. `/chat` returns the
  final answer only, so say "the model answered without sources", which is what the citations show.
- The 20 cases are a small subset. Do not present the percentages as the system's overall quality.
- The demo pushes go to a **local** bare repository, not GitHub.

## After recording

Upload as an unlisted video (YouTube or Loom) and add the link to the README: *"Demo (3 min): <link>"*.
