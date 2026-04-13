# Declawsified Domain Packs

**Scope:** Definitions of the industry-specific domain packs (engineering, legal, marketing, research, finance, personal/education) and the pack auto-detection / activation mechanism. Packs refine the `activity` facet with domain-specific sub-activities on top of the universal 10-activity taxonomy.

**Companion doc:** [`plan-classification.md`](./plan-classification.md) -- classification design this is part of; defines the facet schema, context detection, project discovery, and in-prompt commands that packs plug into.

---

## Table of Contents

1. [Domain-Specific Activity Taxonomies (Industry Packs)](#1-domain-specific-activity-taxonomies-industry-packs)
   - [Why Domain Packs?](#why-domain-packs)
   - [Pack: Software Engineering](#pack-software-engineering)
   - [Pack: Legal](#pack-legal)
   - [Pack: Marketing](#pack-marketing)
   - [Pack: Research / Academic](#pack-research--academic)
   - [Pack: Finance / Accounting](#pack-finance--accounting)
   - [Pack: Personal / Education](#pack-personal--education)
   - [Pack Auto-Detection](#pack-auto-detection-finding-the-right-pack-without-configuration)

---

## 1. Domain-Specific Activity Taxonomies (Industry Packs)

The 10 universal activities cover the cross-domain view. But within specific domains, finer-grained activity taxonomies already exist and have been battle-tested in production for decades. Declawsified should ship with **pre-built taxonomy packs** that layer domain-specific subcategories onto the universal activities.

### Why Domain Packs?

When Meta's legal team uses the tool, they don't want "investigating" -- they want the UTBMS codes they already use for billing. When Google's engineering team uses it, they want Conventional Commits categories. The universal taxonomy is the common language; domain packs are the local dialects.

**Architecture**: Domain packs are optional overlays. The universal 10-activity taxonomy always runs. When a domain pack is active for a team, it adds a second-level classification within the detected activity.

```
Universal:  activity=investigating
  +
Legal pack: legal_activity=L300:discovery, legal_task=A102:research
  =
Tags: auto:activity:investigating, auto:legal:L300, auto:legal_task:A102
```

### Pack: Software Engineering

Based on Conventional Commits (community standard, 10 types), Jellyfish categories, and GitClear/Pluralsight Flow classification.

| Activity | Engineering Sub-Activities |
|----------|--------------------------|
| `investigating` | error-tracing, performance-profiling, log-analysis, root-cause-analysis |
| `building` | feature-implementation, api-development, ui-development, data-modeling |
| `improving` | refactoring, performance-optimization, code-cleanup, dependency-update |
| `verifying` | unit-testing, integration-testing, e2e-testing, manual-testing |
| `researching` | architecture-research, library-evaluation, spike, code-reading |
| `configuring` | ci-cd, docker, kubernetes, terraform, monitoring-setup |
| `reviewing` | code-review, pr-review, design-review, architecture-review |
| `planning` | sprint-planning, architecture-design, technical-spec, estimation |
| `communicating` | documentation, changelog, adr, api-docs |
| `coordinating` | standup, retro, cross-team-sync, incident-response |

**Signal mapping**: Uses Conventional Commits prefixes (`feat`->`building`, `fix`->`investigating`, `refactor`->`improving`, `test`->`verifying`, `docs`->`communicating`, `ci`->`configuring`, `chore`->`configuring`).

### Pack: Legal

Based on UTBMS/LEDES codes -- the industry standard for legal billing used by thousands of law firms for 25+ years.

| Activity | Legal Sub-Activities (UTBMS mapped) |
|----------|-------------------------------------|
| `investigating` | fact-gathering (C100), witness-interviews, evidence-review |
| `building` | brief-drafting (A103), contract-drafting, motion-preparation |
| `improving` | contract-redlining, brief-revision, document-amendment |
| `verifying` | cite-checking, conflict-checking, compliance-review, privilege-review (A124) |
| `researching` | legal-research (C200/A102), case-law-analysis, regulatory-analysis |
| `planning` | case-strategy (L120), litigation-planning, transaction-structuring (P300) |
| `communicating` | client-communication (A106), opposing-counsel-comm (A107), court-filing |
| `configuring` | e-discovery-setup (L600), document-management (A110), database-config |
| `reviewing` | document-review (A104/A121), deposition-review, discovery-review (L300) |
| `coordinating` | case-management (L100), project-management (A127), team-coordination (A105) |

### Pack: Marketing

Based on standard agency service categories and marketing taxonomy frameworks (Improvado, HubSpot).

| Activity | Marketing Sub-Activities |
|----------|--------------------------|
| `investigating` | competitive-analysis, audience-research, analytics-review |
| `building` | content-creation, campaign-building, ad-creative, landing-pages |
| `improving` | a-b-testing-analysis, copy-optimization, conversion-optimization |
| `verifying` | brand-consistency-check, compliance-review, link-checking |
| `researching` | market-research, keyword-research, trend-analysis, customer-research |
| `planning` | campaign-planning, content-calendar, media-planning, budget-planning |
| `communicating` | social-media, email-marketing, press-release, partner-outreach |
| `configuring` | analytics-setup, tag-management, crm-integration, automation-setup |
| `reviewing` | creative-review, performance-review, report-generation |
| `coordinating` | agency-coordination, stakeholder-alignment, cross-channel-sync |

### Pack: Research / Academic

Based on NSF/OECD R&D classification and standard academic work categories.

| Activity | Research Sub-Activities |
|----------|------------------------|
| `investigating` | hypothesis-testing, experimental-debugging, data-validation |
| `building` | experiment-design, model-building, simulation-development, prototype |
| `improving` | model-refinement, method-optimization, calibration |
| `verifying` | statistical-validation, reproducibility-check, peer-review-response |
| `researching` | literature-review, prior-art-search, data-collection, survey-design |
| `planning` | study-design, grant-writing, research-proposal, methodology-selection |
| `communicating` | paper-writing, poster-preparation, presentation, conference-prep |
| `configuring` | lab-setup, compute-infrastructure, data-pipeline, tool-installation |
| `reviewing` | peer-review, manuscript-review, data-review, methods-review |
| `coordinating` | collaboration-management, multi-site-coordination, irb-coordination |

### Pack: Finance / Accounting

Based on Big 4 service categories and standard accounting workflow.

| Activity | Finance Sub-Activities |
|----------|------------------------|
| `investigating` | variance-analysis, discrepancy-investigation, fraud-analysis |
| `building` | financial-modeling, forecast-building, report-creation, budget-draft |
| `improving` | model-refinement, process-improvement, reconciliation-cleanup |
| `verifying` | audit-testing, reconciliation, control-testing, compliance-check |
| `researching` | tax-research, regulatory-research, benchmark-analysis, market-data |
| `planning` | budget-planning, tax-planning, audit-planning, year-end-planning |
| `communicating` | client-advisory, management-letter, investor-reporting |
| `configuring` | erp-setup, reporting-tool-config, integration-setup |
| `reviewing` | financial-review, tax-review, audit-review, disclosure-review |
| `coordinating` | engagement-management, multi-entity-coordination, external-audit-support |

### Pack: Personal / Education

**Note on Education vs Personal**: The educational use case (students using AI for coursework) is a specialized subset of personal use. An educational overlay adds sub-activities like `homework`, `exam-prep`, `thesis-work` within the personal pack's areas (primarily `learning`, `career-personal`, `personal-growth`).

For the MVP, the personal pack covers both. A dedicated education pack is post-MVP.

### Pack Auto-Detection: Finding the Right Pack Without Configuration

New users install the plugin and type their first prompt. They haven't configured a profile. They may not even know what a "domain pack" is. The system must **work immediately with zero config** and **suggest the right pack(s) after observing real usage** -- never blocking productivity on setup.

#### Design Goals

1. **Zero-config start**: No pack required. Universal 10-activity taxonomy works for everyone.
2. **Progressive enhancement**: Packs activate as evidence accumulates. Never disrupt active work.
3. **Multi-pack support**: A user can have engineering AND legal active simultaneously (e.g., a tech company's GC who codes). Packs are not mutually exclusive.
4. **Per-project scope**: Packs can be global or scoped to specific projects.
5. **Unobtrusive suggestion**: Ask once, remember the answer, don't nag.

#### Pack Detection Signals

Each pack defines three signal tiers:

| Signal Tier | Weight | Examples |
|-------------|--------|----------|
| **Strong** (weight 1.0) | Unambiguous domain markers | Legal: case citations (`42 U.S.C. § 1983`), `plaintiff`, `indemnification`; Eng: `.py`/`.ts` files, git ops, `pytest` |
| **Medium** (weight 0.5) | Common in domain but not unique | Legal: "contract", "compliance"; Eng: "function", "class", "api" |
| **Weak** (weight 0.2) | Occasional hints | Legal: "client", "review"; Eng: "debug", "deploy" |
| **Exclusion** (weight -0.8) | Actively rules out this pack | Legal: source code files present; Eng: `.docx` with legal boilerplate |

**Per-pack signal inventories**:

```yaml
engineering:
  strong:
    file_extensions: [.py, .ts, .go, .rs, .java, .cpp, .rb, .ex]
    tools: [Bash, Edit, Read, Write, Grep]
    patterns: [git commit, npm install, pytest, docker build]
    vocab: [function, class, variable, repo, branch, pull request, merge]
  medium:
    vocab: [code, api, debug, refactor, deploy, test, build, run]
    file_extensions: [.md, .yaml, .json, .toml]
  weak:
    vocab: [system, service, data, response, error]
  exclusion:
    vocab: [plaintiff, defendant, statute, jurisdiction]  # if dominant -> not eng

legal:
  strong:
    patterns: ['\d+ U\.S\.C\. § \d+', '\d+ F\.\dd \d+', case citations]
    vocab: [plaintiff, defendant, appellant, indemnification, warranty, statute, jurisdiction, pleading, motion, discovery, deposition]
    file_extensions: [.docx with legal terms, contract templates]
  medium:
    vocab: [contract, agreement, clause, compliance, regulation, counsel, attorney, client privilege]
  weak:
    vocab: [review, draft, revise, analyze, research]
  exclusion:
    vocab: [function, class, compile]  # code-heavy context

marketing:
  strong:
    vocab: [CTR, CPA, CPM, ROAS, conversion funnel, impression, engagement rate, landing page, UTM, campaign KPI]
    patterns: [tracking pixels, ad copy, CTA]
  medium:
    vocab: [audience, segment, target, brand, message, creative, channel, campaign, content]
  weak:
    vocab: [review, draft, create, launch]
  exclusion:
    vocab: [compile, stack trace, exception]

research:
  strong:
    vocab: [hypothesis, methodology, p-value, statistical significance, literature review, peer review, citation, abstract, IRB, controlled study]
    patterns: ['p < 0\.0\d', 'n = \d+', DOI references]
    file_extensions: [.tex, .bib, .Rmd, .ipynb with analysis]
  medium:
    vocab: [experiment, study, analysis, findings, results, methods, data]
  weak:
    vocab: [investigate, measure, observe, compare]

finance:
  strong:
    vocab: [P&L, EBITDA, amortization, depreciation, accrual, GAAP, IFRS, variance analysis, reconciliation]
    patterns: ['\$[\d,]+\.\d\d', ledger entries, financial statements]
    file_extensions: [.xlsx with financial models]
  medium:
    vocab: [budget, forecast, revenue, cost, expense, margin, profit, audit]
  weak:
    vocab: [review, analyze, report]

personal:
  strong:
    vocab: [my homework, my resume, personal project, learning to, practicing]
    patterns: [first-person singular dominance, tutorial-following]
  medium:
    vocab: [learn, understand, study, practice, personal]
  weak:
    vocab: [help me, I want to, I'm trying]
  exclusion:
    vocab: [team, organization, client, stakeholder, department]
```

#### Scoring Algorithm

For each call, compute a score per pack:

```python
def compute_pack_score(call: Call, pack: Pack) -> float:
    """
    Returns a score in [-1, +1] indicating pack match strength.
    Positive = pack matches; negative = pack excluded.
    """
    score = 0.0
    signals_found = 0

    # File extensions in tool calls
    for ext in extract_file_extensions(call):
        if ext in pack.strong.file_extensions:
            score += 1.0
            signals_found += 1
        elif ext in pack.medium.file_extensions:
            score += 0.5
            signals_found += 1

    # Vocabulary matches (with TF-IDF weighting to avoid rewarding repetition)
    prompt_terms = tokenize(call.prompt)
    term_counts = Counter(prompt_terms)

    for term in pack.strong.vocab:
        if term in term_counts:
            score += 1.0 * log(1 + term_counts[term])  # Diminishing returns
            signals_found += 1

    for term in pack.medium.vocab:
        if term in term_counts:
            score += 0.5 * log(1 + term_counts[term])
            signals_found += 1

    # Exclusion signals
    for term in pack.exclusion.vocab:
        if term in term_counts:
            score -= 0.8
            signals_found += 1

    # Normalize by signals found (prevents long prompts from dominating)
    if signals_found == 0:
        return 0.0
    return clamp(score / sqrt(signals_found), -1.0, 1.0)
```

#### Activation State Machine

Each pack has three states per scope (global or per-project):

```
INACTIVE  ----(evidence threshold)---->  SUGGESTED  ----(user accepts)---->  ACTIVE
   ^                                         |                                  |
   |                                    (user declines)                    (evidence fades)
   |                                         |                                  |
   +---<------(remembered for 30 days)-------+--<--(signals drop below 0.3)-----+
```

**Thresholds**:

| Transition | Rule |
|-----------|------|
| INACTIVE → SUGGESTED | Rolling average of last 20 calls > 0.7, AND >= 50 total calls observed |
| SUGGESTED → ACTIVE | User accepts suggestion |
| SUGGESTED → INACTIVE (remembered) | User declines; pack won't re-suggest for 30 days |
| ACTIVE → INACTIVE (faded) | Rolling average over last 50 calls < 0.3, AND user hasn't used pack-specific tags in 100 calls |
| Any → ACTIVE (explicit) | User runs `!pack <name>` or sets in config |
| ACTIVE → INACTIVE (explicit) | User runs `!pack off <name>` |

**Why these numbers**:
- 50 calls minimum before suggesting: avoids premature suggestions from a handful of prompts
- 0.7 threshold: strong signal, avoids false positives
- 30-day re-ask cooldown: respects user's "no"
- Never auto-deactivate without very clear signals: a quiet week doesn't mean the pack is wrong

#### Bootstrap Phase (First 50 Calls)

Before enough evidence accumulates, the system runs in **observation mode**:

```
Universal taxonomy only (10 activities, 10 domains, no sub-activities)
+
Signal scoring for all 6 packs (background, no user-facing action)
+
Auto-discovery report accumulating
```

The user sees classifications working immediately (universal taxonomy). The pack-specific refinement is invisible until suggested.

#### Suggestion UX

When a pack crosses the suggestion threshold, the system surfaces it via the out-of-band channel (NOT inline in the LLM prompt):

```
[Declawsified] After 50 calls, I've noticed:
  - 73% of your work matches the engineering pack
  - 18% matches the legal pack

Suggest activating: engineering
Optional secondary: legal (coverage for the 18%)

To accept:
  !pack engineering                   (primary only)
  !pack engineering legal             (both)
  !pack-no-thanks engineering         (don't suggest again for 30 days)
  !pack-auto                          (auto-accept suggestions)
```

**Key principles**:
- The suggestion is a **notification**, not a blocker. Work continues uninterrupted.
- User can respond whenever (next prompt, next week, never).
- Multi-pack acceptance is a first-class option.
- `!pack-auto` mode exists for users who want to trust the system.

#### Multi-Pack Operation

Packs are **additive, not exclusive**. When multiple packs are active, each call is evaluated against each pack's signals:

```
Call arrives with pack signals: eng=0.85, legal=0.12, marketing=0.04
Packs active: engineering, legal

-> engineering pack dominates (0.85 >> 0.12)
-> Apply engineering sub-activity classification
-> Tag: auto:engineering:error-tracing, auto:pack:primary:engineering

Call arrives with pack signals: eng=0.20, legal=0.78, marketing=0.05
Packs active: engineering, legal

-> legal pack dominates
-> Apply legal sub-activity classification (UTBMS mapping)
-> Tag: auto:legal:C200, auto:legal_task:A102, auto:pack:primary:legal

Call arrives with pack signals: eng=0.45, legal=0.48, marketing=0.05
Packs active: engineering, legal

-> Close call; apply BOTH packs
-> Tag: auto:engineering:documentation, auto:legal:C300, auto:pack:primary:mixed
```

**Mixed-pack resolution rule**: If the top two pack scores are within 0.15 of each other, tag with both. This handles cases like engineers writing legal policies or lawyers reviewing code -- where both perspectives are valid.

#### Per-Project Pack Scoping

Packs can be global (user-level) or project-scoped (overrides global for specific projects):

```yaml
# declawsified-config.yaml (user-level)
default_packs:
  - engineering

projects:
  patent-filing-q3:
    packs: [legal, research]   # overrides global; only legal+research active here
    domain: legal

  marketing-website:
    packs: [engineering, marketing]  # both apply

  auth-service:
    packs: [engineering]       # explicit -- no pack drift for this project
```

**Switching semantics**:

```
Call 1: project=auth-service
  -> Active packs for this call: [engineering] (from project config)

Call 2: project=patent-filing-q3
  -> Active packs for this call: [legal, research]

Call 3: project=unknown
  -> Fall back to global default: [engineering]
```

Pack switching is **automatic and invisible** when driven by project detection. The user never sees "pack switching" as a concept -- they just see that their tags become domain-appropriate.

#### Explicit Pack Commands

For power users and edge cases, the in-prompt command layer (§1.12) supports pack control:

| Command | Effect |
|---------|--------|
| `!pack <name>` | Activate pack for this call only (one-shot override) |
| `!pack <a>,<b>` | Activate multiple packs for this call |
| `!pack off` | Disable all packs for this call (universal taxonomy only) |
| `!pack-default <name>` | Set default pack for current project |
| `!pack-default <name> global` | Set global default |
| `!pack-auto on` / `!pack-auto off` | Toggle auto-suggestion acceptance |
| `!pack-list` | Out-of-band: show active packs and their scopes |
| `!pack-no-thanks <name>` | Decline suggestion for 30 days |

**Example: mid-session pack switch**:

```
Prompt 1: "Let me fix this auth bug in the login flow."
  -> detected: project=auth-service, packs=[engineering]
  -> classified: activity=investigating, engineering:error-tracing

Prompt 2: "Now help me draft the privacy policy update for this change. !pack legal"
  -> one-shot override: pack=legal for THIS CALL ONLY
  -> classified: activity=building, legal:contract-drafting
  -> session default remains engineering (next call reverts)

Prompt 3: "Back to code -- add a consent flow in the UI."
  -> packs revert to [engineering] (session default)
```

#### Cold Start Learning Loop

The system learns progressively as calls accumulate:

**Stage 1 (calls 1-50)**: Universal taxonomy only. Observation mode. Pack scores accumulating.

**Stage 2 (calls 50-200)**: First pack suggestion surfaces. User accepts (most common case) or declines. Pack-specific sub-activity classification begins for accepted packs.

**Stage 3 (calls 200-1,000)**: Classifier confusion analysis per pack. User corrections refine pack detection signals. Secondary pack may surface if work is cross-domain.

**Stage 4 (calls 1,000+)**: Pack detection is mature. Cross-customer aggregate data improves baseline (the CrowdStrike flywheel). Signal inventories refined based on real-world term distributions.

#### Project-Level Pack Inference

When a new project is detected (via `!new-project` or auto-discovery), the system makes an initial pack assignment based on the project's first 10 calls:

```python
def infer_project_packs(project: str, first_calls: list[Call]) -> list[str]:
    """
    Run when a new project is detected. Assigns initial packs.
    """
    pack_scores = {pack: mean(compute_pack_score(c, pack) for c in first_calls)
                   for pack in ALL_PACKS}

    # Primary pack: clearly dominant
    primary = max(pack_scores, key=pack_scores.get)
    packs = [primary] if pack_scores[primary] > 0.6 else []

    # Secondary pack: close second
    for pack, score in sorted(pack_scores.items(), key=lambda x: -x[1]):
        if pack == primary:
            continue
        if score > 0.4 and score > pack_scores[primary] - 0.2:
            packs.append(pack)

    # If nothing is confident, fall back to global defaults
    if not packs:
        packs = get_global_default_packs()

    return packs
```

#### Pack Conflicts and Edge Cases

**Conflict: tech company's marketing team uses code blocks in prompts**

```
Marketing manager pastes a code snippet to ask "can we track this on the landing page?"
-> Signal: eng=0.55 (code present), marketing=0.65 (CTA, track, landing page)
-> Both packs fire; project=marketing-website already has packs=[engineering, marketing]
-> Tagged with both; no conflict
```

**Conflict: legal ops engineer works on both contract automation code AND legal review**

```
Sees engineering signals in code-heavy calls, legal signals in review calls
-> Both packs remain active at project level
-> Each call classified by whichever pack dominates THAT call
-> Over time, sub-activity distributions diverge cleanly by call
```

**Conflict: "contract" appears in microservices context**

```
"Define the contract for this API endpoint" -> keyword "contract" triggers legal signal
-> But .py/.ts files are present (engineering exclusion for legal), eng vocab dense
-> Engineering dominates, legal score suppressed by exclusion signals
-> Correctly classified as engineering
```

**Handling misdetection**: User can always `!correct` or `!pack off` to fix. Corrections become training data for per-org signal refinement.

#### Invariants (What Must Always Hold)

1. **Universal taxonomy always available**: Even with no packs active, the 10 activities + 10 domains work. No pack = degraded UX, not broken UX.
2. **Pack suggestions never block prompts**: The suggestion is out-of-band. Work continues regardless of user response.
3. **Explicit user commands always win**: `!pack legal` overrides any detection logic.
4. **Stable project defaults**: Within a project, packs don't flicker. Changes require evidence threshold or explicit command.
5. **Local-first**: Pack signal scoring happens locally. Aggregate anonymized data for cross-customer learning is opt-in only.

**References**

*Software Engineering Activity Classification*
- Lientz & Swanson, "Software Maintenance Management" (1980) -- foundational taxonomy (corrective/adaptive/perfective)
- Schach et al., "Determining the Distribution of Maintenance Categories" (Empirical SE 2003)
- evidencebp/commit-classification -- 93% accuracy on corrective commit detection
- Conventional Commits Specification -- [conventionalcommits.org](https://www.conventionalcommits.org/)
- UTBMS Activity Codes (ABA/ACCA) -- [utbms.com/aba-activity-codes/](https://utbms.com/aba-activity-codes/)
- GitClear/Pluralsight Flow -- production auto-classification of commits

*Tree-Path Classification Against Large Taxonomies*
- Xue et al., "Deep Classification in Large-scale Text Hierarchies" (SIGIR 2008) -- two-stage retrieve+classify, 51.8% Mi-F1 at level 5 over 130K ODP categories
- Sebastiani, "Machine Learning in Automated Text Categorization" (ACM Computing Surveys 2002) -- foundational survey
- Gabrilovich & Markovitch, "Explicit Semantic Analysis" (IJCAI 2007) -- Wikipedia concepts as classification space
- Suchanek et al., "YAGO: A Core of Semantic Knowledge" (WWW 2007) -- Wikipedia + WordNet unified taxonomy
- Puurula et al., "Kaggle LSHTC4 Winning Solution" (arXiv 1405.0546) -- ensemble methods on DMOZ
- TELEClass (arXiv 2403.00165, WWW 2025) -- LLM walk-the-tree weakly-supervised HTC
- HierPrompt (EMNLP-Findings 2025) -- zero-shot HTC via category contextualization
- KG-HTC (arXiv 2505.05583) -- RAG + knowledge graphs for hierarchical classification
- Payberah, "Single-pass Hierarchical Text Classification with LLMs" -- walk-the-tree vs flat LLM comparison
- "Hierarchical Text Classification Using Black Box LLMs" (arXiv 2508.04219) -- cost/accuracy tradeoffs
- Wu et al., "Deep-RTC" (ECCV 2020) -- hierarchical rejection for long-tailed recognition

*Extreme Multi-Label Classification (XMC)*
- Parabel (Prabhu et al. 2018) -- balanced label tree, 1-vs-all at leaves
- AttentionXML (arXiv 1811.01727) -- label tree + attention
- X-Transformer / XR-Transformer (Chang et al. 2019, 2021) -- transformer + XR-Linear
- CascadeXML (NeurIPS 2022, arXiv 2211.00640) -- multi-resolution, end-to-end, SOTA
- PECOS (JMLR 2022, [github.com/amzn/pecos](https://github.com/amzn/pecos)) -- production framework, <1ms at 2.8M labels
- Extreme Classification Repository -- [manikvarma.org](http://manikvarma.org/downloads/XC/XMLRepository.html) benchmark datasets

*Production Systems Using Large Taxonomies*
- Pinterest Interest Taxonomy + Pin2Interest -- 10 levels, 10K+ interests, 200B+ pins classified
- Pinterest Neural Taxonomy Expansion -- embedding projection to find parents for new terms
- LinkedIn Skills Graph -- 39K skills, 374K aliases, KGBert-assisted maintenance
- Netflix 76,897 altgenres -- combinatorial paths over curated tag vocabulary
- Spotify / Every Noise at Once (~6,291 genres) -- bottom-up clustering + naming
- Microsoft Academic Graph Fields of Study -- 700K fields, 5 levels, hierarchical classifier
- Amazon hierarchical product classifier (2024) -- 91.6% accuracy at 3rd tier, dual-expert LLM
- Gupta et al., "Don't Classify, Translate" (2018) -- seq2seq translation to category paths

*Path Aggregation / User Profiling*
- Middleton et al., "Ontological User Profiling in Recommender Systems" (ACM TOIS 2004) -- foundational
- Karloff & Shirley, "Summary Trees" (2013) -- MDL-based taxonomy summarization, DMOZ example
- Iana et al., "Survey on Knowledge-Aware News Recommender Systems" (2024) -- path-based methods
- "User Modeling and User Profiling: A Comprehensive Survey" (arXiv 2402.09660, 2024)
- Pachinko Allocation Model (Li & McCallum ICML 2006) and Hierarchical PAM (2007)
- TDTMF (Information Processing & Management 2022) -- temporal interest drift modeling

*Available Open-Source Taxonomies*
- Curlie (DMOZ successor): ~1M categories, ~3M entries, depth 15, OSS w/ attribution
- Wikipedia categories: ~1.5M categories, CC BY-SA (cyclical, needs DBpedia for clean tree)
- YAGO: 17M entities, CC BY 3.0/4.0, Wikipedia+WordNet clean taxonomy
- IAB Content Taxonomy v3.1: ~698 categories, 4 tiers, open on GitHub
- Google Product Taxonomy: ~6,600 categories, public
- MAG Fields of Study: 700K fields, 5 levels, CC0
- WildChat 1M (Allen AI, arXiv 2405.01470) -- real ChatGPT interactions, mineable for AI-use taxonomy

