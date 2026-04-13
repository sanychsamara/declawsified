# declawsified-core

The core classification engine for Declawsified. Implements the modular faceted
pipeline contract defined in `docs/plan-classification.md` §1.2.

## What's here (MVP scaffold)

- **Pipeline contract**: fixed `ClassifyInput` / `Classification` / `ClassifyResult`
  schemas and a `FacetClassifier` protocol every classifier implements.
- **Generic aggregator**: merges per-facet outputs using the registered arity
  (`scalar` or `array`) — no per-facet branching in the pipeline.
- **Mock classifiers**: one deterministic mock per MVP facet
  (context, domain, activity, project, phase) exercising the contract end-to-end.

Mocks exist to validate the contract before real Tier 1 rules, Tier 2 keywords/ML,
and Tier 3 LLM classifiers land in subsequent phases (see `docs/plan.md` §4).

## Quickstart

```bash
uv pip install -e ".[dev]"
pytest tests/ -v
```

## Extending

- **New classifier for an existing facet**: implement `FacetClassifier` in
  `declawsified_core/facets/<facet>.py` and register it in
  `declawsified_core/registry.py::default_classifiers()`. The pipeline runs it
  alongside the existing ones; the aggregator picks the winner by confidence.
- **New facet**: add an entry to `FACETS` in `registry.py`, drop a classifier
  into `facets/<newfacet>.py`, register it. Nothing else changes.
