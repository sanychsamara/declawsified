# Evaluation Datasets — Research & Recommendations

**Purpose:** Find public conversational/text datasets with thematic labels we can use to evaluate the declawsified classification pipeline. Specifically: how well do our 5 facets (`context`, `domain`, `activity`, `project`, `tags`) recover labels that humans/researchers have already assigned?

**Status:** Research complete (2026-04-24). Recommendations at the end.

---

## TL;DR

**Our facet model has no perfect-fit public dataset.** No published dataset uses `context/domain/activity/project/tags` exactly. The closest matches:

| Our facet | Best public proxy | Why |
|---|---|---|
| `activity` | **WildBench** (12 task categories: info-seeking, coding, planning, ...) | Categories map almost 1:1 to our 10 activity values |
| `domain` | **MASSIVE** (18 domains: cooking, finance, news, sports, travel, ...) | Single-utterance but matches our domain semantics |
| `tags` | **DBPedia hierarchical** (3 levels: 9/70/219 classes) | Hierarchical taxonomy is the only public ontology that matches our v2 tree shape |
| `tags` (alt) | **DeepPavlov Topics** (33 topics, multi-label, conversational) | Multi-label tag setting matches our array-arity tags |
| `context` | **None directly** — derive from working_directory or session metadata | No dataset distinguishes personal-vs-business AI use |
| `project` | **None directly** — derived from git/workdir, not in any text dataset | Project attribution requires metadata we don't get from text dumps |

**Recommended evaluation plan** (see [§7](#7-recommended-evaluation-plan)):

1. **Unit-tier benchmarks**: validate each classifier in isolation against its closest public proxy (KeywordTagger + EmbeddingTagger vs DBPedia / DeepPavlov; activity rules vs WildBench)
2. **End-to-end synthetic benchmark**: Claude-annotate ~2000 messages from WildChat across all 5 facets (Anthropic Batch API + prompt caching; ~$11 total) to create a "Declawsified Eval Set v2" (DES-2000), calibrated against a 100-sample human spot-check
3. **Coverage check**: sample 1k WildChat conversations, run classifier, verify no `tags=unknown` rate exceeds 10%
4. **Long-tail validation**: rare tags should appear at expected proportions (sports for ~5%, sensitive for ~2%, etc.)

---

## 1. Real-World Conversation Datasets (no topic labels, but realistic)

These are the gold standard for *coverage* and *realism* but lack topic labels. Use them to:
- Verify our taxonomy covers what real users actually ask
- Sanity-check `tags=unknown` rates
- Test session continuity across multi-turn flows

### WildChat-4.8M *(allenai)*

- **Size**: 3.2M conversations (4.8M total raw), 74+ languages, multi-turn (2-498 turns)
- **Schema**: full message arrays, per-message moderation/toxicity labels, language detection, country, timestamps, model used
- **Labels for us**: ❌ no topic labels; only moderation (harassment, hate, illicit, self-harm, sexual, violence)
- **License**: ODC-BY (commercial OK)
- **Use**: bulk corpus for coverage analysis. ~100K English conversations is enough to validate any taxonomy.
- **Source**: [allenai/WildChat-4.8M](https://huggingface.co/datasets/allenai/WildChat-4.8M) ([nontoxic subset](https://huggingface.co/datasets/allenai/WildChat-nontoxic))

### LMSYS-Chat-1M *(LMSYS / Chatbot Arena)*

- **Size**: 1M conversations, 154 languages, avg 2 turns
- **Schema**: OpenAI Messages format, 25 different LLMs, moderation tags, redaction flag
- **Labels for us**: ❌ no topic labels (but research has clustered into ~24 topic categories using GPT-4 + sentence-transformers + k-means)
- **License**: custom — research and commercial OK, no redistribution
- **Use**: cross-model conversation diversity. The arxiv paper's 24-cluster annotation could be a labeled subset.
- **Source**: [lmsys/lmsys-chat-1m](https://huggingface.co/datasets/lmsys/lmsys-chat-1m) · [paper](https://arxiv.org/abs/2309.11998)

### ShareGPT variants

- **Size**: ~90K conversations scraped from ShareGPT.com (real ChatGPT shares)
- **Schema**: ShareGPT format (`conversations: [{from, value}]`)
- **Labels for us**: ❌ no topic labels
- **Use**: realistic multi-turn conversations skewed toward technical/coding queries
- **Sources**: [icybee/share_gpt_90k_v1](https://huggingface.co/datasets/icybee/share_gpt_90k_v1), [openchat/openchat_sharegpt4_dataset](https://huggingface.co/datasets/openchat/openchat_sharegpt4_dataset), [RyokoAI/ShareGPT52K](https://huggingface.co/datasets/RyokoAI/ShareGPT52K)

### HH-RLHF *(Anthropic)*

- **Size**: ~169K (helpful) + ~42K (harmless) + 38K red-team transcripts
- **Schema**: chosen/rejected response pairs; red-team data has `transcript`, `task_description`, `harmlessness_score`
- **Labels for us**: ⚠️ helpfulness + harmlessness preferences; red-team task_description is freeform text describing what the attacker tried (could be parsed)
- **License**: MIT
- **Use**: edge cases for `sensitive` tag, alignment with safety classifications
- **Source**: [Anthropic/hh-rlhf](https://huggingface.co/datasets/Anthropic/hh-rlhf)

---

## 2. Datasets with Real Thematic Labels (smaller but labeled)

These have explicit topic/domain/intent labels we can directly compare against.

### WildBench *(allenai)* ⭐ best activity-facet match

- **Size**: 1,024 tasks selected from real chatbot logs, multi-turn (up to 4 turns)
- **Schema**: prompt + multi-turn history + 12-category task label + checklist for evaluation
- **Labels**:
  - **12 task categories** consolidated to 5 groups for easier analysis:
    - Info Seeking (information-seeking, advice-seeking)
    - Math & Data (math, data analysis)
    - Reasoning & Planning (reasoning, planning)
    - Coding & Debugging
    - Creative Tasks (creative writing, editing, role play, brainstorming)
- **License**: research-friendly
- **Use for declawsified**: **map directly to `activity` facet**. WildBench's "Coding & Debugging" → our `building`/`investigating`. "Information seeking" → our `researching`. "Planning" → our `planning`. Etc.
- **Source**: [WildBench paper (PDF)](https://allenai.github.io/WildBench/WildBench_paper.pdf) · [arxiv](https://arxiv.org/html/2406.04770v1)

### MASSIVE *(Amazon)* ⭐ best domain-facet match

- **Size**: 1M utterances, 51 languages, single-utterance (NOT conversation)
- **Schema**: `utt`, `annot_utt`, `scenario` (domain), `intent`, slot annotations, judgments
- **Labels**:
  - **18 domains**: alarm, audio, cooking, entertainment, iot, lists, messaging, music, news, payments, recipes, reminder, services, shopping, social, sports, travel, weather
  - **60 intents** (e.g., `alarm_set`, `iot_hue_lightoff`, `music_play_song`)
- **License**: CC BY 4.0
- **Use for declawsified**: validate `domain` facet, especially `KeywordTagger` for sports/entertainment/travel/food. Test that "wake me up at 9am" classifies as `domain=alarm` correctly.
- **Caveat**: single-utterance, voice-assistant style — narrower than open chat
- **Source**: [AmazonScience/massive](https://huggingface.co/datasets/AmazonScience/massive) · [paper](https://arxiv.org/abs/2204.08582)

### DeepPavlov Topics ⭐ best tags-facet match (multi-label)

- **Size**: 4.2M samples (full) / 2.2M (downsampled), conversational domain, English
- **Labels**: **33 multi-label topics**:
  - Animals&Pets, Art&Hobbies, Artificial Intelligence, Beauty, Books&Literature, Celebrities&Events, Clothes, Depression, Disasters, Education, Family&Relationships, Finance, Food, Gadgets, Garden, Health&Medicine, Home&Design, Job, Leisure, MassTransit, Movies&Tv, Music, News, Personal Transport, Politics, Psychology, Religion, Science&Technology, Space, Sports, Toys&Games, Travel, VideoGames
- **License**: research
- **Use for declawsified**: directly map to our v2 taxonomy `tags`. Multi-label setting matches our array-arity tags. Categories like Movies&Tv → `entertainment`, Sports → `sports`, Gadgets → `engineering`-adjacent.
- **Source**: [DeepPavlov Topics](https://deeppavlov.ai/datasets/topics) · [paper](https://link.springer.com/chapter/10.1007/978-3-031-19032-2_39)

### DBPedia hierarchical *(DeveloperOats/DBPedia_Classes)* ⭐ best taxonomy-shape match

- **Size**: 337K Wikipedia article descriptions
- **Schema**: `text`, `l1` (level-1 class), `l2`, `l3`
- **Labels**: **9 → 70 → 219 hierarchical classes** (Agent, Work, Place, Species, Event, SportsSeason, UnitOfWork, Infrastructure, ...)
- **License**: CC BY-SA (Wikipedia)
- **Use for declawsified**: hierarchical eval — does EmbeddingTagger correctly walk the right branch? Same depth-3 shape as our v2 taxonomy. Testing leaf prediction accuracy maps directly to our setup.
- **Caveat**: documents (encyclopedia text), not conversations
- **Source**: [DeveloperOats/DBPedia_Classes](https://huggingface.co/datasets/DeveloperOats/DBPedia_Classes)

### Topical-Chat *(Amazon Alexa)*

- **Size**: ~11K conversations, ~235K utterances, knowledge-grounded
- **Labels**: explicit topic labels per conversation (8 broad topics: fashion, politics, books, sports, music, science & tech, entertainment, news)
- **License**: research
- **Use**: multi-turn conversations grounded in a given topic — gold standard for testing if classifier produces the topic the conversation is *about*.
- **Source**: [Conversational-Reasoning/Topical-Chat](https://huggingface.co/datasets/Conversational-Reasoning/Topical-Chat) · [github](https://github.com/alexa/Topical-Chat)

### DailyDialog

- **Size**: 13K human-human dialogues, multi-turn
- **Labels**: emotion (7 classes), dialog act (4 classes), topic (10 broad topics: ordinary life, school, culture, attitude, relationships, tourism, health, work, politics, finance)
- **License**: CC BY-NC-SA
- **Use**: 10-topic conversational benchmark for `tags` facet. Smaller scale but well-annotated.
- **Source**: [li2017dailydialog/daily_dialog](https://huggingface.co/datasets/li2017dailydialog/daily_dialog)

### MultiWOZ v2.2

- **Size**: ~10K multi-turn dialogues, task-oriented
- **Labels**: 7 domains (restaurant, hotel, attraction, taxi, train, hospital, police), dialog acts per turn, slot annotations
- **License**: MIT
- **Use**: gold standard for activity transitions across domains within a session. Tests `domain` facet handling of multi-domain sessions (one of the hardest cases).
- **Source**: [pfb30/multi_woz_v22](https://huggingface.co/datasets/pfb30/multi_woz_v22)

### Action-Based Conversations Dataset (ABCD)

- **Size**: 10K human-to-human dialogues
- **Labels**: 55 distinct user intents, action sequences, policy constraints
- **Use**: fine-grained intent classification beyond what MASSIVE offers
- **Source**: [paper](https://www.researchgate.net/publication/350625584)

### TUNA *(Taxonomy of User Needs and Actions)*

- **Size**: 1,193 human-AI conversations, qualitatively analyzed
- **Labels**: **3-level hierarchy** of user actions: information seeking, synthesis, procedural guidance, content creation, social interaction, meta-conversation
- **Use**: validation framework for `activity` taxonomy — TUNA's hierarchy could inform a v2 of our 10 universal activities
- **Source**: [Taxonomy of User Needs and Actions paper](https://arxiv.org/html/2510.06124v2)

---

## 3. Engineering / Coding-Specific (relevant for `engineering` domain & tags)

### CodeXGLUE *(Microsoft)*

- **Size**: 14 datasets across 10 programming tasks
- **Labels**: per-task (clone detection, defect detection, code search, code summarization, ...)
- **Use**: validate that our `engineering` keyword + `engineering` taxonomy branch covers real developer workflows
- **Source**: [github](https://github.com/microsoft/CodeXGLUE)

### CodeAssistBench (CAB)

- **Size**: scalable, multi-turn codebase-grounded conversations
- **Labels**: Correct / Partially Correct / Incorrect (LLM judge)
- **Use**: realistic multi-turn coding conversations (closest to actual Claude Code traffic)
- **Source**: [paper](https://arxiv.org/html/2507.10646v5)

### WorkBench

- **Size**: 690 unique workplace tasks
- **Labels**: task templates (email, calendar, CRM, ...)
- **Use**: validate our `work/*` taxonomy branches (engineering, marketing, sales, hr, ops)
- **Source**: [paper](https://arxiv.org/html/2405.00823v2)

### Stack Overflow datasets

- **Size**: millions of questions/answers
- **Labels**: tags (multi-label) + categories
- **Use for declawsified**: tag distribution validation; specifically test `engineering` subtopics (databases, frontend, backend, devops) match Stack Overflow tag conventions
- **Sources**: [pacovaldez/stackoverflow-questions](https://huggingface.co/datasets/pacovaldez/stackoverflow-questions), [HuggingFaceH4/stack-exchange-preferences](https://huggingface.co/datasets/HuggingFaceH4/stack-exchange-preferences)

---

## 4. Quality / Helpfulness Datasets (preference signals)

### HelpSteer / HelpSteer2 / HelpSteer3 *(NVIDIA)*

- **Size**: HelpSteer 37K, HelpSteer2 21K, HelpSteer3 ~50K
- **Labels**: per-response 5-attribute scores (helpfulness, correctness, coherence, complexity, verbosity), 0-4 scale + task category (Rewrite, Summarization, Classification, Extraction, Closed QA, Open QA, Generation, Brainstorming)
- **License**: CC BY 4.0
- **Use**: task-category labels overlap with our `activity` facet. 8 task categories → maps to ~6 of our 10 activities.
- **Source**: [nvidia/HelpSteer](https://huggingface.co/datasets/nvidia/HelpSteer) · [HelpSteer2](https://huggingface.co/datasets/nvidia/HelpSteer2)

### Daring-Anteater *(NVIDIA)*

- **Size**: ~100K (mostly synthetic)
- **Labels**: instruction tuning task types
- **Use**: synthetic but diverse task coverage
- **Source**: [nvidia/Daring-Anteater](https://huggingface.co/datasets/nvidia/Daring-Anteater)

---

## 5. Single-Document Topic Classification (for tags-facet validation)

These are document-level (not conversational) but have well-curated topic labels. Useful for stress-testing the `EmbeddingTagger` against fixed gold-standard labels.

| Dataset | Categories | Notes |
|---|---|---|
| **20 Newsgroups** | 20 | Classic, balanced, public |
| **AG News** | 4 | World/Sports/Business/Sci-Tech — mainstream news |
| **Yahoo Answers** | 10 | Question categories: Society & Culture, Science, Health, Education, Computers, Sports, Business, Entertainment, Family, Politics |
| **HuffPost News Category** | 41 | Fine-grained news categorization |
| **Reuters-21578** | 90 (multi-label) | News, multi-label |
| **DBPedia 14** | 14 | Flat version of hierarchical above |

For our purpose, **DBPedia hierarchical** is the most useful (matches our 3-level taxonomy structure).

---

## 6. Specialized

### Health/Medical conversations

- **Nature Health Study (2026)** — hierarchical 12-intent taxonomy for health queries. Symptom assessment, condition management, emotional well-being, caregiving. ([source](https://www.nature.com/articles/s44360-026-00117-x))
- **Mental Health Counseling Datasets** — 5 known sets, useful for `sensitive` tag validation

### Customer support

- **syncora/customer_support_conversations_dataset** — categorized support tickets ([source](https://huggingface.co/datasets/syncora/customer_support_conversations_dataset))

### Spoken/dialog acts

- **SILICONE benchmark** — 10 spoken-dialog datasets with sequence labels ([source](https://huggingface.co/datasets/silicone))

---

## 7. Recommended Evaluation Plan

### Phase A — Unit benchmarks per classifier (1-2 days)

| Classifier | Eval dataset | Metric | Target |
|---|---|---|---|
| `KeywordTagger` (sports group) | MASSIVE `sports` domain | recall | >90% |
| `KeywordTagger` (entertainment) | MASSIVE `entertainment` + DeepPavlov `Movies&Tv`/`Music` | recall | >85% |
| `KeywordTagger` (engineering) | Stack Overflow tag-filtered subset | recall | >80% |
| `KeywordTagger` (sensitive) | HH-RLHF red-team subset | recall | >70%, precision >50% |
| `EmbeddingTagger` (any leaf) | DBPedia L3 (219 classes) | top-3 accuracy vs label | >40% (random ~1.4%) |
| `DomainKeywordsClassifier` | MASSIVE 18 domains | accuracy | >60% |
| `ActivityRulesClassifier` | WildBench 5 consolidated categories | accuracy | >70% (currently always `unknown` because no tool_calls in proxy mode — gated on TODO #2 of plan-classification.md) |

### Phase B — Synthetic end-to-end eval set (DES-2000, 4-5 days)

Build a "Declawsified Eval Set" with **Claude-annotated** (synthetic) labels, 10× the original DES-200 proposal. Full implementation plan lives in [`plan-ground-truth.md`](./plan-ground-truth.md).

1. Sample 2000 messages from WildChat (English, nontoxic, length 50-500 chars) — 1500 random + 500 stratified from rare-topic embedding clusters so the long-tail taxonomy leaves are covered.
2. Annotate each message across all 5 facets via the Anthropic Batch API (Claude Sonnet 4.6, prompt-cached taxonomy + few-shot examples):
   - `context`: personal | business | unknown
   - `domain`: engineering | marketing | finance | legal | health | unknown
   - `activity`: investigating | building | improving | verifying | researching | planning | communicating | configuring | reviewing | coordinating | unknown
   - `project`: free-text or unknown
   - `tags`: 0-5 from v2 taxonomy leaves
3. Quality-check: self-consistency re-run on 200 samples (temperature variant), cross-model re-run on 100 with Opus 4.7, and a 100-sample human spot-check to calibrate synthetic→human agreement.
4. Run the full declawsified pipeline, measure per-facet F1 + per-tag precision/recall.
5. DES-2000 becomes the permanent regression set — CI runs on every taxonomy or classifier change.

**Synthetic caveat.** Labels are generated by Claude, not humans. Agreement with the 100-sample human spot-check is reported as the calibration factor. Treat absolute metrics as approximate; treat deltas across pipeline versions as meaningful.

**Cost:** ~$11 total (~$7 Sonnet batch + ~$3 Opus cross-check + ~$1 self-consistency), using batch API + prompt caching.

**Target**: ≥75% F1 on `tags` after 3 iterations (calibrated). ≥60% on `activity` once tool-call extraction (TODO #2) ships.

### Phase C — Long-tail coverage (1 day)

1. Sample 1000 random WildChat conversations
2. Run classifier with v2 taxonomy
3. Compute:
   - % of messages with at least one tag (target: >85%)
   - % of v2 taxonomy leaves that fire at least once (target: >50% — anything less means we have dead branches)
   - Tag distribution: do `sensitive`/`sports`/`engineering` fire at expected proportions?
4. Identify dead branches (taxonomy leaves never matched) → candidates for v3 pruning

### Phase D — Multi-turn / session continuity (1 day)

1. Use Topical-Chat or DailyDialog (have multi-turn + topic labels)
2. Run through `classify_with_session` with full session continuity + arc revision
3. Measure: does the session-level inferred topic match the dataset's annotated topic?
4. Specifically validate the **anchor/follower** revision — for short-follow-up turns, does inheritance from the anchor match the dataset's per-turn annotation?

---

## 8. Datasets we've ALREADY produced

Don't forget what we have in-house:

- **`data/chat-gpt/`** — user's own ChatGPT export (639 conversations, 2,565 messages) classified across all 5 facets. Already validated v2 taxonomy at 100% coverage.
- **`data/claude/`** — Claude.ai export (15 messages, 2 conversations). Smaller but labeled with the same pipeline.
- **`data/all-conversations/classifications.json`** — 2,603 fully-classified messages from the 2026-04-23 batch run.
- **`docs/manager-analysis.md`** — example of what insights look like at scale.

These are **gold for regression testing** — every change to a classifier should be validated against the existing `classifications.json` to verify expected differences only.

---

## 9. Decision

**Ship Phase A first** (1-2 days, mostly automated). It validates each classifier in isolation against existing labeled benchmarks — fast feedback on whether KeywordTagger, EmbeddingTagger, and DomainKeywordsClassifier have any signal at all.

**Then ship Phase B (DES-2000, Claude-annotated)** — this is the most valuable artifact long-term. Once we have a 2000-message Claude-labeled eval set (calibrated against a 100-sample human spot-check), every classifier change is measurable. See [`plan-ground-truth.md`](./plan-ground-truth.md) for the implementation plan.

Phases C and D are nice-to-haves once A+B are stable.

---

## Appendix — Datasets considered but excluded

- **Vicuna ShareGPT unfiltered** — license unclear, contains PII
- **WildVision** — image-grounded, not relevant
- **PIPPA** — role-play / persona, off-domain
- **OpenAssistant (OASST1/2)** — quality labels but no thematic classification
- **MMLU / GSM8K / HumanEval** — model evaluation, not topic classification
- **Pile-of-Law** — legal documents, single-domain (already covered if we want legal-only eval)

---

## Sources

- [allenai/WildChat-4.8M](https://huggingface.co/datasets/allenai/WildChat-4.8M)
- [allenai/WildChat-nontoxic](https://huggingface.co/datasets/allenai/WildChat-nontoxic)
- [lmsys/lmsys-chat-1m](https://huggingface.co/datasets/lmsys/lmsys-chat-1m)
- [LMSYS-Chat-1M paper (arxiv)](https://arxiv.org/abs/2309.11998)
- [WildBench paper](https://allenai.github.io/WildBench/WildBench_paper.pdf)
- [WildBench arxiv](https://arxiv.org/html/2406.04770v1)
- [AmazonScience/massive](https://huggingface.co/datasets/AmazonScience/massive)
- [MASSIVE paper](https://arxiv.org/abs/2204.08582)
- [DeepPavlov Topics](https://deeppavlov.ai/datasets/topics)
- [DeveloperOats/DBPedia_Classes](https://huggingface.co/datasets/DeveloperOats/DBPedia_Classes)
- [fancyzhx/dbpedia_14](https://huggingface.co/datasets/fancyzhx/dbpedia_14)
- [Conversational-Reasoning/Topical-Chat](https://huggingface.co/datasets/Conversational-Reasoning/Topical-Chat)
- [li2017dailydialog/daily_dialog](https://huggingface.co/datasets/li2017dailydialog/daily_dialog)
- [pfb30/multi_woz_v22](https://huggingface.co/datasets/pfb30/multi_woz_v22)
- [Anthropic/hh-rlhf](https://huggingface.co/datasets/Anthropic/hh-rlhf)
- [nvidia/HelpSteer](https://huggingface.co/datasets/nvidia/HelpSteer)
- [nvidia/HelpSteer2](https://huggingface.co/datasets/nvidia/HelpSteer2)
- [nvidia/Daring-Anteater](https://huggingface.co/datasets/nvidia/Daring-Anteater)
- [openchat/openchat_sharegpt4_dataset](https://huggingface.co/datasets/openchat/openchat_sharegpt4_dataset)
- [icybee/share_gpt_90k_v1](https://huggingface.co/datasets/icybee/share_gpt_90k_v1)
- [RyokoAI/ShareGPT52K](https://huggingface.co/datasets/RyokoAI/ShareGPT52K)
- [pacovaldez/stackoverflow-questions](https://huggingface.co/datasets/pacovaldez/stackoverflow-questions)
- [HuggingFaceH4/stack-exchange-preferences](https://huggingface.co/datasets/HuggingFaceH4/stack-exchange-preferences)
- [silicone benchmark](https://huggingface.co/datasets/silicone)
- [syncora/customer_support_conversations_dataset](https://huggingface.co/datasets/syncora/customer_support_conversations_dataset)
- [TUNA paper](https://arxiv.org/html/2510.06124v2)
- [Nature Health Study (hierarchical 12-intent)](https://www.nature.com/articles/s44360-026-00117-x)
- [WorkBench paper](https://arxiv.org/html/2405.00823v2)
- [CodeAssistBench paper](https://arxiv.org/html/2507.10646v5)
- [Microsoft CodeXGLUE](https://github.com/microsoft/CodeXGLUE)
- [Topical-Chat repo](https://github.com/alexa/Topical-Chat)
- [Action-Based Conversations Dataset (ABCD)](https://www.researchgate.net/publication/350625584_Action-Based_Conversations_Dataset_A_Corpus_for_Building_More_In-Depth_Task-Oriented_Dialogue_Systems)
- [Hierarchical text classification review (MDPI)](https://www.mdpi.com/2079-9292/13/7/1199)
- [DeepPavlov Topics paper](https://link.springer.com/chapter/10.1007/978-3-031-19032-2_39)
