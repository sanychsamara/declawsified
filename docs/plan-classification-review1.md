# Classification Turnaround Review 1

**Date:** 2026-04-22  
**Revision:** 4, after Context facet simplification  
**Inputs reviewed:** `docs/plan.md`, `docs/plan-classification.md`, `docs/status-classification.md`, current implementation under `sources/declawsified-core/`, and product-positioning feedback.

## Executive Summary

The admin-facing model should be as simple as possible:

- **Project**: company initiative/repo/cost bucket, discovered from high-trust non-semantic signals.
- **Activity**: what kind of work happened.
- **Context**: existing Business/Personal facet.
- **Tags**: flexible semantic and risk clues.

Do **not** add a separate `Usage` facet. Do **not** split project into multiple project-like facets. Do **not** expose a deep semantic taxonomy as the management filter model.

The product can still catch basketball research during work hours:

```text
Project: auth-service or Unassigned
Activity: Research
Context: Business
Tags: personal, sports, basketball, non-work
```

The inefficiency insight is derived from the combination:

```text
Context = Business
Tags include personal/non-work/basketball
Time = work hours
Cost = material
```

That is simpler than a `Usage` facet and reuses the existing `Context` concept.

## Product UX Principle

Declawsified should feel like the iPhone of AI cost observability: obvious filters, simple labels, and powerful defaults.

Main admin filters:

- Time
- Team/User
- Project
- Activity
- Context
- Tags

Admins should not need to learn classifier internals. They should be able to answer:

- "How much Business-context spend was tagged personal last week?"
- "Which projects have the most non-work tags?"
- "Which teams spend the most on research?"
- "Which projects have retry-loop or waste tags?"
- "Which users are creating sensitive-topic spend?"

## Corrected Object Model

## 1. Project

Project remains a stable company attribution field.

Project should be discovered from high-trust, mostly non-LLM signals:

- explicit project tags
- LiteLLM team/key/customer mapping
- repo name
- working directory
- branch name and ticket references
- artifact paths
- session continuity
- admin-defined aliases

Project should **not** be assigned from broad semantic topic inference.

Example:

- Prompt: "Compare LeBron and Jokic playoff stats"
- Workdir: `C:\Users\alex\work\auth-service`
- Project: `auth-service` if metadata policy allows current repo attribution, otherwise `Unassigned`
- Context: `Business`
- Activity: `Research`
- Tags: `personal`, `sports`, `basketball`, `non-work`

This keeps project reporting trustworthy and makes mismatch analysis easy: "why does `auth-service` contain spend tagged `basketball`?"

## 2. Activity

Activity remains a small closed set:

- debugging
- feature development
- refactoring
- testing
- research
- planning
- documentation
- devops/configuration
- review
- coordination

Classify Activity with rules, lightweight ML, and optional tiny LLM fallback only when confidence is low.

## 3. Context

Context should stay the existing simple facet:

- `Business`
- `Personal`

Do not overload Context with values like `Sensitive`, `Waste`, or `Approved work`. Those are not context; they are semantic/risk tags or derived dashboard views.

Context signals:

- account/workspace type
- team/org metadata
- workdir roots
- user profile settings
- explicit tags or config
- time/account policy only as supporting signal, not as the whole classification

Examples:

- Work account + company repo -> `Business`
- Personal account + home directory -> `Personal`
- Company account + basketball prompt -> still likely `Business` context with `personal`, `sports`, `basketball`, `non-work` tags

That last distinction matters: the inefficiency is visible because personal semantic tags appear inside Business context.

## 4. Tags

Tags carry semantic meaning, risk clues, and inefficiency signals.

Example semantic tags:

- `personal`
- `non-work`
- `sports`
- `basketball`
- `travel`
- `shopping`
- `medical`
- `legal-personal`
- `personal-finance`
- `interview-prep`
- `auth`
- `database`
- `security`
- `ci-cd`

Example efficiency/risk tags:

- `retry-loop`
- `low-output`
- `excessive-context`
- `sensitive`
- `regulated`
- `policy-review`
- `unassigned-project`
- `project-tag-mismatch`

Tags can have hierarchy internally for rollups, but the UI should show them as simple chips and filters.

## Why Tags, Not Usage

Dropping `Usage` keeps the product simpler. Most "usage" insights are actually derived views over existing fields:

- Business context + `personal` tag -> personal spend on company resources
- Business context + `sensitive` tag -> sensitive-topic review
- Project + `retry-loop` tag -> waste pattern
- Project + `basketball` tag -> project/tag mismatch
- Activity = Research + no artifact output + high cost -> possible low-value research

This gives admins simple filters without introducing another abstract facet.

## Revised Classification Pipeline

## Stage 0: Feature Builder

Extract cheap signals:

- account/team/user
- account context hints
- repo/workdir/branch/ticket
- artifact paths and file extensions
- tool names and command patterns
- prompt text sketch
- named entities and keywords
- token cost, retries, latency, cache misses

## Stage 1: Project Classifier

Use only high-trust non-semantic sources:

1. explicit `project` tag or admin mapping
2. LiteLLM team/key/customer metadata
3. repo name
4. branch ticket
5. artifact path or workdir
6. session continuity
7. `Unassigned`

Semantic inference should produce tags, not project labels.

## Stage 2: Context Classifier

Classify only:

- `Business`
- `Personal`

Use:

- account/workspace metadata
- org/team mapping
- configured workdir roots
- explicit context tags
- session continuity

Do not classify policy outcomes here.

## Stage 3: Activity Classifier

Use:

- branch prefixes
- tool patterns
- file paths
- keywords
- TF-IDF/logistic regression or fastText
- optional tiny LLM fallback for low-confidence cases

Target:

- 85-90% accuracy
- no hosted LLM for most calls

## Stage 4: Semantic and Risk Tagger

Generate tags through a cascade:

1. admin-defined tag dictionaries
2. keyword and phrase matches
3. named entity extraction
4. local embedding nearest-neighbor over tag definitions
5. session tag carry-forward
6. optional one-shot small LLM only for high-cost or policy-relevant uncertain calls

The tagger should support broad and specific tags together:

```json
["personal", "non-work", "sports", "basketball"]
```

If a specific tag is unknown, fall back gracefully:

```json
["personal", "non-work", "sports", "entity:curling"]
```

This preserves basketball/curling detection without online tree walking.

## Stage 5: Derived Insights and Aggregation

Do not add another facet. Compute dashboard insights from combinations:

- `Business` context + `personal` or `non-work` tags -> personal spend on business resources
- `Business` context + `sensitive` tag -> sensitive-topic review
- Project + `basketball` tag -> project/tag mismatch
- Project + `retry-loop` tag -> waste pattern
- high-cost research + no artifact output -> possible low-value exploration
- repeated unassigned project spend -> project discovery/config issue

Surface patterns, not noisy per-call policing.

## What To Do With The Existing Tree Taxonomy

Do not expose the 2,000-node tree as the admin model.

Use it as:

- an internal source for tag definitions
- aliases and descriptions
- an embedding corpus for tag suggestions
- an offline enrichment tool
- a rollup map from specific tags to broad tags

Do not use it as:

- online LLM tree walk
- project hierarchy
- management filter hierarchy

Recommended conversion:

```yaml
tag: basketball
parents: [sports, personal, non-work]
aliases: [nba, lebron, jokic, playoffs, hoops]
context_interpretation:
  business: suspicious_personal_spend
  personal: normal_personal_topic
```

## LLM Strategy

Use LLMs only as fallback, never as multi-step taxonomy walkers.

Good LLM use:

- one-shot tag selection from a shortlist
- strict JSON for ambiguous high-cost calls
- offline tag dictionary expansion
- evaluation-set labeling

Bad LLM use:

- beam-walking a deep taxonomy per call
- choosing project from open-ended semantics
- classifying every call with a hosted model

Models to benchmark:

- `GPT-4.1-nano`: strict JSON tag selection.
- `Gemini Flash Lite`: cheap hosted fallback.
- `GPT-4.1-mini`: quality ceiling.
- local `Qwen 2.5 3B/7B Instruct`: privacy/local fallback.
- local `Llama 3.2 3B Instruct`: shortlist tag selection baseline.

Benchmark them on:

- top-20 tag shortlist selection
- personal/non-work tag recall
- sensitive-topic tag recall
- JSON reliability

## Admin Dashboard Shape

### Main Filters

- Time
- Team/User
- Project
- Activity
- Context
- Tags

### Main Views

- Spend by Project
- Spend by Activity
- Spend by Context
- Business Spend with Personal Tags
- Sensitive Tags
- Waste / Retry Tags
- Unassigned Spend
- Top Tags

### Example Admin Questions

- "How much Business-context spend had personal tags last week?"
- "Which projects have the most unassigned spend?"
- "Which users spent the most on non-work topics?"
- "Which projects are burning tokens on retry loops?"
- "What tags are appearing inside `auth-service`?"

## Cost and Performance Targets

Online path:

- Project classification: <5ms
- Context classification: <5ms
- Activity classification: <10ms
- Semantic/risk tagging without LLM: <20ms
- Full no-LLM classification: <40ms
- LLM fallback: <5-10% of calls
- Average classification cost: <= $0.00005-$0.0002/call

Quality targets:

- Project precision: very high; prefer `Unassigned` over hallucinated project.
- Context accuracy: very high when account/workdir metadata exists.
- Activity accuracy: >=85%.
- Personal/non-work tag recall: high.
- Sensitive-topic tag recall: high and conservative.
- Alert precision: high after aggregation.

## Experiments To Run Next

1. **Project purity test**
   - Disable semantic taxonomy project assignment.
   - Measure project attribution from repo/team/workdir/session only.
   - Track unassigned rate and false project assignment rate.

2. **Context preservation test**
   - Verify company-account personal-topic prompts remain `Context=Business` and receive personal/non-work tags.
   - Verify personal-account work-like prompts can be `Context=Personal` with work-like tags.

3. **Semantic tag benchmark**
   - Build prompts for basketball, travel, shopping, health, legal-personal, personal finance, interview prep, and approved work.
   - Measure tag precision/recall with no LLM, local embeddings, and optional LLM fallback.

4. **Admin filter usability test**
   - Mock dashboard filters: Project, Activity, Context, Tags.
   - Confirm admins can answer key spend questions without understanding classifier internals.

5. **Tree-to-tags conversion**
   - Convert taxonomy leaves/ancestors into tag dictionary entries.
   - Add aliases for high-risk personal categories.
   - Evaluate top-K tag retrieval.

6. **LLM fallback ablation**
   - Compare no LLM vs one-shot small LLM on only uncertain/high-cost cases.
   - Measure cost reduction and incremental accuracy.

## Revised 3-Phase Recovery Plan

## Phase 1: Simplify the Product Model

Time: 3-5 days

- freeze admin-facing facets to `Project`, `Activity`, `Context`, `Tags`
- keep Context strictly Business/Personal
- remove `Usage` from the plan
- make Project metadata-only and high precision
- add semantic/risk tag output

Deliverable:

- a product model admins can understand immediately.

## Phase 2: Replace Tree Walk With Tagging

Time: 1-2 weeks

- convert taxonomy nodes into tag definitions
- build local tag embedding index
- add keyword/entity tagger
- add session tag cache
- add one-shot tag shortlist fallback for high-value uncertain calls

Deliverable:

- detects basketball/personal topics without slow tree walking.

## Phase 3: Build Inefficiency Detection From Existing Fields

Time: 1-2 weeks

- aggregate `Context + Tags + Project + Activity + Cost`
- detect Business-context personal-tag spend
- detect retry loops and waste tags
- surface simple admin dashboard views
- add active learning from admin corrections

Deliverable:

- token inefficiencies are identified with simple filters, without adding a `Usage` facet.

## Bottom Line

Keep the public model to four simple concepts:

- `Project`: stable, metadata-derived company attribution.
- `Activity`: small work-type set.
- `Context`: existing Business/Personal facet only.
- `Tags`: flexible semantic, risk, and inefficiency clues.

Basketball research during work hours becomes:

```text
Project: Unassigned or current metadata project
Activity: Research
Context: Business
Tags: personal, non-work, sports, basketball
```

This is simple, filterable, management-friendly, and does not require slow LLM tree walking or a new `Usage` facet.
