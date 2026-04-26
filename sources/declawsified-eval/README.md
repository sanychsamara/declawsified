# declawsified-eval

Eval harness for the declawsified classification pipeline.

Implements the plan in [`docs/plan-ground-truth.md`](../../docs/plan-ground-truth.md):
- **Phase A** — unit benchmarks per classifier vs externally-curated public datasets (MASSIVE, DBPedia, DeepPavlov, WildBench, Stack Overflow, HH-RLHF).
- **Phase B** — synthetic DES-2000 end-to-end eval set (Claude-annotated WildChat samples).

## Install

```
pip install -e "./sources/declawsified-eval[hf,ml]"
```

Optional extras:
- `hf` — HuggingFace `datasets`, `scikit-learn`, `pandas` (every Phase A loader needs this).
- `ml` — `sentence-transformers` for Phase A5 (EmbeddingTagger vs DBPedia).
- `anthropic` — `anthropic` SDK for Phase B annotation only.

## Layout

```
declawsified_eval/
  datasets/        # HF loaders, one per public dataset
  crosswalks/      # YAML mappings from dataset labels → declawsified facets
  metrics.py       # precision, recall, F1, top-k, set-F1, Jaccard, kappa, Wilson CI
  models.py        # EvalExample, EvalDataset protocol
  runner.py        # generic eval driver
  report.py        # markdown report writer
```

Eval scripts live under `scripts/eval/phase_a_*.py`.

Cached HF downloads land in `data/eval/cache/` (git-ignored); per-test reports in `data/eval/phase_a/<test_id>/`.
