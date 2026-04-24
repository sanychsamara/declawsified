# Manager Report — AI Usage Analysis

**Subject:** Personal AI account holder (ChatGPT + Claude.ai exports)
**Period:** 2023-03-18 to 2026-04-13 (447 active days, 38 months)
**Total interactions:** 2,603 user prompts across 649 conversations
**Classifier:** declawsified-core, no-LLM mode (rule-based + KeywordTagger + EmbeddingTagger over hybrid-v2 taxonomy)
**Pass-2 corrections:** 212 arcs revised, 1,239 facet updates

---

## TL;DR

This is a **personal-account user**, not a corporate one — so the typical work-vs-personal cost-leakage signal isn't applicable. But classification still surfaces useful patterns:

1. **Sports dominates by a wide margin.** 486 sports-tagged messages, 59 sports-dominant sessions, the 4 longest single-topic sessions (≥51 msgs each) are all NBA roleplay/analysis. This is a **major time investment** in fantasy sports content generation.
2. **Roleplay/character-building consumes the longest sessions.** Top session is 218 messages of Beyblade character creation. Sessions like Naruto character building (91), NBA career simulation (47), basketball shot form (64) suggest deep multi-turn creative writing.
3. **Some real work signal exists.** 222 engineering-tagged messages, 66 sessions where engineering is the dominant tag. Topics include: transformer training, data pipelines, code generation, classifier work.
4. **Activity timing skews late-night.** Heaviest hours are 04:00-06:00 UTC and 22:00-23:00 UTC. Sunday is by far the busiest day (639 msgs; weekday avg ~310). Pattern fits "evening hobby user" not "9-to-5 work user."
5. **Sensitive-content flags fired 27 times** across 12 sessions — mostly contract review ("are these terms fair"), PII discussions, and one chat about firing/job loss. Worth a glance for compliance.
6. **Volume spike March-April 2025** (795 messages, 31% of total in 2 months). Coincides with project bursts elsewhere or unusual life event.

---

## 1. What the user actually does with AI

### Sessions by dominant topic (n = 649)

| Bucket | Sessions | % |
|---|---:|---:|
| **Untagged** (greetings, very short prompts) | 334 | 51% |
| **Personal-other** (life, advice, miscellaneous) | 108 | 17% |
| **Other specific tags** (entertainment, learning, etc.) | 81 | 12% |
| **Work-tech** (engineering, devops, data) | 66 | 10% |
| **Sports** (NBA dominant) | 59 | 9% |
| **Sensitive** | 1 | <1% |

### Top tags by message volume

| Tag | Messages | Notes |
|---|---:|---|
| sports | 486 | NBA-heavy: drafts, careers, shot form |
| personal | 474 | Catch-all life topics |
| non-work | 256 | Entertainment, hobbies |
| engineering | 222 | Code, ML, systems |
| basketball | 32 | Specific to basketball |
| sensitive | 27 | Mostly contracts, PII, job loss |
| stress | 15 | Mental health conversations |
| entrepreneurship | 14 | Business ideation |
| privacy | 14 | Data privacy questions |

### Top-10 longest sessions (all single-purpose creative deep-dives)

| Session | Msgs | Type | First prompt |
|---|---:|---|---|
| 67eda879 | **218** | Personal/roleplay | "Can you come up with a beyblade character" |
| 67df66e5 | 114 | NBA roleplay | "I'm gonna tell you 2 college players..." |
| 67d8f4e9 | 95 | Mixed personal/sports | "so my old chat was starting to take really long" |
| 66e4e672 | 91 | Naruto roleplay | "create a character from Naruto" |
| 67ec7791 | 78 | Mixed mechanical Q&A | "I have a mechanical question" |
| be023f08 | 77 | Sports-only | "Did you see tjat" |
| 677c916a | 64 | Basketball coaching | "describing perfect shot form for basketball" |
| 7cbd8787 | 51 | NBA simulation | "rebuilding the 2019-2020 knicks" |
| e43503b3 | 47 | NBA career roleplay | "Were gonna build a nba career" |
| 68ef306b | 40 | Engineering | "how batch size affects transformer training" |

**Insight:** Of the top 10 longest sessions, **9 are personal (sports/roleplay), 1 is engineering** (transformer training). The transformer session is materially shorter than the sports ones.

---

## 2. Productivity signals

### Time-of-day pattern (UTC)

```
hr   work  personal
04     28       124       ← evening burst
05     19       212       ← peak personal hour
22     24        47       ← second evening burst
23     19        75
01     27        85       ← late night

09-12   0         0       ← daytime gap (asleep/working)
```

The user is **active outside typical work hours**. Morning UTC (US evening) and late evening UTC (US morning hours) are heaviest. Daytime UTC (US morning workday) sees almost no AI activity. This is consistent with someone using AI for personal interest in evenings.

### Day-of-week distribution

| Day | Messages |
|---|---:|
| Sun | **639** ← spike |
| Wed | 414 |
| Tue | 333 |
| Mon | 328 |
| Sat | 311 |
| Thu | 291 |
| Fri | 287 |

Sunday is 2× the weekday average. Strong weekend hobby-time signal.

### Volume timeline (last 24 months)

```
2024-07: 240 ###########################
2024-08: 107 ############
2024-09: 149 #################
2025-03: 360 #########################################
2025-04: 435 ##################################################  ← peak
2025-05:  53 ######
2025-09:  79 #########
2025-10:  91 ##########
```

**Anomaly:** March-April 2025 saw 795 messages combined — 31% of all activity in 2 of 38 months. After the peak, volume dropped to ~50/month for several months. Worth investigating: a project, a life event, or the user discovering a new use case.

---

## 3. Concerning signals

### Sensitive content (12 sessions, 27 flagged messages)

Sample:
- "are these terms and conditions fair" (legal review of vendor T&Cs)
- "Goal: Use Input text below to generate 3 ideas for a software business" (potential confidential idea generation)
- "Read this article and tell me if 'motivated attack..." (security/privacy content)
- "list of asset types generate class definitions" (work-related code with possibly proprietary names)
- PII-related queries ("PII features", "table from the query")

**Recommendation:** None of these are clearly policy violations on a personal account, but if this user later joins an organization with an AI-use policy, the sensitive flag should be elevated.

### Stress signal (15 messages, 1 long session)

Single coherent session about feeling "stressed and overwhelmed", AI tools affecting career outlook, mindfulness reading (Eckhart Tolle, Sam Harris). Pattern fits **personal mental-health support use**, not a corporate concern.

### Mixed work + personal sessions (55 sessions)

Sessions where engineering tags coexist with sports/personal tags. Examples:
- `66e4e672`: Naruto roleplay + martial-arts + memorization + swimming + engineering (rare engineering co-mention)
- `66fe40d8`: Anime + fitness + weightlifting + engineering

Most appear to be **personal sessions where engineering was incidentally mentioned**, not work-leakage. False positive rate on this signal looks high.

---

## 4. What the data CAN'T tell us (and why)

The classifier ran in **export-data mode** — it had no access to:
- `working_directory` → context defaulted to "business" for all 2,603 messages (meaningless on personal accounts)
- `git_context` → activity defaulted to "investigating" for all messages (no real signal)
- `tool_calls` → can't infer build/debug/test ratios

**Tags from message text are the ONLY high-fidelity signal** in this analysis. If we wanted true productivity attribution, the proxy needs to run live on the user's terminal/IDE to capture git/workdir/tool signals — which is exactly what `declawsified-proxy` does for Claude Code.

---

## 5. Manager-level recommendations (if this were a corporate user)

Hypothetically, if this same usage pattern came from someone using AI on a company account:

1. **Cost attribution:** ~85% of message volume is personal/non-work topics. If this were on company tokens, that's a clear policy/cost issue.
2. **Time-of-day:** Late-night/weekend usage is fine for a personal account but would be unusual for routine work — not a flag, just a context note.
3. **Sensitive content:** 12 sessions with sensitive flags would warrant a brief compliance check, especially the contract-review and PII items.
4. **Volume spike (Mar-Apr 2025):** Worth a 1-on-1 to understand — could be a high-value project burst or a personal stress period.
5. **Engineering work output:** The transformer training session (40 msgs) and a few data engineering / ML conversations look like **legitimate work product**. Tag those messages, attribute to the relevant project.

---

## 6. What to improve in the classifier

Observations from running this end-to-end:

1. **Add an explicit "roleplay" tag.** The longest sessions are all character/career roleplay — currently catch-all "personal". A dedicated tag would surface them faster.
2. **Add a "creative-writing-collab" tag.** Multi-turn Naruto/Beyblade/NBA-career sessions look the same structurally — long, generative, hobby. One tag name covers the pattern.
3. **The `personal` tag is too broad.** It fires on too many things. Consider splitting into `personal-life`, `personal-creative`, `personal-research`.
4. **`engineering` over-fires.** "I have a mechanical question" got tagged engineering despite being non-software. The keyword set needs disambiguation.
5. **Add session-level rollup tags.** A session with 90% sports messages should get a session-level `sports-roleplay` tag. Currently each message classifies independently.
6. **The `untagged` rate is 51%.** Half of sessions have no tags after pass-2 — usually because they're 1-message greetings or very short. Worth a separate "trivial" or "noise" classification.
