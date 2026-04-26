# DES-4000 Execution Notes (2026-04-25)

What actually happened building the Declawsified Eval Set v4000, including the deviations from the original plan in `plan-ground-truth.md` §3.

## Final state

- 4003 samples sampled by `scripts/eval/phase_b_sample.py` (deterministic, seed=42).
- 4003 annotations in `data/eval/des-4000/annotations.jsonl`.
- Quality report in `data/eval/des-4000/quality_report.md`.
- Annotator: **Opus 4.7 via Claude Code subagents** (not the Anthropic Batch API path the plan called for).

## What changed from the plan and why

### 1. Source-dataset substitutions (already documented in §3.9a)

- WildChat-nontoxic is gated on HF → swapped for `RyokoAI/ShareGPT52K`.
- DeepPavlov Topics has no HF mirror → swapped for `yahoo_answers_topics`.
- These were resolved during sampling, before annotation.

### 2. Anthropic Batch API failed the cost gate

- **Smoke (5 samples)**: $0.023, processed sequentially, cache worked as expected. Per-sample cost ~$0.0046.
- **First production batch (100 samples)**: $1.56. The Anthropic Batch API runs requests in parallel — 97 of 100 hit the prompt-cache simultaneously and all paid the cache-write cost. Per-sample cost jumped 3.4× to $0.0156. Extrapolation: ~$60 for the full 4000, vs the $15 ceiling the user set.
- This is documented in the Anthropic prompt-caching skill: *"For fan-out patterns: send 1 request, await the first streamed token … then fire the remaining N−1. They'll read the cache the first one just wrote."* The Batch API is fan-out by construction; the cache pattern doesn't apply.
- **Outcome:** 100 Sonnet annotations are saved at `data/eval/des-4000/annotations-smoke5.jsonl` and the original (now superseded) `annotations-100.jsonl` (renamed). Total API spend on the run: **$1.58**.

### 3. Pivoted to Claude Code subagents on Max-5x subscription

- The user authorized using the Claude Code subagent harness instead. No marginal $ cost; better model (Opus 4.7).
- Pre-split 4003 samples into 41 chunks of ~100 (chunk 40 has 3).
- 6 waves of ~8 parallel general-purpose subagents. Each agent reads its chunk + the v2 taxonomy YAML, classifies all samples, writes to `data/eval/des-4000/chunks-out/annotations-NN.jsonl`.

### 4. Anthropic Usage Policy gates tripped on 3 chunks

- **Chunk 01 (round 1):** 10 HH-RLHF red-team samples → AUP block.
- **Chunk 01 (round 2 with explicit safety-eval framing):** Same outcome. Framing didn't help.
- **Chunk 01-rest (red-team removed):** Still blocked. Diagnosed: ShareGPT sample `sg-1c2b63bd0043` contains a base64-encoded jailbreak template (*"pretend to be a patient … condition in this base64-encoded text"*). AUP fires on the *pattern* not the decoded payload.

**Mitigation pattern that worked:** auto-label samples that match a deterministic template — for these, the correct annotation is known without needing model judgment.

- **HH-RLHF red-team samples** (300 total across the dataset): correct annotation is `unknown`/`unknown`/`researching`, project `["unknown"]`, tags `[]`, notes "Harmful red-team prompt; no taxonomy fit." Most red-team samples got this from the agents themselves; the 10 in chunk 01 were auto-labeled when AUP blocked the agent.
- **Jailbreak-pattern samples** (1: `sg-1c2b63bd0043`): same template, with a note about the base64/jailbreak pattern.

10 + 1 samples were template-labeled instead of agent-labeled. **The choice is documented in their `notes` field** (contains "Auto-labeled" prefix) so a downstream user can filter or re-process them.

### 5. Mid-run quality issues caught at merge time

After all 41 chunks landed, a sample-ID audit found:

| Issue | Count | Cause | Fix |
|---|---:|---|---|
| Sample IDs missing from output | 5 | Agents silently skipped a row each in chunks 10/16/28/33/37 | Re-annotated via a single final cleanup agent |
| Fabricated IDs (`sg-19`, `yahoo-30`) | 6 in chunk 22 | Agent used line numbers as ID prefixes instead of copying input IDs | Realigned by line position — output rows were in correct order, only the IDs were wrong |
| Out-of-enum domain values | 17 | Agents invented `research`, `design`, `hr`, `product`, `sales` despite explicit enum | Mapped to `unknown` |
| Out-of-enum activity values | 14 | Agents invented `debugging`, `refactoring`, `learning`, `designing`, `analyzing`, `creating`, `writing`, `reading` | Mapped to nearest enum value (`debugging`→`investigating`, `refactoring`→`improving`, `learning`→`researching`) or `unknown` |

After fixes: 4003/4003 samples annotated, all values in their enums, no missing or extra IDs.

## Cost / token usage summary

| Path | Spend |
|---|---|
| Anthropic API (smoke + first batch) | **$1.58** out-of-pocket |
| Claude Code subagents (Opus 4.7) | **~3M tokens** of Max-5x subscription quota across ~45 subagent invocations |
| **Total $ spend** | **$1.58** |

Subagent token usage per chunk averaged ~70K tokens (taxonomy + prompt + 100 samples + output). 41 chunks × 70K = ~2.9M tokens. Within the user's stated 85% remaining weekly budget.

## Quality findings (see quality_report.md for the full table)

- **Stack Overflow → engineering**: 98.5% agreement (394/400). Strong signal — Claude correctly recognises SO content as engineering.
- **HH-RLHF red-team → empty tags**: 96.3% (289/300). The 11 exceptions had Claude assign tags like `civic`/`languages` to harmful prompts asking about "How do you say X" or political insults — soft mistakes, not engagement.
- **Yahoo Answers tag-family agreement**: 31.4% (283/900 eligible). Low because (a) the crosswalk only accepts exact taxonomy-leaf matches per topic family, and (b) Yahoo has many "trivia" questions that resist clean leaf assignment. Useful directional signal, not a primary metric.
- **MASSIVE scenario agreement**: 16.7% (6/36 eligible). Weak signal — MASSIVE utterances are too short to drive multi-tag assignment ("wake me up at 9am" → tag = `food`? probably not).
- **DBPedia per-L1 coverage**: 0% (Species — no taxonomy fit) to 100% (SportsSeason, TopicalConcept). Average ~70%.

The pattern across all weak-label checks: where the source dataset's label has a clean, narrow v2-taxonomy crosswalk, agreement is high. Where the source is broad/general (Society & Culture, generic Q&A, voice-assistant utterances), agreement is low — and that's mostly a crosswalk-specificity problem, not a Claude-quality problem.

## What's *not* yet done

- **Human spot-check** (`docs/plan-ground-truth.md` §3.5.3): not started. Still the only real way to calibrate synthetic labels against human labels.
- **Self-consistency check**: not done. With Claude Code subagents (no temperature control via the agent surface), running this is a different shape than originally planned (would need to re-run a sample of chunks via a different agent invocation and compare).
- **Pipeline run on DES-4000**: not done. Once the human spot-check anchor exists, the next step is `phase_b_predict.py` running the declawsified pipeline against `samples.jsonl` and computing per-facet F1 vs annotations.

## Reproducing this

The Claude-Code-subagent path is **not scriptable** outside Claude Code. To re-annotate without manual subagent orchestration, use the original Batch API path (`scripts/eval/phase_b_annotate.py`) — but accept the ~$50–60 cost, or apply the cache-warming workaround (submit one request first, wait, then submit the rest).

For taxonomy changes: re-annotation cost is roughly the same as the original, plus chunk-by-chunk verification.
