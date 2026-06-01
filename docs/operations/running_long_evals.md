# Running long evals

```bash
make bandit-monte-carlo     # bandit vs random, N seeds, CI
make retriever-stress       # synthetic large repo, budget never exceeded
make chaos                  # kill/resume workflow
make security-redteam       # malicious-task safety suite
make soak-6h                # repeated fake-agent workflows
make eval-bakeoff-overnight # adapter scorecard -> evals/reports/
```
