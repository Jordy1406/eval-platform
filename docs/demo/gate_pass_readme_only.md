## ✅ Eval quality gate: PASSED

`4798b591514ee4abd54da001997e0b91d0de7cd3` (4798b591514e) vs baseline `main` (1431763b598a) · 20 cases · model llama3.2:3b · thresholds `gate.yaml`

| Metric | Baseline | This change | Regression | Allowed | |
|---|---:|---:|---:|---:|:---:|
| Refusal recall (must-refuse cases refused) | 100% | 100% | +0 pp | 0 pp | ✅ |
| Disclaimer compliance (advice cases) | 100% | 100% | +0 pp | 0 pp | ✅ |
| False refusal rate (answerable cases refused) | 36% | 36% | +0 pp | 10 pp | ✅ |
| Citation-miss rate (answered, no required document cited) | 33% | 33% | +0 pp | 10 pp | ✅ |
| Context recall (required document retrieved) | 79% | 79% | +0 pp | 10 pp | ✅ |

Latency p50/p95: 8.75/46.47 s → 8.75/46.47 s (answers served from cache keep their first measured latency).

Cache: baseline 20/20, this change 20/20 cases reused.
