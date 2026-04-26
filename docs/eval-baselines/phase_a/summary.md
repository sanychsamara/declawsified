# Phase A — Summary

- Generated: 2026-04-24T23:23:34.576065+00:00
- Git SHA: fc7534b
- Started:  2026-04-24T23:22:56.532582+00:00

## Results

| Test | Description | Metric | Target | Actual | Pass | Runtime |
| --- | --- | --- | --- | --- | --- | --- |
| `a1_sports` | KeywordTagger sports recall (Yahoo Answers) | recall | 90% | 33.2% | ❌ | 4.3s |
| `a2_entertainment` | KeywordTagger entertainment recall (Yahoo Answers) | recall | 85% | 37.0% | ❌ | 3.8s |
| `a3_engineering` | KeywordTagger engineering recall (Stack Overflow) | recall | 80% | 28.7% | ❌ | 3.6s |
| `a4_sensitive` | KeywordTagger sensitive recall+precision (HH-RLHF) | recall | 70% | 1.3% | ❌ | 6.3s |
| `a5_embedding_dbpedia` | EmbeddingTagger top-3 acc (DBPedia) | top-3-accuracy | 40% | 5.0% | ❌ | 16.3s |
| `a6_domain_massive` | DomainKeywordsClassifier accuracy (MASSIVE) | accuracy | 60% | 92.5% | ✅ | 3.9s |

Per-test details: `data/eval/phase_a/<test_id>/report.md`
