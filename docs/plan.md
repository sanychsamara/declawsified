# Declawsified MVP Execution Plan

**Date:** April 11, 2026
**Objective:** Deliver a working LiteLLM auto-classification plugin that classifies every AI agent API call along 5 independent facets (domain, activity, project, artifact, phase) with 85-90% accuracy, serving knowledge workers from solo developers to enterprise organizations across engineering, legal, marketing, research, and finance.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Classification Taxonomy Design](#2-classification-taxonomy-design)
   - [2.1 The Problem with a Single Flat Taxonomy](#21-the-problem-with-a-single-flat-taxonomy)
   - [2.2 Faceted Classification: The Architectural Foundation](#22-faceted-classification-the-architectural-foundation)
   - [2.3 MVP Facet Schema (5 Dimensions)](#23-mvp-facet-schema-5-dimensions) -- domain, activity, project, artifact, phase
   - [2.4 Domain-Specific Activity Taxonomies (Industry Packs)](#24-domain-specific-activity-taxonomies-industry-packs) -- engineering, legal, marketing, research, finance, personal
   - [2.5 Automatic Project Detection](#25-automatic-project-detection)
   - [2.6 Multi-Dimensional Tag Output Format](#26-multi-dimensional-tag-output-format)
   - [2.7 The Combinatorial Power](#27-the-combinatorial-power-why-this-matters)
   - [2.8 Taxonomy Evolution Strategy](#28-taxonomy-evolution-strategy)
   - [2.9 Taxonomy Library: Starting Points by Setting](#29-taxonomy-library-starting-points-by-setting) -- solo dev, startup, enterprise, law firm, agency, university
   - [2.10 Cross-Dimensional Intelligence](#210-cross-dimensional-intelligence)
   - [2.11 In-Prompt Communication Layer](#211-in-prompt-communication-layer) -- `#tags` and `!commands` for power users
   - [2.12 Academic Foundations](#212-academic-foundations-for-this-design)
3. [Classification Engine: Research & Approach](#3-classification-engine-research--approach)
4. [Classification Technique Cost Analysis](#4-classification-technique-cost-analysis)
5. [Memory & Taxonomy System Research](#5-memory--taxonomy-system-research)
6. [Execution Steps](#6-execution-steps)
7. [Success Criteria & Metrics](#7-success-criteria--metrics)

---

## 1. Architecture Overview

```
Claude Code / Codex CLI / Any LLM client
    |
    | (ANTHROPIC_BASE_URL / OPENAI_BASE_URL)
    v
LiteLLM Proxy (existing infra, no changes)
    |
    | async_logging_hook
    v
+------------------------------------------+
|  AutoClassifier Plugin (THIS PROJECT)    |
|                                          |
|  Tier 1: Metadata Rules      (<0.1ms)   |
|    - git branch prefix                   |
|    - tool names / file paths             |
|    - model selection signals             |
|         |                                |
|  Tier 2: Keyword/ML Classifier (<1ms)   |
|    - keyword matching                    |
|    - TF-IDF + LogReg (when trained)      |
|         |                                |
|  Tier 3: LLM Micro-Classifier (200ms)   |
|    - GPT-4.1-nano / Gemini Flash Lite    |
|    - only for ambiguous cases            |
|                                          |
|  Output: request_tags +=                 |
|    ["auto:activity:debugging",           |
|     "auto:domain:engineering",           |
|     "auto:project:auth-service",         |
|     "auto:artifact:source",              |
|     "auto:phase:maintenance",            |
|     "auto:confidence:activity:0.92"]     |
+------------------------------------------+
    |
    v
SpendLogs DB (tags persisted, queryable)
    |
    v
Dashboard / Reports (cost by work type)
```

### Integration Point

LiteLLM `CustomLogger.async_logging_hook` -- runs before all success callbacks, receives the full `standard_logging_object`, can mutate `request_tags` before DB persistence. No LiteLLM code changes needed. Registration is a single line in proxy config.

### Data Available

- Full prompt text (`standard_logging_object["messages"]`)
- Full response (`standard_logging_object["response"]`)
- Cost in USD (`response_cost`)
- Token counts (input, output, cache)
- Existing manual tags (`request_tags`)
- Model, API base, team/user/org metadata
- Claude Code session headers (`X-Claude-Code-Session-Id`)

---

## 2. Classification Taxonomy Design

### 2.1 The Problem with a Single Flat Taxonomy

The original plan proposed 6 software engineering categories (debugging, feature-dev, refactoring, testing, research, devops). This fails on two fronts:

**It only serves individual software engineers.** At a company like Google or Meta, AI agents are used by legal teams drafting patents, marketing teams writing campaigns, researchers analyzing data, PMs coordinating across teams, security teams auditing code, and hardware engineers running simulations. A "debugging vs. feature-dev" taxonomy is invisible to 80% of knowledge workers.

**It collapses multiple independent dimensions into one.** A legal researcher debugging a contract analysis script is simultaneously doing: domain=Legal, activity=Debugging, project=Contract-Analyzer, artifact=Source, phase=Maintenance. Forcing this into a single "debugging" tag destroys the information that matters most to the CFO (Legal is spending $X on AI) and the engineering manager (debugging cost $Y this week).

### 2.2 Faceted Classification: The Architectural Foundation

The solution comes from S.R. Ranganathan's Colon Classification (1933) -- the foundational theory of faceted classification. Instead of a single tree, classify each API call along **multiple independent dimensions (facets)** simultaneously.

**Why facets over hierarchy:**

| Approach | Categories to Maintain | Training Examples | Combinations Supported |
|----------|----------------------|-------------------|------------------------|
| Single hierarchy (6 x 8 x 20 x 5) | 4,800 leaf nodes | ~48,000 (10/class) | Only pre-enumerated |
| Faceted (6 + 8 + 20 + 5) | 39 values across 4 facets | ~390 (10/value) | All 4,800 + any new combo |

Faceted classification requires **99% fewer definitions** and **99% fewer training examples** while supporting infinite new combinations without schema changes. This is not a "nice-to-have" -- it is a structural requirement for serving diverse organizations.

**Ranganathan's PMEST formula** identifies five universal facets for any knowledge domain:

| PMEST Facet | Meaning | Declawsified Analog |
|-------------|---------|---------------------|
| **Personality** | The core entity/agent | `agent` -- who is acting (Claude Code, Codex, Copilot) |
| **Matter** | The material being worked on | `artifact` -- what is being touched (source, test, config, docs) |
| **Energy** | The action/process/operation | `activity` -- what kind of work (debugging, drafting, research) |
| **Space** | Location in the organization | `domain` + `project` -- where in the org and what initiative |
| **Time** | Temporal period/phase | `phase` -- where in the work lifecycle (discovery, implementation, review) |

**Cognitive load constraint**: Miller's Law (1956) and Cowan's revision (2001) establish that humans can track **4 items** in working memory. The system should produce 4-5 facets maximum in the standard view, with optional extended facets available but not prominent. PMEST's 5 dimensions sit exactly at this limit.

### 2.3 MVP Facet Schema (5 Dimensions)

Every API call is classified along all 5 dimensions simultaneously. Each facet has its own classifier, they run independently and in parallel.

```
API Call arrives
    |
    v
+-- Facet Extractors (independent, parallel) --------+
|                                                      |
|  [agent_extractor]     -> agent=claude-code          |
|  [artifact_extractor]  -> artifact=source            |
|  [activity_classifier] -> activity=debugging (0.91)  |
|  [domain_extractor]    -> domain=engineering         |
|  [project_extractor]   -> project=auth-service       |
|  [phase_classifier]    -> phase=maintenance (0.78)   |
|                                                      |
+-- Optional: Cross-Facet Correlation Layer -----------+
|                                                      |
|  If artifact=test AND activity=debugging:            |
|    adjust -> activity=testing (0.85)                 |
|                                                      |
+------------------------------------------------------+
    |
    v
Output tags (all dimensions, per-facet confidence):
  auto:agent:claude-code
  auto:domain:engineering
  auto:activity:debugging
  auto:artifact:source
  auto:project:auth-service
  auto:phase:maintenance
  auto:confidence:activity:0.91
  auto:confidence:phase:0.78
```

#### Facet 1: `domain` -- Organizational Function (WHAT PART OF THE BUSINESS)

This is the highest-value facet for enterprises. It answers: "Which department's budget does this AI cost belong to?"

**MVP values (10 categories, derived from standard organizational structure + SOC major groups):**

| Value | Description | Signal Sources |
|-------|-------------|----------------|
| `engineering` | Software development, architecture, infrastructure | Code file types, dev tool calls, git operations |
| `research` | Scientific/market/competitive research, data science | Read-heavy, data analysis tools, academic references |
| `legal` | Contracts, compliance, IP, regulatory | Legal terminology, contract templates, regulatory references |
| `marketing` | Content creation, campaigns, brand, communications | Marketing copy, social media, campaign references |
| `finance` | Budgeting, forecasting, financial analysis, accounting | Spreadsheet operations, financial terms, reporting |
| `product` | Product management, specs, roadmaps, user research | PRDs, user stories, feature specs, competitive analysis |
| `design` | UI/UX, visual design, prototyping | Design files, CSS/styling, wireframe references |
| `security` | Security audits, vulnerability analysis, compliance | CVEs, audit logs, security scanning, policy files |
| `operations` | HR, procurement, internal processes, admin | Policy documents, process documentation, internal tools |
| `support` | Customer support, documentation, troubleshooting | Ticket references, FAQ content, customer-facing docs |

**Why these 10**: Cross-referencing SOC major groups (23 categories), standard corporate org charts, and Davenport's knowledge work taxonomy, these 10 cover >95% of knowledge work at technology companies. Non-tech organizations (hospitals, law firms, universities) have the same functional splits at the top level.

**Extraction strategy**: Primarily from team/user metadata already flowing through LiteLLM (team tags, virtual key assignment). Fallback to content-based classification using domain vocabulary.

#### Facet 2: `activity` -- Work Activity Type (WHAT KIND OF ACTION)

This is the original "work type" classifier, now one facet among five. The values need to work across ALL domains, not just engineering.

**The universal activity pattern**: Research across UTBMS legal billing codes, O*NET work activities, Bloom's taxonomy, and Reinhardt's knowledge worker roles reveals that the same ~10 activity types recur in every industry:

| Value | Description | Cross-Industry Validation |
|-------|-------------|---------------------------|
| `investigating` | Finding root causes, debugging, diagnosing, auditing | Legal A104, Medical diagnosis, Eng debugging, Audit fieldwork |
| `building` | Creating new artifacts from scratch, implementing | Legal A103, Eng feature-dev, Marketing content creation |
| `improving` | Refactoring, optimizing, enhancing existing work | Eng refactoring, Legal redlining, Marketing optimization |
| `verifying` | Testing, QA, validation, checking, proofreading | Legal A122, Eng testing, Audit testing, Medical lab work |
| `researching` | Exploring, reading, gathering information, learning | Legal A102, Academic research, Market research, Discovery |
| `planning` | Strategy, architecture, roadmapping, scheduling | Legal A101, PM sprint planning, Research study design |
| `communicating` | Writing emails, drafting messages, documentation | Legal A105-A108, All domains: meetings, reports, memos |
| `configuring` | DevOps, setup, deployment, infrastructure, admin | Eng devops, IT operations, System administration |
| `reviewing` | Code review, peer review, approval, critique | Legal review, Academic peer review, Eng code review |
| `coordinating` | Project management, cross-team sync, delegation | Legal A127, PM, Cross-functional coordination |

**Why 10 universal activities instead of 6 engineering-specific ones**: The UTBMS legal billing standard (A101-A128) has been production-validated for 25+ years across thousands of law firms. When we map their 28 activity codes to our system, they collapse to these same 10 categories. O*NET's 41 Generalized Work Activities similarly reduce to these clusters. This is not accidental -- these represent fundamental modes of knowledge work.

**Mapping from the original 6 engineering categories**:

| Original | New Universal | Notes |
|----------|--------------|-------|
| debugging | `investigating` | Same action, domain-neutral name |
| feature-dev | `building` | Same action, domain-neutral name |
| refactoring | `improving` | Same action, domain-neutral name |
| testing | `verifying` | Same action, domain-neutral name |
| research | `researching` | Same action, already domain-neutral |
| devops | `configuring` | Same action, domain-neutral name |
| (new) | `planning` | Was missing -- critical for PM, legal, product |
| (new) | `communicating` | Was missing -- significant AI use case |
| (new) | `reviewing` | Was missing -- code review, document review |
| (new) | `coordinating` | Was missing -- cross-team work, project mgmt |

**Bloom's cognitive level as an optional sub-dimension of activity**:

| Bloom's Level | Maps To | AI Agent Pattern |
|---------------|---------|------------------|
| Remember | `researching` | Information retrieval, lookup |
| Understand | `researching` | Summarization, explanation |
| Apply | `building`, `configuring` | Template application, procedure execution |
| Analyze | `investigating`, `reviewing` | Debugging, data analysis, comparison |
| Evaluate | `reviewing`, `verifying` | Code review, quality assessment |
| Create | `building`, `planning` | New code, designs, strategies |

#### Facet 3: `project` -- Work Initiative (WHAT ARE WE WORKING TOWARD)

Automatic project detection -- not deferred to post-MVP. This is the facet that answers "where is the money going?" and every enterprise buyer needs it from day 1.

**Detection hierarchy (most specific wins)**:

| Priority | Signal | Confidence | Example |
|----------|--------|------------|---------|
| 1 | Explicit tag in request headers | 100% | `x-litellm-tags: project:auth-service` |
| 2 | LiteLLM team/key assignment | 100% | Virtual key `sk-auth-team-abc` maps to team "auth-service" |
| 3 | Git repository name | 95% | Working dir `/home/dev/auth-service/` -> project=auth-service |
| 4 | Git branch name | 85% | Branch `feature/PROJ-123-oauth-flow` -> project=PROJ-123 |
| 5 | Working directory path | 80% | Path components as project identifier |
| 6 | Jira/Linear ticket reference in prompt | 90% | "Working on AUTH-456" in prompt text |
| 7 | Session continuity | 75% | Same session as previous call -> same project |
| 8 | Semantic clustering | 60% | Similar file paths/topics to previous classified calls |

**The Workday "driver worktag" pattern**: Once `project` is identified, it should auto-populate related metadata. If the project "auth-service" is registered, it auto-fills: team=platform, repository=github.com/co/auth-service, cost_center=ENG-042. This follows Workday's Foundation Data Model where driver worktags cascade to related worktags, eliminating manual tagging.

**Project registry design**:
```yaml
# declawsified-projects.yaml (user-provided, optional)
projects:
  auth-service:
    team: platform
    domain: engineering
    cost_center: ENG-042
    patterns:
      - repo: "*/auth-service"
      - branch: "AUTH-*"
      - directory: "*/auth-service/*"

  patent-filing-q3:
    team: ip-legal
    domain: legal
    cost_center: LEGAL-007
    patterns:
      - directory: "*/patent-q3/*"
      - keywords: ["patent", "prior art", "claims"]
```

When no registry exists, projects are auto-detected from git repository names and working directory paths, then surfaced to the user for confirmation and enrichment.

#### Facet 4: `artifact` -- What Is Being Worked On (WHAT MATERIAL)

| Value | Description | Detection Signal |
|-------|-------------|------------------|
| `source` | Application source code | `.py`, `.ts`, `.go`, `.java`, `.rs` etc. in tool calls |
| `test` | Test code and test infrastructure | `*_test.*`, `*_spec.*`, `test_*`, `__tests__/` |
| `config` | Configuration, environment, settings | `.yaml`, `.toml`, `.env`, `*.config.*`, `settings.*` |
| `docs` | Documentation, READMEs, specs | `.md`, `.rst`, `.txt`, `docs/`, `README` |
| `infra` | Infrastructure-as-code, CI/CD | `Dockerfile`, `.github/`, `terraform/`, `k8s/` |
| `data` | Data files, schemas, migrations | `.sql`, `.csv`, `.json` (data), `migrations/` |
| `design` | Design artifacts, mockups, styles | `.css`, `.scss`, `.figma`, `*.sketch`, design tokens |
| `legal` | Legal documents, contracts, policies | `.docx` (legal), contract templates, policy files |

**Extraction**: Pure rule-based from file paths in tool calls. Near-zero cost, near-100% accuracy when file paths are present. Falls back to `unknown` when no file operations occur (e.g., pure conversation).

#### Facet 5: `phase` -- Work Lifecycle Position (WHEN IN THE PROCESS)

| Value | Description | Detection Signal |
|-------|-------------|------------------|
| `discovery` | Understanding the problem, exploring options | Read-heavy, question-heavy prompts, broad file access |
| `planning` | Designing the solution, architecting | Architecture docs, diagrams, decision records |
| `implementation` | Active building, creating, coding | Edit-heavy, new file creation, high write:read ratio |
| `review` | Reviewing, testing, validating | Review comments, diff inspection, test running |
| `deployment` | Releasing, deploying, configuring production | Deploy scripts, production configs, release notes |
| `maintenance` | Fixing, patching, updating existing systems | Bug branches, hotfix, small targeted changes |

**Extraction**: Session-level pattern analysis. A session that starts Read-heavy and transitions to Edit-heavy moves from `discovery` to `implementation`. This is the lowest-confidence facet and can be omitted in early releases.

### 2.4 Domain-Specific Activity Taxonomies (Industry Packs)

The 10 universal activities cover the cross-domain view. But within specific domains, finer-grained activity taxonomies already exist and have been battle-tested in production for decades. Declawsified should ship with **pre-built taxonomy packs** that layer domain-specific subcategories onto the universal activities.

#### Why Domain Packs?

When Meta's legal team uses the tool, they don't want "investigating" -- they want the UTBMS codes they already use for billing. When Google's engineering team uses it, they want Conventional Commits categories. The universal taxonomy is the common language; domain packs are the local dialects.

**Architecture**: Domain packs are optional overlays. The universal 10-activity taxonomy always runs. When a domain pack is active for a team, it adds a second-level classification within the detected activity.

```
Universal:  activity=investigating
  +
Legal pack: legal_activity=L300:discovery, legal_task=A102:research
  =
Tags: auto:activity:investigating, auto:legal:L300, auto:legal_task:A102
```

#### Pack: Software Engineering

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

#### Pack: Legal

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

#### Pack: Marketing

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

#### Pack: Research / Academic

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

#### Pack: Finance / Accounting

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

#### Pack: Personal / Education

Based on GTD, PARA method, Eisenhower matrix, and Bloom's taxonomy for learning activities.

| Activity | Personal/Education Sub-Activities |
|----------|-----------------------------------|
| `investigating` | troubleshooting, problem-diagnosis, self-assessment |
| `building` | project-work, homework, creative-project, portfolio |
| `improving` | skill-practice, revision, editing, self-improvement |
| `verifying` | self-testing, quiz-prep, answer-checking, proofreading |
| `researching` | learning, reading, tutorial-following, course-study |
| `planning` | goal-setting, schedule-planning, project-planning, career-planning |
| `communicating` | email, journaling, blogging, social-media-personal |
| `configuring` | tool-setup, environment-config, account-management |
| `reviewing` | note-review, spaced-repetition, reflection, mentor-feedback |
| `coordinating` | group-project, meeting-scheduling, delegation |

#### Pack Auto-Detection: Finding the Right Pack Without Configuration

New users install the plugin and type their first prompt. They haven't configured a profile. They may not even know what a "domain pack" is. The system must **work immediately with zero config** and **suggest the right pack(s) after observing real usage** -- never blocking productivity on setup.

##### Design Goals

1. **Zero-config start**: No pack required. Universal 10-activity taxonomy works for everyone.
2. **Progressive enhancement**: Packs activate as evidence accumulates. Never disrupt active work.
3. **Multi-pack support**: A user can have engineering AND legal active simultaneously (e.g., a tech company's GC who codes). Packs are not mutually exclusive.
4. **Per-project scope**: Packs can be global or scoped to specific projects.
5. **Unobtrusive suggestion**: Ask once, remember the answer, don't nag.

##### Pack Detection Signals

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

##### Scoring Algorithm

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

##### Activation State Machine

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

##### Bootstrap Phase (First 50 Calls)

Before enough evidence accumulates, the system runs in **observation mode**:

```
Universal taxonomy only (10 activities, 10 domains, no sub-activities)
+
Signal scoring for all 6 packs (background, no user-facing action)
+
Auto-discovery report accumulating
```

The user sees classifications working immediately (universal taxonomy). The pack-specific refinement is invisible until suggested.

##### Suggestion UX

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

##### Multi-Pack Operation

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

##### Per-Project Pack Scoping

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

##### Explicit Pack Commands

For power users and edge cases, the in-prompt command layer (Section 2.11) supports pack control:

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

##### Cold Start Learning Loop

Over the first month, the system learns:

**Week 1 (calls 1-50)**: Universal taxonomy only. Observation mode. Pack scores accumulating.

**Week 2 (calls 50-200)**: First pack suggestion surfaces. User accepts (most common case) or declines. Pack-specific sub-activity classification begins for accepted packs.

**Week 3-4 (calls 200-1000)**: Classifier confusion analysis per pack. User corrections refine pack detection signals. Secondary pack may surface if work is cross-domain.

**Month 2+**: Pack detection is mature. Cross-customer aggregate data improves baseline (the CrowdStrike flywheel). Signal inventories refined based on real-world term distributions.

##### Project-Level Pack Inference

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

##### Pack Conflicts and Edge Cases

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

##### Invariants (What Must Always Hold)

1. **Universal taxonomy always available**: Even with no packs active, the 10 activities + 10 domains work. No pack = degraded UX, not broken UX.
2. **Pack suggestions never block prompts**: The suggestion is out-of-band. Work continues regardless of user response.
3. **Explicit user commands always win**: `!pack legal` overrides any detection logic.
4. **Stable project defaults**: Within a project, packs don't flicker. Changes require evidence threshold or explicit command.
5. **Privacy**: Pack signal scoring happens locally. Aggregate anonymized data for cross-customer learning is opt-in only.

### 2.5 Automatic Project Detection

Project detection is not optional and cannot wait for post-MVP. It is the #1 value proposition for any organization beyond a single developer.

#### Detection Algorithm

```python
def detect_project(call_metadata: dict, project_registry: dict) -> str:
    """
    Returns project identifier. Runs as part of Facet 3 extraction.
    Priority order ensures most-specific signal wins.
    """
    # Priority 0: In-prompt command (100% confidence, see Section 2.11)
    #   User typed: !project auth-service   OR   #project:auth-service
    if prompt_command := extract_project_from_prompt(call_metadata.get("messages")):
        register_if_new(prompt_command, project_registry)
        return prompt_command

    # Priority 1: Explicit header tag (100% confidence)
    if explicit_tag := call_metadata.get("request_tags", {}).get("project"):
        return explicit_tag

    # Priority 2: LiteLLM team/key mapping (100% confidence)
    if team := call_metadata.get("team_alias"):
        if project := registry_lookup(team, project_registry):
            return project

    # Priority 3: Git repository name (95% confidence)
    if repo := extract_git_repo(call_metadata):
        return normalize_project_name(repo)

    # Priority 4: Git branch with ticket reference (85% confidence)
    if branch := extract_git_branch(call_metadata):
        if ticket := extract_ticket_id(branch):  # PROJ-123, AUTH-456
            return ticket
        if project_prefix := extract_branch_project(branch):
            return project_prefix

    # Priority 5: Working directory (80% confidence)
    if workdir := extract_working_directory(call_metadata):
        return derive_project_from_path(workdir)

    # Priority 6: Ticket reference in prompt prose (90% confidence)
    if prompt := call_metadata.get("messages"):
        if ticket := extract_ticket_from_text(prompt):  # "Working on AUTH-456..."
            return ticket

    # Priority 7: Session continuity (75% confidence)
    if session_project := get_session_project(call_metadata.get("session_id")):
        return session_project

    return "unattributed"
```

**Note on Priority 0**: User-typed tags and commands in the prompt text are the **highest-priority signal** because they represent direct, intentional user communication. The in-prompt layer (Section 2.11) gives users the lowest-friction way to override automatic detection when they know better than the signals.

#### Session-Level Project Tracking

Within a session, project typically doesn't change. Track the dominant project per session and apply it to all calls:

```
Session starts -> first call with workdir /home/dev/auth-service/
  -> project=auth-service (confidence 0.80)
  -> all subsequent calls in session inherit project=auth-service
  -> unless a strong counter-signal appears (different repo, different branch)
```

#### Auto-Discovery Mode

When no project registry exists (first-time users), the system operates in auto-discovery mode:

1. Extract project identifiers from git repos and working directories
2. Cluster API calls by detected project
3. Generate a report: "We detected 5 projects this week: auth-service (42% of spend), frontend-redesign (28%), docs-update (15%), infra-monitoring (10%), unattributed (5%)"
4. User confirms or corrects, building the project registry over time

### 2.6 Multi-Dimensional Tag Output Format

Every classified call produces tags in a structured namespace:

```
# Core facets (always present)
auto:domain:engineering
auto:activity:investigating
auto:project:auth-service

# Artifact and phase (present when detectable)
auto:artifact:source
auto:phase:maintenance

# Agent identification (always present, trivial extraction)
auto:agent:claude-code
auto:agent:model:claude-sonnet-4-5

# Domain pack overlay (when active)
auto:engineering:error-tracing
auto:engineering:commit-type:fix

# Confidence scores (per-facet)
auto:confidence:domain:0.95
auto:confidence:activity:0.91
auto:confidence:project:0.80
auto:confidence:phase:0.72

# Classifier metadata
auto:classifier:activity:tier1     # which tier resolved this facet
auto:classifier:version:0.3.1     # classifier version for reproducibility
```

This format is compatible with LiteLLM's `request_tags` (flat string list) while encoding structured multi-dimensional data. Consumers can filter on any facet dimension independently: "show me all `auto:domain:legal` spend" or "show me all `auto:activity:investigating` across all domains."

### 2.7 The Combinatorial Power: Why This Matters

With 5 facets, the system answers questions no single-taxonomy tool can:

| Question | Facets Used | Who Asks |
|----------|-------------|----------|
| "How much did Legal spend on AI this month?" | domain=legal | CFO |
| "What % of engineering AI use is debugging vs building?" | domain=engineering, activity | VP Engineering |
| "How much did the auth-service project cost?" | project=auth-service | Project lead |
| "Are we spending more on research or implementation?" | activity | Anyone |
| "Which projects are stuck in investigation phase?" | activity=investigating, project, phase | PM |
| "How much AI spend is on test code vs source code?" | artifact | Tech lead |
| "Which team spends the most on AI-assisted code review?" | activity=reviewing, domain | Engineering manager |
| "What's our AI cost for patent work specifically?" | domain=legal, project=patent-* | IP counsel |
| "How does Claude Code vs Codex cost compare for debugging?" | agent, activity=investigating | Developer |
| "What fraction of AI use is deep creative work vs admin?" | activity (Bloom's mapping) | CTO |

None of these questions are answerable with a flat 6-category engineering taxonomy. All are answerable with faceted classification from day 1.

### 2.8 Taxonomy Evolution Strategy

#### Within-Facet Evolution

Each facet's value list can evolve independently using TaxoAdapt signals (ACL 2025):

- **Density threshold**: When a value accumulates >= N classified calls with high internal variance, suggest splitting (e.g., `investigating` in engineering contains both "error-tracing" and "performance-profiling" patterns -> offer subcategories).
- **Unmapped density**: When calls are classified with low confidence, cluster them and suggest new values.
- Maximum depth: 2 levels within a facet (value + optional sub-value). No deeper -- complexity kills adoption.

#### TaxMorph Refinement (EACL 2026)

Periodically (weekly/monthly), run taxonomy health check:
1. Analyze classifier confusion matrix per facet
2. Identify frequently-confused value pairs
3. Apply four operations: rename (clarity), merge (redundant values), split (overloaded values), rearrange (misplaced values)
4. Key finding: **taxonomies refined to align with actual classifier confusion patterns improve F1 by +2.9 points**

#### Custom Facets

Following Workday's model (supports 15 custom worktag types), allow organizations to define additional facets beyond the core 5. Examples:

- `cost_center` -- maps to accounting codes
- `client` -- for agencies/consultancies billing multiple clients
- `compliance_scope` -- for regulated industries (HIPAA, SOX, GDPR)
- `priority` -- urgent/normal/low
- `billable` -- yes/no (critical for professional services)

Custom facets can be rule-based (derived from project registry) or LLM-classified.

#### Balanced Tree Construction (When Subcategories Are Needed)

From the eXtreme Multi-Label classification literature, use **Positive Instance Feature Aggregation (PIFA)**:

```
Input: N classified calls for a facet value, desired branching factor B
Output: B subcategories with descriptive names

1. Compute TF-IDF weighted embeddings for all calls in this value
2. Apply balanced k-means with k=B
3. If inter-cluster distance > SEPARATION_THRESHOLD:
   - Clusters are meaningfully distinct -> create subcategories
   - Use LLM to generate descriptive names for each cluster
4. If inter-cluster distance < SEPARATION_THRESHOLD:
   - Value is already cohesive -> do not split
```

Research shows algorithmically-constructed frequency-based hierarchies outperform hand-curated semantic hierarchies for classification accuracy (CascadeXML R-Precision 84.61 vs HGCLR 84.22 on NYT-166).

### 2.9 Taxonomy Library: Starting Points by Setting

The system ships with pre-configured taxonomy profiles for different organizational contexts. Users select a profile at setup; it configures which domain packs are active and how facets are weighted.

#### Profile: Solo Developer / Open Source

```yaml
profile: solo-developer
domain_facet: disabled  # single person, no org structure
active_packs: [engineering]
primary_view: activity + project
project_detection: auto (git repo + working directory)
```

#### Profile: Engineering Team (Startup / SMB)

```yaml
profile: engineering-team
domain_facet: simplified  # engineering, product, design, operations
active_packs: [engineering]
primary_view: project + activity + artifact
project_detection: litellm teams + git repo
```

#### Profile: Enterprise Technology Company (Google, Meta scale)

```yaml
profile: enterprise-tech
domain_facet: full  # all 10 domains
active_packs: [engineering, legal, marketing, research, finance]
primary_view: domain + project + activity
project_detection: litellm teams + project registry + git repo
custom_facets: [cost_center, business_unit]
```

#### Profile: Law Firm / Legal Department

```yaml
profile: legal
domain_facet: simplified  # legal, operations, research
active_packs: [legal]
primary_view: project (=matter) + activity (UTBMS-mapped)
project_detection: matter number from headers/prompts
custom_facets: [client, matter_type, billable]
utbms_export: enabled  # export classifications as UTBMS codes
```

#### Profile: Consulting / Professional Services

```yaml
profile: professional-services
domain_facet: per-engagement
active_packs: [finance, legal, engineering]  # depends on practice
primary_view: client + project (=engagement) + activity
project_detection: engagement codes from headers
custom_facets: [client, engagement, billable, service_line]
```

#### Profile: University / Research Institution

```yaml
profile: academic
domain_facet: simplified  # research, teaching, administration
active_packs: [research, personal]
primary_view: project (=grant/study) + activity
project_detection: grant numbers, course codes
custom_facets: [grant_number, pi, department, funding_source]
```

#### Profile: Marketing Agency

```yaml
profile: marketing-agency
domain_facet: simplified  # marketing, design, operations
active_packs: [marketing]
primary_view: client + project (=campaign) + activity
project_detection: client/campaign codes from headers
custom_facets: [client, campaign, channel, billable]
```

### 2.10 Cross-Dimensional Intelligence

The highest-value insights come from correlating across facets. These are not part of the classifier itself but emerge from the multi-faceted data:

**Work pattern detection**:
- "Engineering team spends 45% of AI budget on `investigating` (debugging) -- 3x higher than industry benchmark of 15%. Suggest investment in testing infrastructure."
- "Legal team's `researching` activity doubled after the EU AI Act deadline announcement."
- "Project auth-service has been in `maintenance` phase for 8 weeks with 90% `investigating` activity -- this project may need architectural attention."

**Anomaly detection**:
- Sudden spike in `investigating` activity -> potential production incident
- Unusual `domain` for a team -> shadow AI usage detection
- High `unattributed` project rate -> tagging hygiene issue

**Cross-customer pattern learning (the CrowdStrike flywheel)**:
- Aggregate anonymized activity distributions across customers
- "Companies with >30% `investigating` spend tend to have lower `building` productivity"
- "Legal teams that use AI for `researching` show 40% reduction in `reviewing` time"
- This is the long-term moat: classification models that improve from cross-customer data

### 2.11 In-Prompt Communication Layer

The lowest-friction configuration method is the prompt itself. No config files, no env vars, no UI. Users should be able to declare project affinity, correct classifications, and pass metadata by typing naturally -- the same way Slack users embed `#channel` references or GitHub users type `/assign @user` in comments.

#### The Core Constraint: LLM Visibility

Declawsified is in-band. Unlike Slack where commands are intercepted server-side before any LLM sees them, our prompts flow through LiteLLM to the main agent (Claude Code, Codex, etc.). Any syntax we design will be visible to the main LLM. This creates a hard requirement: **the syntax must be safe even if the LLM interprets it literally.**

Research across 10 LLMs showed that instruction-styled tokens (e.g., `#ignore-previous-instructions`) achieved 20-30% compliance rates against weakly-aligned models. The design must avoid instruction-shaped syntax entirely.

#### Sigil Selection: Why `#` for Tags and `!` for Commands

Modern chat/dev tools have converged on three sigils, each already claimed by something:

| Sigil | Claude Code | Codex CLI | Cursor | Copilot | Slack | Availability |
|-------|-------------|-----------|--------|---------|-------|--------------|
| `/` | 60+ built-in commands | 20+ commands | Folder drill-down | 5+ commands | Slash commands | **Collides** |
| `@` | File references | File references | File/symbol mentions | Chat participants | User mentions | **Collides** |
| `#` | *unused* | *unused* | *unused* | Chat variables (VS Code only) | Channel references | **Available** |
| `!` | *unused* | *unused* | *unused* | *unused* | *unused* | **Available** |

**Declawsified claims `#` for tags and `!` for commands.** Both sigils are unused by major agents, have strong precedent elsewhere (`#` = hashtags since Twitter 2007, `!` = bot commands since IRC/Hubot), and are rarely ambiguous in natural prose.

#### Tag Syntax (Mid-Prompt, Anywhere)

Lightweight topic-style tags, embeddable mid-sentence, following twitter-text parsing rules:

```
#<namespace>:<value>    # structured: explicit facet assignment
#<value>                # freeform: classifier infers namespace
#<ns>/<sub>/<value>     # nested: Obsidian-style hierarchical tag
```

Examples in natural prose:
```
"Working on the OAuth timeout #project:auth-service. This looks like a
regression from yesterday's deploy #bug."

"Switching context to #patent-filing-q3 for the afternoon. Need to
review prior art #domain:legal."

"Let me investigate this #performance issue in the login flow
#project/auth-service/token-validation."
```

**Parsing regex** (derived from Twitter's `twitter-text` reference implementation, the most-standardized hashtag spec):
```
(?:^|[^\p{L}\p{M}\p{Nd}_])#([\p{L}\p{Nd}_\-/:]+)
```

**Rules**:
- Character set: Unicode letters, digits, `_`, `-`, `/`, `:`
- Boundary: preceded by start-of-string or non-word character (prevents matching URLs like `example.com/#anchor` or code like `#include`)
- Must contain at least one non-numeric character (so `#2026` is text, `#q3-2026` is a tag) -- Obsidian's rule
- Case-insensitive matching

**Why namespace:value pattern**: Matches established conventions (Docker image tags `ubuntu:22.04`, YAML keys `project: auth-service`, semantic web `foaf:name`). Terse, unambiguous, nestable.

#### Command Syntax (Start-of-Line, More Expressive)

For actions beyond tagging (declaring new projects, corrections, overrides), use `!` commands anchored to the start of any line -- the proven Prow/GitLab pattern:

```
!<command> [args]           # at start of any line (not message)
```

**Parsing regex**:
```
(?m)^!(\w[\w-]*)(?:\s+(.*?))?\s*$
```

The multi-line anchor (`(?m)^`) is critical: prose flows around commands in multi-line prompts, but single-line commands still work. Over a decade of Kubernetes PRs has proven this exact split.

**MVP command vocabulary**:

| Command | Purpose | Example |
|---------|---------|---------|
| `!project <name>` | Assign project (this call + session) | `!project auth-service` |
| `!new-project <name> [key=val ...]` | Declare and register new project | `!new-project patent-q3 domain=legal cost_center=LEG-07` |
| `!activity <value>` | Override activity classification | `!activity improving` |
| `!domain <value>` | Override domain classification | `!domain legal` |
| `!phase <value>` | Override phase | `!phase discovery` |
| `!goal <description>` | Attach goal/task description | `!goal migrate auth to OAuth2` |
| `!correct <facet>=<value>` | Correct prior classification | `!correct activity=improving` |
| `!tag <tag>` | Add arbitrary tag | `!tag urgent` |
| `!untag <tag>` | Remove tag | `!untag urgent` |
| `!no-classify` | Skip classification for this call | `!no-classify` |
| `!pack <name>[,<name>]` | Activate pack(s) for this call only | `!pack legal` |
| `!pack off [<name>]` | Disable pack(s) for this call | `!pack off` |
| `!pack-default <name>` | Set default pack(s) for current project | `!pack-default legal,research` |
| `!pack-auto <on\|off>` | Toggle auto-suggestion acceptance | `!pack-auto on` |
| `!pack-no-thanks <name>` | Decline pack suggestion (30-day cooldown) | `!pack-no-thanks marketing` |
| `!help` | Out-of-band help (doesn't reach LLM) | `!help` |

**Tag-to-command equivalence table**:

| Inline tag | Equivalent command | Notes |
|-----------|-------------------|-------|
| `#project:X` | `!project X` | Same effect |
| `#X` (freeform) | `!project X` if X is registered | Otherwise logged as signal |
| `#activity:X` | `!activity X` | Same effect |
| `#urgent` | `!tag urgent` | Generic tag |

Users can mix styles freely -- inline tags feel natural, line-anchored commands are more explicit.

#### LLM Safety Analysis: Why This Is Robust

If the main LLM sees our tags/commands despite our parsing, what happens?

**Hashtag case (`#project:auth-service`)**:
- Pattern-matched to social media / forum posts in training data
- Models treat as topic decoration, not instruction
- **Worst case**: Model echoes it ("I see you're working on `#project:auth-service`...")
- **Risk**: Zero. No action taken, just content acknowledgment.

**Bang-command case (`!project auth-service`)**:
- Pattern-matched to exclamation + text or bot commands (IRC, Discord)
- Less consistent training signal, but still non-instructional in most contexts
- **Worst case**: Model interprets as emphasis or remarks on syntax
- **Risk**: Very low. Even if model tries to "help" with the command, it cannot execute anything consequential.

**What we explicitly avoid**:

| Pattern | Why It's Unsafe |
|---------|----------------|
| `<project>X</project>` | LLM interprets as XML tool call |
| `classify as debugging` | Natural-language instruction -- LLM will follow it |
| `/command` (at line start) | Collides with agent built-ins, gets stripped before LiteLLM |
| `[SYSTEM] project=X` | Mimics system prompt injection |
| `!ignore-previous` | Instruction-shaped token, prompt injection risk |
| `sudo project X` | Imperative verb pattern |

**Design principle**: Declarative noun-phrases ("project is auth-service") are safer than imperative verb-phrases ("set project to auth-service"). Our syntax is entirely declarative: `#project:auth-service` declares a topic, `!project auth-service` declares a label. Neither compels the LLM to take action.

#### Extraction Pipeline

```
Raw prompt arrives at UserPromptSubmit hook (or LiteLLM async_logging_hook)
    |
    v
Step 1: Extract tags (regex, pure function, no LLM calls)
    hashtags = find_hashtags(prompt)
    commands = find_line_commands(prompt)
    |
    v
Step 2: Route to facet assignments
    explicit_facets = {
        "project": from !project or #project:X,
        "activity": from !activity or #activity:X,
        "domain": from !domain or #domain:X,
        ...
    }
    freeform_tags = [tags that don't match a namespace]
    |
    v
Step 3: Run facet classifiers (parallel)
    For each facet NOT in explicit_facets:
        Run normal Tier 1-3 cascade
    For facets IN explicit_facets:
        Skip classification, use user value at confidence 1.0
    |
    v
Step 4: Apply prompt handling mode
    strip_mode:     remove all !commands and #tags from prompt
    preserve_mode:  leave prompt untouched (default)
    normalize_mode: replace #project:X with "(context: working on X)"
    |
    v
Step 5: Forward cleaned prompt to LLM, emit tags to LiteLLM
```

#### Three Prompt Handling Modes

| Mode | Behavior | Best For |
|------|----------|----------|
| `preserve` (default) | Tags remain in prompt, visible to LLM | Solo devs, natural flow |
| `strip` | Remove tags/commands before LLM call | Enterprise, clean audit trails |
| `normalize` | Convert tags to natural-language phrases | Balanced -- LLM gets context, users see clean UI |

**Example of `normalize` mode**:

```
Before: "Working on #project:auth-service. Fix the #bug in token validation.
         !activity investigating"

After:  "Working on the auth-service project. Fix the bug in token validation.
         (The user is investigating this issue.)"
```

Normalization preserves context for the LLM while making the structured metadata invisible as syntax.

#### Session Continuity: Sticky Tags

Once a user tags a project, it persists without retyping -- matching the Slack-channel mental model where context is implicit.

```
Prompt 1: "Working on #project:auth-service. Let me fix the timeout bug."
          -> project=auth-service tagged AND cached for session

Prompt 2: "Now let me check the token validation logic."
          -> project=auth-service inherited from session cache

Prompt 3: "!project frontend-redesign switching to frontend work"
          -> session cache updated to project=frontend-redesign

Prompt 4: "Now update the login page styles."
          -> project=frontend-redesign inherited
```

**Invalidation signals** (session project cleared, re-auto-detect):
- `!project clear` (explicit user action)
- Git branch change detected (automatic)
- Working directory change detected (automatic)
- Session gap > 30 minutes (automatic)

#### New Project Declaration (On-the-Fly)

```
!new-project patent-q3-filings domain=legal cost_center=LEGAL-007

Working on Q3 patent filings. Need to research prior art for the
new compression algorithm.
```

**Effects**:
1. Registers `patent-q3-filings` in the project registry
2. Associates driver-related metadata (domain=legal, cost_center=LEGAL-007) -- Workday pattern
3. Sets current call and session to this project
4. Future calls matching signals (file paths, git branches) auto-attribute to this project

**Auto-suggestion from observation**: When the classifier detects recurring unattributed patterns, it surfaces a one-command registration:

```
[Declawsified] Detected 47 calls in /home/dev/acme-migration/ this week, no project tag.
[Declawsified] Suggest: !new-project acme-migration domain=engineering
```

User types the suggested command once; all past and future calls in that pattern are retroactively attributed.

#### Correction Loop: The Mint Pattern

When the classifier gets it wrong, corrections flow back as training data:

```
# Previous call classified as activity=building
!correct activity=improving

I was refactoring the auth module, not building new features.
```

**Effects**:
1. Updates tags on the most recent call (time-limited to last 10 calls in session)
2. Stores as labeled training example for the active-learning pipeline
3. Pattern-tracks corrections: "You've corrected activity=building→improving 5 times this week -- adjust classification rules?"

This is the feedback flywheel from Mint's auto-categorization -- initial accuracy of 70-80% improves to 95%+ over weeks as user corrections accumulate.

#### Error Handling: Fail-Safe Parsing

Unknown or malformed syntax must never block the user's actual prompt.

**Unknown command (typo)**:
```
User types: !projct auth-service
    |
    v
Parsed as: command="projct" args="auth-service"
    |
    v
No match in command registry
    |
    v
Fuzzy match: "project" (Levenshtein similarity 0.89, >= 0.85 threshold)
    |
    v
Action: log as signal "unknown_command:projct",
        surface suggestion via out-of-band channel
        (NOT inline -- would leak to LLM)
        DO NOT auto-correct, DO NOT block prompt
    |
    v
Prompt proceeds to LLM unchanged (in preserve mode) or with command stripped (in strip mode)
```

**Invalid argument**:
```
User types: !project    (no name)
    |
    v
Parsed, validation fails
    |
    v
Action: silent skip, log for debugging
    |
    v
Prompt proceeds normally
```

**Unrecognized hashtag**:
```
User types: #quantum-flux-capacitor
    |
    v
No facet namespace match, no registered project match
    |
    v
Action: log as freeform signal "tag:quantum-flux-capacitor"
        (weak classification signal -- maybe future pattern)
    |
    v
Prompt proceeds normally
```

**Fuzzy-match threshold**: 0.85 Levenshtein similarity. Below threshold → no suggestion. Never auto-correct (the GitHub CLI lesson: silent rewrites confuse users more than explicit errors).

#### Integration Points by Agent

**Claude Code (5/5 feasibility)**: `UserPromptSubmit` hook is ideal.
- Fires before LLM invocation with raw prompt text
- Can mutate prompt (for strip/normalize modes)
- Can emit structured metadata to LiteLLM via `ANTHROPIC_CUSTOM_HEADERS`
- Zero latency penalty (hook runs in milliseconds)

**Codex CLI (4/5)**: Codex hook system (added March 2026) provides similar pre-prompt interception. Mechanism under development; fall back to proxy-level extraction.

**LiteLLM proxy (universal)**: Extract from `standard_logging_object["messages"]` in `async_logging_hook`.
- Works for all agents routing through LiteLLM
- Limitation: runs AFTER LLM sees the prompt (can't strip, only tag)
- Still fully functional for `preserve` mode

**MCP server (future, 100% safe)**: A dedicated Declawsified MCP tool that agents invoke explicitly (`declawsified_tag(project="X")`). Completely bypasses the main LLM. Requires agent support for tool invocation but gives perfect safety guarantees.

#### Claude-in-Slack: Validating Prior Art

Anthropic's own Claude-in-Slack integration (`code.claude.com/docs/en/slack`) uses a similar classification pattern in production:

- Slack `@Claude` mentions trigger an intent classifier (code task vs. chat)
- Two routing modes: "Code only" or "Code + Chat" (auto-routed)
- Misclassification surfaces a "Retry as Code" button
- Explicit security warning: "Claude may follow directions from other messages in the context"

This validates both (a) that intent classification works in production at this level, and (b) that the prompt-visibility concern is real and must be designed around. Declawsified's syntax design directly addresses the warning by using declarative (not imperative) tags.

#### Discovery: `!help` Without LLM Leakage

How does a user discover the available commands? The `!help` command must return documentation WITHOUT passing through the main LLM (which would be confusing and waste tokens).

**Implementation options**:

1. **Hook-level response**: The `UserPromptSubmit` hook intercepts `!help` alone, returns help text directly to the terminal, blocks the LLM call entirely. Best UX but requires hook support.
2. **Documented in CLAUDE.md**: If Declawsified is installed, it adds a `CLAUDE.md` section listing commands. Agent sees this as project context and can respond to "what commands are available?" naturally.
3. **Status line indicator**: A persistent UI element (Claude Code statusline, terminal prompt) showing currently active tags and linking to docs.

MVP ships with option 2; option 1 is post-MVP.

#### Backwards Compatibility

**If Declawsified is not installed**: Tags and commands are just text in the prompt. Harmless. The LLM treats `#project:auth-service` as a topic marker or ignores it. No breakage.

**If Declawsified is installed but tag namespace is unrecognized**: Logged as a signal, doesn't affect prompt or LLM behavior.

**If another tool also uses `#` tags in prompts** (e.g., a personal note-taking workflow): Both tools extract tags from the same prompt. Declawsified only consumes tags matching its namespace prefixes (`project:`, `activity:`, `domain:`, `phase:`). Non-matching tags are logged as signals but don't affect classification. No conflict.

#### Summary: The Design in One Table

| Concern | Resolution |
|---------|-----------|
| Sigil collision with agents | Use `#` (tags) and `!` (commands) -- both unclaimed |
| LLM misinterpretation | Declarative syntax only; worst case is model echoes the tag |
| Mid-prompt embeddability | `#tags` match twitter-text rules; work anywhere |
| Structured commands | `!commands` at start-of-line, Prow/GitLab pattern |
| Session continuity | Sticky tags with automatic invalidation signals |
| New projects | `!new-project` with driver→related pattern |
| Corrections | `!correct` feeds active learning |
| Errors | Never block prompt; fuzzy-match suggestions; signal-only logging |
| Discovery | `CLAUDE.md` + future hook-level `!help` |
| Privacy | Three modes: preserve / strip / normalize |
| Backwards compat | Tags are harmless text if Declawsified isn't installed |

### 2.12 Academic Foundations for This Design

| Source | Contribution to Design |
|--------|----------------------|
| **Ranganathan, Colon Classification (1933)** | PMEST facet framework: 5 independent dimensions covering any knowledge domain |
| **Reinhardt et al., "Knowledge Worker Roles and Actions" (2011)** | 13 knowledge actions empirically validated across 10 worker roles -- basis for our 10 universal activities |
| **O*NET Generalized Work Activities (DOL)** | 41 activities in 4 domains, government-validated, mapped to 867 occupations -- cross-validated our activity list |
| **UTBMS Activity Codes (ABA/ACCA)** | 28 billing activity codes, 25+ years in production at thousands of law firms -- validated that universal activities work across domains |
| **Anderson & Krathwohl, Revised Bloom's Taxonomy (2001)** | 6 cognitive levels x 4 knowledge types -- provides cognitive depth dimension mapped to activity types |
| **Davenport, "Thinking for a Living" (2005)** | 2x2 complexity/interdependence matrix for knowledge work -- informs our `phase` and complexity signals |
| **TaxoAdapt (ACL 2025)** | Density-based taxonomy expansion signals -- our within-facet evolution strategy |
| **TaxMorph (EACL 2026)** | 4 taxonomy refinement operations, LLM-driven, +2.9 F1 improvement -- our periodic refinement approach |
| **Workday Foundation Data Model** | Driver/related worktag pattern, 15 custom worktag types -- our project->team auto-population and custom facets |
| **PIFA / CascadeXML (eXtreme Multi-Label)** | Algorithmic balanced tree construction outperforms manual hierarchies -- our subcategory generation approach |
| **Miller/Cowan (cognitive load)** | 4-item working memory limit -- constrains us to 5 primary facets maximum |
| **Conventional Commits** | Community-adopted 10-type commit classification -- direct signal source for engineering pack |
| **GitClear/Pluralsight Flow** | Production auto-classification of commits into 4 work types from git signals alone -- validates signal-based classification |
| **MemPalace (2025)** | Hierarchical structure improved retrieval by 34% over flat -- evidence that structured organization matters even for simple lookups |
| **Slot-filling paradigm (ACM Computing Surveys 2022)** | Multi-facet classification reframed as independent slot-filling -- our per-facet classifier architecture |
| **Multi-output classification (scikit-learn)** | Independent classifier per dimension, embarrassingly parallel -- our implementation pattern |
| **Cal Newport, "Deep Work" (2016)** | Deep/shallow work binary -- maps to cognitive complexity signal across all domains |
| **Gene Kim, "The Phoenix Project" (2013)** | 4 types of work (business projects, internal projects, changes, unplanned work) -- maps to our phase facet |

---

## 3. Classification Engine: Research & Approach

### 3.1 Academic Foundations

#### Three Canonical Approaches to Text Classification

| Approach | Description | Best For | Declawsified Fit |
|----------|-------------|----------|------------------|
| **Local (top-down)** | One classifier per level, cascade downward | Deep hierarchies (5+ levels) | Not needed |
| **Flat (big-bang)** | Single multi-class classifier over all labels | Small label spaces (<50) | Per-facet classifiers (10 values each) |
| **Global (structure-aware)** | Single model encoding hierarchy structure via GNNs, contrastive loss | Large hierarchies (100+ labels) | Future: domain pack sub-activities |

**Key models in the literature**: HTCInfoMax (NAACL 2021), HGCLR (ACL 2022), HiTIN (ACL 2023), HiGen (2025).

**Multi-output classification**: Each facet gets its own flat classifier (sklearn MultiOutputClassifier pattern). Research shows independent classifiers per dimension are competitive with joint models and far simpler to debug. Only add cross-facet correlation if inter-dimension dependencies are measured in real data (e.g., `artifact=test` strongly predicts `activity=verifying`).

#### Software Engineering Activity Classification

This is the closest academic analog to Declawsified's problem. Substantial prior work exists:

**The Lientz-Swanson taxonomy (1978)**: Corrective (bug fixing, 17.4%), Adaptive (new features, 18.2%), Perfective (improvements/refactoring, 60.3%). A 2003 replication found corrective maintenance 2-3x higher than originally reported.

**Conventional Commits specification**: Community standard pre-classifying commits: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`. When agents or developers use this convention, classification becomes trivial parsing.

**Keyword-based commit classification**: The `evidencebp/commit-classification` project achieved **93% accuracy** for corrective commit probability using just 20 keywords. **The single word "fix" is the strongest feature.**

**ML benchmarks for commit classification**:

| Method | Accuracy | F1 Score | Notes |
|--------|----------|----------|-------|
| Keyword dictionary (20 words) | ~65-70% | -- | Baseline, zero training |
| TF-IDF + Random Forest | ~60-75% | 0.759 (weighted) | word2vec + max aggregation |
| Source code changes + commit msg | ~76% | 0.63 Kappa | Project-agnostic |
| BERT + code changes (DNN) | 79.66% | 0.80 (macro) | Best pre-LLM result |

**Developer activity classification from IDE telemetry**: Minelli et al. found developers spend 70% of time on program comprehension. Damevski et al. used Hidden Markov Models on IDE actions to identify latent task states. Tool usage patterns are strong classification signals -- directly applicable to Declawsified.

### 3.2 Recommended Classification Architecture: Tiered Cascade

Academic literature on cascade classifiers supports a tiered approach where classifiers are applied sequentially, with each tier handling progressively harder cases.

#### Tier 1: Metadata Rules (zero cost, <0.1ms)

Signal-only classification without reading prompt content. Privacy-safe tier. Runs independently per facet.

**Activity facet signals**:

| Signal | Classification Rule | Precision | Coverage |
|--------|-------------------|-----------|----------|
| Git branch prefix `fix/`, `bug/`, `hotfix/` | investigating | ~95% | 10-15% of calls |
| Git branch prefix `feature/`, `feat/` | building | ~90% | 15-20% of calls |
| Git branch prefix `refactor/`, `cleanup/` | improving | ~90% | 3-5% of calls |
| File paths `*_test.*`, `*_spec.*`, `test_*` | verifying | ~95% | 5-10% of calls |
| File paths `Dockerfile`, `.github/`, `terraform/` | configuring | ~95% | 3-5% of calls |
| Tool pattern: Read-heavy, few Edits | researching | ~70% | 5-10% of calls |
| Tool pattern: test runner invocation | verifying | ~90% | 3-5% of calls |

**Artifact facet signals** (nearly 100% rule-based):

| Signal | Classification | Precision |
|--------|---------------|-----------|
| `.py`, `.ts`, `.go`, `.java` in tool calls | source | ~98% |
| `*_test.*`, `*_spec.*` in tool calls | test | ~99% |
| `.yaml`, `.toml`, `.env`, `*.config.*` | config | ~95% |
| `.md`, `.rst`, `README` | docs | ~98% |
| `Dockerfile`, `.github/`, `terraform/` | infra | ~97% |
| `.sql`, `migrations/`, `.csv` (data) | data | ~90% |

**Domain facet signals**: Primarily from LiteLLM team/user metadata (high confidence) with content-based fallback.

**Project facet signals**: See Section 2.5 detection algorithm.

**Expected Tier 1 coverage**: 25-35% of `activity` calls resolved. 70-80% of `artifact` calls resolved. 90%+ of `project` calls resolved (when metadata or git signals present).

#### Tier 2: Keyword/Content Classifier (<1ms)

For calls not resolved by Tier 1. Reads prompt content.

**Phase A (day 1, no training data)**: keyword matching for `activity` facet

| Activity | Keywords (high precision) |
|----------|--------------------------|
| investigating | error, bug, fix, traceback, stack trace, exception, crash, failing, broken, debug |
| building | implement, create, add, build, new feature, develop, scaffold, generate |
| improving | refactor, rename, extract, move method, clean up, restructure, optimize, simplify |
| verifying | test, spec, assert, coverage, mock, fixture, expect, validate, check |
| researching | explain, how does, what is, understand, explore, investigate, learn, read about |
| configuring | deploy, docker, ci, cd, pipeline, infrastructure, terraform, setup, install |
| planning | plan, design, architect, roadmap, spec, strategy, outline, propose |
| communicating | document, write up, summarize, draft email, describe, explain to, changelog |
| reviewing | review, check, audit, evaluate, approve, feedback, critique, assess |
| coordinating | coordinate, sync, delegate, assign, prioritize, schedule, align |

**Expected accuracy**: 55-70% (keyword overlap between categories limits recall). Works identically for all domains -- the keywords are activity-oriented, not domain-specific.

**Phase B (week 2+, with training data)**: TF-IDF + Logistic Regression per facet

- Independent classifier per facet (MultiOutputClassifier pattern)
- Trains in <1 second per facet on a laptop
- Inference <1ms per classification across all facets
- Expected accuracy: 82-86% per facet with 200-500 labeled examples per value
- Library: scikit-learn, zero GPU required

**Phase C (month 2+, with more data)**: SetFit or Sentence Transformers + KNN

- SetFit achieves 92.7% accuracy with just 8 examples per class (outperforms GPT-3)
- Trains in 30 seconds per facet
- Inference: 5-15ms on CPU
- Expected accuracy: 85-92% per facet

#### Tier 3: LLM Micro-Classifier (~200ms)

For genuinely ambiguous cases where Tiers 1-2 have low confidence.

**Model**: GPT-4.1-nano ($0.000058/call) or Gemini 2.0 Flash Lite ($0.000044/call)

**Prompt template** (multi-facet slot-filling):
```
System: Classify this AI agent interaction by filling each slot.
Return JSON with exactly these fields:

- activity: one of [investigating, building, improving, verifying, researching,
  planning, communicating, configuring, reviewing, coordinating]
- domain: one of [engineering, research, legal, marketing, finance, product,
  design, security, operations, support]
- phase: one of [discovery, planning, implementation, review, deployment, maintenance]
- activity_confidence: float 0-1
- domain_confidence: float 0-1

Context:
- Branch: {branch_name}
- Files touched: {file_paths}
- Tools used: {tool_names}
- Team/user metadata: {team_info}
- First 200 chars of user prompt: {prompt_snippet}
```

**Expected accuracy**: 90-95% for `activity`, 85-90% for `domain`, 75-85% for `phase`. Multi-slot filling in a single LLM call is more efficient than separate calls per facet.

#### Cascade Flow (Per Facet, Parallel Across Facets)

```
Call arrives -> All facet extractors run in parallel
  |
  | ARTIFACT facet          ACTIVITY facet           DOMAIN facet         PROJECT facet
  | (almost always          (cascade)                (cascade)            (mostly rules)
  |  rule-based)
  |                          |                        |
  | file path rules   Tier 1: metadata rules   team/user metadata   git repo/workdir/tags
  | -> artifact=source       |                        |                    |
  |                    High conf? -> done        Known team? -> done  Signal found? -> done
  |                          |                        |                    |
  |                    Tier 2: keywords/ML      Tier 2: keywords     session continuity
  |                          |                        |                    |
  |                    High conf? -> done        High conf? -> done   -> project=X
  |                          |                        |
  |                    Tier 3: LLM micro-classifier (multi-slot)
  |                    -> fills activity + domain + phase in one call
```

**Key optimization**: When Tier 3 is needed, a single LLM call fills ALL remaining low-confidence facets simultaneously via slot-filling prompt. This avoids paying for separate LLM calls per facet.

**Combined expected accuracy**: 88-93% for `activity`, 85-90% for `domain`, 90-95% for `project` (when git signals present), 70-80% for `phase`.
**Combined expected cost**: $0.017-0.023 per 1,000 calls (only Tier 3 has non-zero cost, only invoked for 30-50% of calls).
**Combined expected latency**: <1ms average across all facets (60-70% resolved in Tiers 1-2), 200-400ms for calls requiring Tier 3.

### 3.3 Active Learning for Bootstrapping

**Core finding**: Active learning reduces labeling needs by 50-70% compared to random sampling.

**Bootstrap plan** (per facet, `activity` is the hardest -- other facets are mostly rule-based):

| Phase | Labeled Examples | Activity Accuracy | Domain Accuracy | Method |
|-------|-----------------|-------------------|-----------------|--------|
| Day 0 | 0 | 60-75% | 80-90% (from team metadata) | Rules + keywords |
| Week 1 | 80 (8 per activity) | 80-87% | 85-92% | SetFit few-shot per facet |
| Week 2-4 | 200-500 | 87-92% | 90-94% | Active learning per facet |
| Month 2+ | 1,000+ | 90-95% | 93-97% | Trained classifiers + corrections |

**Sampling strategies** (ranked by effectiveness):
1. **Uncertainty sampling**: Select examples where the current model is least confident.
2. **Diversity sampling**: Select examples maximally different from each other.
3. **DIST (combined)**: Combines uncertainty + diversity. Requires 30-50% fewer samples.
4. **LLM-guided selection**: Use LLM to identify most informative unlabeled examples. Converges 2.62x faster.

**Production library**: Small-Text (EACL 2023 Best Demo, MIT license) provides pool-based active learning for text classification integrating with scikit-learn, PyTorch, and HuggingFace Transformers.

**User correction flywheel (the Mint model)**: After a few iterations of human feedback, AI suggestions become accurate enough that humans transition from annotator to verifier. Research shows 58% productivity increase with adaptive human-in-the-loop systems. Design the tag schema to accept correction signals from day 1:
- `auto:work_type:debugging` (classifier output)
- `correction:work_type:feature-dev` (user override)
- Corrections become training signal for the next model iteration.

### 3.4 Goal/Task Detection

Beyond work-type classification, the second product pillar is grouping API calls into meaningful "work units" (goals/tasks).

**Signals available**:
- `prompt.id` from Claude Code OTel (correlates all tool calls + API requests from a single user prompt)
- `X-Claude-Code-Session-Id` header (groups all calls within a session)
- Git branch name (all work on `fix/auth-timeout` is one goal)
- Working directory (project identification)
- Temporal clustering (calls within a time window likely belong to same goal)

**Approach**: Session-level goal detection using a combination of:
1. Session ID grouping (trivial)
2. Branch name as goal proxy (trivial)
3. Temporal clustering with LLM-generated goal summaries (deferred to post-MVP)

---

## 4. Classification Technique Cost Analysis

### 4.1 Per-Call Cost Comparison

Assumptions: 500 token input (system + prompt snippet + metadata), 20 token output.

| Technique | Cost/call | Latency | Accuracy | Training Data Needed |
|-----------|-----------|---------|----------|---------------------|
| **Gemini 2.0 Flash Lite** | $0.000044 | 200-400ms | 88-93% | None |
| **GPT-4.1-nano** | $0.000058 | 200-400ms | 90-95% | None |
| **DeepSeek V3.2 (cached)** | $0.000022 | 300-800ms | 90-94% | None |
| **GPT-4.1-mini** | $0.000232 | 300-600ms | 92-96% | None |
| **Claude Haiku 4.5** | $0.000600 | 400-800ms | 92-96% | None |
| **DeepSeek V3.2** | $0.000148 | 300-800ms | 90-94% | None |
| **OpenAI embedding + KNN** | $0.000010 | 50-150ms | 82-90% | 120-300 examples |
| **Local embedding + KNN** | ~$0.00 | 5-15ms | 80-88% | 120-300 examples |
| **Sentence BERT + KNN** | ~$0.00 | 5-15ms | 85-92% | 300-1,200 examples |
| **TF-IDF + LogReg** | ~$0.00 | <1ms | 82-86% | 1,200-3,000 examples |
| **FastText** | ~$0.00 | <1ms | 78-85% | 600-3,000 examples |
| **Keywords/Regex** | $0.00 | <0.1ms | 55-70% | None |
| **Metadata decision tree** | $0.00 | <0.1ms | 60-75% | None |
| **Hybrid (rules + LLM)** | $0.000017-0.000023 | <1ms avg | 88-93% | None |

### 4.2 Monthly Cost at Scale

| Technique | 100/day | 1,000/day | 10,000/day |
|-----------|---------|-----------|------------|
| GPT-4.1-nano (pure) | $0.17 | $1.74 | $17.40 |
| Gemini Flash Lite (pure) | $0.13 | $1.32 | $13.20 |
| Hybrid (rules 60% + nano 40%) | $0.05 | $0.52 | $5.22 |
| Traditional ML (self-hosted) | ~$0.00 | ~$0.00 | ~$0.00 |
| Self-hosted GPU (always-on L4) | $350 | $350 | $350 |

### 4.3 Cost Decision

**Recommendation**: Hybrid (Tier 1 rules + Tier 2 keywords + Tier 3 GPT-4.1-nano/Gemini Flash Lite).

At $0.52/month for 1,000 calls/day, the classification cost is negligible compared to the LLM API calls being classified (which cost $0.01-$0.10+ each). The classification cost is <0.1% of the cost being tracked.

Self-hosted models (local 3B on GPU) are only cost-effective at >50K calls/day sustained, and add significant operational complexity. Not recommended for MVP.

### 4.4 Local Model Option (Privacy-Sensitive Deployments)

For enterprise users who cannot send prompt content to external APIs:

- **Tier 1 + Tier 2 only** (metadata rules + keywords/ML): 80-87% accuracy at $0.00/call
- **Tier 3 local via Ollama** (Phi-4-mini, Qwen 2.5 3B): 80-88% accuracy, 500-1500ms latency, runs on consumer hardware
- **Sentence Transformers locally** (all-MiniLM-L6-v2, 22MB model): 85-92% accuracy, 5-15ms latency, runs on CPU

---

## 5. Memory & Taxonomy System Research

### 5.1 Why This Matters

The classification taxonomy is itself a structured knowledge representation. LLM memory systems solve an analogous problem: organizing information into retrievable hierarchies that evolve over time. Key insights from memory system research directly apply to taxonomy design and maintenance.

### 5.2 Key Systems Analyzed

#### MemPalace (2025-2026, open-source)

Organizes information into a navigable spatial hierarchy:
- **Wings** (top-level containers) -> **Rooms** (subject divisions) -> **Halls** (memory types) -> **Closets** (summaries) -> **Drawers** (verbatim originals) -> **Tunnels** (cross-wing connections)
- Progressive retrieval: L0 (~50 tokens, identity) -> L1 (~120 tokens, critical facts) -> L2 (on-demand room recall) -> L3 (full semantic search)
- **Structure improved retrieval by 34 percentage points** over flat semantic search (60.9% to 94.8% on 22,000+ memories)
- GitHub: `milla-jovovich/mempalace`

**Relevance to classification**: The wing/room/hall structure maps directly to work-type/subcategory/signal-type. Progressive loading (cheap signals first, expensive LLM classification only when needed) mirrors our tiered cascade.

#### Aeon (January 2026)

Neuro-symbolic cognitive OS with:
- **Atlas**: Hierarchical spatial index over embeddings using Greedy SIMD Descent with branching factor ~64. O(log_B M) lookup, <2.5ms latency at 1M nodes.
- **Semantic Lookaside Buffer**: 64-entry ring buffer exploiting "semantic inertia" (adjacent queries are semantically close). 85%+ hit rate, reduces average latency to 0.42ms.

**Relevance**: The semantic cache concept directly applies to classification. Sequential API calls from the same agent session are likely doing the same type of work. Caching the classification for recent calls and applying it to semantically similar subsequent calls would dramatically reduce LLM fallback invocations.

#### MemGPT/Letta (production-grade, 16K+ stars)

Three-tier OS-inspired architecture:
- **Core Memory** (in-context, ~2K chars): actively edited by the agent via tool calls
- **Recall Memory**: conversation history with search
- **Archival Memory**: vector DB for long-term storage

**Relevance**: The three-tier model maps to our classification approach: core (rules/heuristics always in-memory), recall (recent classification history for temporal patterns), archival (training data store for model retraining).

#### Mem0 (knowledge graph + vectors)

Dual-store extracting atomic facts via entity extraction -> relationship extraction pipeline. Stores in both vector DB and knowledge graph (Neo4j/Memgraph).

**Relevance**: The entity-relationship extraction pipeline could be adapted for goal detection: extract entities (files, functions, bugs) and relationships (modifies, fixes, creates) from API call metadata to build a work-unit graph.

#### A-MEM (NeurIPS 2025)

Zettelkasten-inspired connected notes. New memories trigger "memory evolution" -- updating descriptions and attributes of linked existing memories. Creates a self-refining knowledge network.

**Relevance**: When a new classification pattern is detected (e.g., a novel tool usage pattern), it should trigger refinement of descriptions and boundaries of nearby existing categories. The taxonomy should evolve, not just grow.

### 5.3 Taxonomy Management Techniques

#### TnT-LLM (Microsoft, KDD 2024)

Iterative taxonomy generation: process minibatches of 200 summaries sequentially. Each batch refines the taxonomy -- analogous to SGD where the taxonomy is the parameter vector.

**Application**: Periodically feed batches of recent classified API calls to an LLM. Ask it to evaluate whether the current taxonomy still fits or needs adjustment. Automate taxonomy health checks.

#### TaxoAdapt (ACL 2025)

Dynamic taxonomy adaptation using expansion signals:
- **Density threshold** (leaf has >= N examples): triggers depth expansion (add subcategories)
- **Unmapped density** (examples assigned to parent but not matching children): triggers width expansion (add siblings)
- Caps at depth L=2 (3 total levels). Produces taxonomies 26.5% more granularity-preserving and 50.4% more coherent than baselines.

**Application**: When "debugging" accumulates thousands of classified calls that cluster into distinct subgroups (error-tracing, performance-profiling, integration-debugging), auto-expand.

#### TaxMorph (EACL 2026)

Four refinement operations: rename, rearrange, generate intermediate nodes, merge. Key finding: **taxonomies refined to align with where the classifier actually confuses categories perform better** than human-intuitive hierarchies (+2.9 F1).

**Application**: Analyze classifier confusion matrix. If "refactoring" and "feature-dev" are frequently confused, consider merging them or adding clarifying subcategories at the boundary.

### 5.4 Practical Insights for Declawsified

1. **Hierarchical structure improves accuracy** -- MemPalace's 34% improvement over flat search is strong evidence. Even if we start with flat classification, organizing the training data and rules hierarchically matters.

2. **Semantic caching** (Aeon's SLB) should be implemented for sequential calls. If the last 5 API calls from session X were classified as "debugging," the 6th is very likely "debugging" too. A simple cache hit avoids Tier 3 entirely.

3. **Taxonomy evolution should be data-driven** (TaxoAdapt, TaxMorph) not hand-crafted. Set density thresholds and let the system tell you when to split or merge categories.

4. **Cross-category connections** (MemPalace's "tunnels") model real work patterns: debugging sessions that become refactoring, testing that reveals bugs, research that leads to feature development. Track category transitions within sessions as a signal.

5. **Multi-generational consolidation** prevents category drift. When merging similar subcategories, use vector clustering first (fast, no LLM), then LLM-gated verification (ensures nuance is preserved).

---

## 6. Execution Steps

### Phase 0: Project Setup (Days 1-2)

- [ ] Initialize Python project with `pyproject.toml`
- [ ] Set up development LiteLLM instance (Docker Compose)
- [ ] Verify `async_logging_hook` callback receives expected data
- [ ] Create project structure:
  ```
  declawsified/
    src/
      declawsified/
        __init__.py
        classifier.py          # Main AutoClassifier(CustomLogger)
        prompt/
          __init__.py
          parser.py            # Hashtag + !command extraction (pure regex)
          commands.py          # Command registry and validation
          modes.py             # preserve / strip / normalize modes
          fuzzy.py             # Levenshtein-based typo suggestions
        facets/
          __init__.py
          base.py              # Base FacetExtractor interface
          agent.py             # Facet 0: agent identification (trivial)
          domain.py            # Facet 1: organizational domain
          activity.py          # Facet 2: work activity type
          project.py           # Facet 3: project detection
          artifact.py          # Facet 4: artifact type
          phase.py             # Facet 5: work lifecycle phase
        tiers/
          __init__.py
          rules.py             # Tier 1: metadata rule engine
          keywords.py          # Tier 2A: keyword matching
          ml_classifier.py     # Tier 2B: ML classifier (TF-IDF/SetFit)
          llm_classifier.py    # Tier 3: LLM micro-classifier (slot-filling)
        packs/
          __init__.py
          base.py              # Pack interface + signal inventory schema
          detector.py          # Pack signal scoring engine
          state_machine.py     # INACTIVE/SUGGESTED/ACTIVE transitions
          definitions/
            engineering.yaml   # Signal inventory + sub-activity taxonomy
            legal.yaml         # UTBMS codes + legal signal inventory
            marketing.yaml     # Marketing vocabulary + sub-activities
            research.yaml      # Academic research signals
            finance.yaml       # Finance/accounting signals
            personal.yaml      # Personal/education signals
        taxonomy.py            # Taxonomy definitions, evolution, profiles
        session.py             # Session cache + sticky tag state
        cache.py               # Classification semantic cache
        config.py              # Configuration, profiles, thresholds
    tests/
    docs/
  ```

### Phase 1: Prompt Parser & Core Facet Extractors (Days 3-11)

**Prompt Parser** (critical, days 3-4)
- [ ] Implement hashtag extraction using twitter-text-derived regex
  - Support `#value`, `#ns:value`, `#ns/sub/value` (nested)
  - Unicode-aware, boundary-respecting
  - Case-insensitive, non-numeric requirement
- [ ] Implement `!command` extraction with line-anchored regex (`(?m)^!...`)
- [ ] Implement command registry for MVP vocabulary:
  - `!project`, `!new-project`, `!activity`, `!domain`, `!phase`, `!goal`
  - `!correct`, `!tag`, `!untag`, `!no-classify`, `!help`
- [ ] Implement three prompt modes: `preserve`, `strip`, `normalize`
- [ ] Implement fuzzy-match suggestions (Levenshtein >= 0.85) for typos
- [ ] Implement namespace routing: tags with known facet namespaces become explicit overrides; unknown tags become freeform signals
- [ ] Write pure-function tests (no LLM, deterministic)
- [ ] Verify LLM safety: manually test that preserved tags don't trigger unintended agent behavior

**Facet 0: Agent** (trivial, day 5)
- [ ] Extract agent identity from request headers, API base URL, user-agent
- [ ] Extract model name from `standard_logging_object`
- [ ] Always 100% confidence, pure rule-based

**Facet 3: Project** (critical, days 5-7)
- [ ] Implement project detection algorithm (Section 2.5):
  - Priority 0: In-prompt `!project` / `#project:X` (from parser)
  - Priority 1: Explicit tags in request headers
  - Priority 2: LiteLLM team/key mapping
  - Priority 3: Git repository name from metadata
  - Priority 4: Git branch ticket references (PROJ-123 patterns)
  - Priority 5: Working directory path extraction
  - Priority 6: Ticket references in prompt text
  - Priority 7: Session continuity (inherit from previous call)
- [ ] Implement `!new-project` registration with driver->related population
- [ ] Implement auto-discovery mode (no registry -> report detected projects)
- [ ] Implement session cache with invalidation signals (branch change, workdir change, 30min gap)
- [ ] Implement project registry YAML format (optional, user-provided)
- [ ] Write tests with realistic git/directory signals + in-prompt commands

**Facet 4: Artifact** (mostly rule-based, days 7-8)
- [ ] Build file extension -> artifact type mapping
- [ ] Extract file paths from tool call metadata in prompt/response
- [ ] Handle multi-artifact calls (touching both source and test files -> tag both)
- [ ] Write tests

**Facet 2: Activity** (the hard one, days 7-11)
- [ ] Tier 1 rules: git branch prefix, tool patterns, file path patterns
- [ ] Tier 2A keywords: 10 keyword dictionaries (see Section 3.2), weighted matching
- [ ] Implement confidence scoring and tier routing
- [ ] Implement `!activity` / `#activity:X` override (from prompt parser)
- [ ] Implement privacy-safe config: `read_prompt_content: bool`
- [ ] Write tests with representative examples for all 10 activity types

**Facet 1: Domain** (days 9-11)
- [ ] Implement team/user metadata extraction (primary signal, high confidence)
- [ ] Implement content-based domain classification (Tier 2 keywords for 10 domains)
- [ ] Implement project registry -> domain mapping (when available)
- [ ] Implement `!domain` / `#domain:X` override
- [ ] Write tests

**Facet 5: Phase** (days 10-11)
- [ ] Implement session-level pattern analysis (read:write ratio, file creation patterns)
- [ ] Implement simple heuristics (new branch = implementation, review tools = review)
- [ ] Implement `!phase` / `#phase:X` override
- [ ] Mark as lowest-confidence facet, acceptable to omit
- [ ] Write tests

### Phase 2: Tier 3 - LLM Multi-Slot Classifier (Days 12-15)

- [ ] Implement multi-facet slot-filling prompt (single LLM call fills activity + domain + phase)
- [ ] Implement configurable model (default: GPT-4.1-nano)
- [ ] Implement prompt caching strategy (system prompt identical across calls)
- [ ] Add timeout and graceful degradation (if LLM is slow, use Tier 2 results)
- [ ] Add cost tracking for the classifier itself (meta: track how much the tracker costs)
- [ ] Implement local model option via Ollama for privacy-sensitive deployments
- [ ] Write tests with expected slot-filling outputs

### Phase 3: Integration & Multi-Facet Tag Writing (Days 16-19)

- [ ] Implement the full `AutoClassifier(CustomLogger)` class
- [ ] Wire up all facet extractors to run in parallel
- [ ] Implement confidence-based Tier routing per facet
- [ ] Write multi-dimensional tags to `request_tags`:
  - `auto:agent:claude-code`, `auto:agent:model:claude-sonnet-4-5`
  - `auto:domain:engineering`
  - `auto:activity:investigating`
  - `auto:project:auth-service`
  - `auto:artifact:source`
  - `auto:phase:maintenance`
  - `auto:confidence:activity:0.91`, `auto:confidence:domain:0.95`
  - `auto:classifier:activity:tier1`, `auto:classifier:version:0.1.0`
- [ ] Write extended metadata to `spend_logs_metadata` (classification reasoning, signals used)
- [ ] Test end-to-end with LiteLLM proxy: verify tags appear in SpendLogs DB
- [ ] Verify queryability via `/spend/tags` and `/spend/logs` APIs
- [ ] Verify each facet can be filtered independently

### Phase 4: Domain Packs, Auto-Detection & Profiles (Days 20-24)

- [ ] Implement domain pack loading system (YAML-based pack definitions)
- [ ] Ship engineering pack: Conventional Commits mapping, GitClear categories
- [ ] Ship legal pack: UTBMS activity code mapping
- [ ] Ship marketing pack: channel/campaign/content-type sub-activities
- [ ] **Implement pack signal scoring engine** (Section 2.4 subsection):
  - Per-pack signal inventories (strong/medium/weak/exclusion)
  - Score computation with TF-IDF-style weighting
  - Exclusion signal handling
- [ ] **Implement pack activation state machine** (INACTIVE → SUGGESTED → ACTIVE):
  - Rolling window of last 20/50/100 calls per pack
  - Threshold-based transitions (0.7 to suggest, 0.3 to deactivate)
  - 30-day cooldown after user declines
- [ ] **Implement multi-pack operation**:
  - Multiple packs can be simultaneously active
  - Per-call pack resolution: dominant pack wins, close calls tag both
  - Per-project pack scoping via project registry
- [ ] **Implement pack auto-suggestion UX**:
  - Out-of-band notification (never inline in LLM prompt)
  - User commands: `!pack`, `!pack off`, `!pack-default`, `!pack-auto`, `!pack-no-thanks`
- [ ] **Implement project-level pack inference**:
  - First 10 calls of new project determine initial packs
  - Fall back to global defaults if no clear signal
- [ ] Implement profile selection: solo-developer, engineering-team, enterprise-tech, legal, etc.
- [ ] Each profile configures: active packs, primary view, facet visibility, project detection mode
- [ ] Write tests for:
  - Pack loading and profile switching
  - Pack signal scoring (synthetic prompts with known signals)
  - Activation state transitions over simulated call streams
  - Multi-pack conflict resolution
  - Per-project pack scoping

### Phase 5: Semantic Cache & Session Intelligence (Days 25-27)

- [ ] Implement session-level classification cache (Aeon SLB concept):
  - Consecutive calls from same session with same facet values -> cache hit
  - Dramatically reduces Tier 3 invocations (85%+ hit rate expected)
- [ ] Cache invalidation: session change, branch change, tool pattern shift, working directory change
- [ ] Implement session-level project tracking (dominant project per session)
- [ ] Implement cross-facet correlation check (optional):
  - If artifact=test AND activity=investigating -> suggest activity=verifying
  - Only apply when correlation improves confidence
- [ ] Measure cache hit rate and latency improvement

### Phase 6: Data Collection & Active Learning (Days 28-32)

- [ ] Implement classification logging per facet: store (facet, input_signals, output, tier, confidence)
- [ ] Design correction feedback mechanism:
  - Tag format: `correction:activity:building` (overrides `auto:activity:investigating`)
  - Corrections stored as labeled training data per facet
- [ ] Implement active learning pipeline:
  - Identify lowest-confidence classifications per facet
  - Present to user for correction (prioritize highest-value facets: activity, domain)
  - Store corrections as labeled training data
- [ ] When 80+ labeled examples accumulated (8 per activity value), train SetFit model for activity facet
- [ ] Implement auto-discovery report: "This week's project distribution: auth-service 42%, frontend 28%, ..."

### Phase 7: Testing & Benchmarking (Days 33-37)

- [ ] Build comprehensive test suite:
  - Unit tests for prompt parser (hashtags, commands, edge cases, fuzzy match)
  - Unit tests for each facet extractor
  - Unit tests for each domain pack
  - Integration tests with mock LiteLLM callback data
  - End-to-end tests with real LiteLLM proxy
  - Profile-specific test suites (solo dev, enterprise, legal)
  - **LLM safety tests**: verify that preserved tags don't trigger unintended agent behavior across Claude Code, Codex, Copilot (manually verified, document findings)
- [ ] Create per-facet accuracy benchmark:
  - Manually classify 200-500 real API call logs across all facets
  - Measure accuracy per facet, per tier, and overall
  - Targets: activity >= 85%, domain >= 85%, project >= 90%, artifact >= 95%
- [ ] Performance benchmarking:
  - Latency: <5ms average across all facets (including amortized Tier 3)
  - Memory: <50MB for the classifier process
  - No measurable impact on LiteLLM proxy throughput
- [ ] Document: configuration options, profile selection, domain pack reference, deployment guide

### Phase 8: Open Source Release (Days 38-42)

- [ ] Write README with:
  - One-line installation
  - 5-minute quickstart (add to existing LiteLLM proxy)
  - Profile selection guide: "I'm a solo dev" vs "I run an engineering team" vs "I'm at an enterprise"
  - Domain pack documentation
  - Accuracy benchmarks per facet
  - Architecture explanation (faceted classification, tiered cascade)
- [ ] Publish to PyPI
- [ ] Create GitHub repository with CI/CD (tests, linting)
- [ ] Write announcement post (target: r/ClaudeAI, r/LocalLLaMA, HN, r/FinOps)
- [ ] Submit to LiteLLM community plugins / docs

### Post-MVP: Accuracy & Taxonomy Evolution (Month 2-3)

- [ ] Accumulate labeled data via active learning + user corrections per facet
- [ ] Train dedicated ML classifiers (TF-IDF+LogReg or SetFit) for Tier 2B per facet
- [ ] Analyze per-facet confusion matrices, refine values per TaxMorph approach
- [ ] Implement TaxoAdapt-style auto-expansion: when activity values become overloaded, suggest subcategories
- [ ] Add session-level classification (classify entire sessions, not just individual calls)
- [ ] Add temporal pattern detection (Markov chains on activity transitions within sessions)
- [ ] Add cross-facet correlation modeling (ClassifierChain if measured correlations are strong)
- [ ] Ship additional domain packs: finance, research, personal/education

### Post-MVP: Platform Expansion (Month 3-6)

- [ ] Langfuse external eval pipeline adapter (batch/post-hoc faceted classification)
- [ ] Portkey webhook guardrail integration
- [ ] Standalone sidecar service (read from any source, write to any sink)
- [ ] OTel Collector processor (universal)
- [ ] Dashboard / reporting UI with multi-facet filtering
- [ ] Cross-customer anonymized pattern analysis (the CrowdStrike flywheel)

---

## 7. Success Criteria & Metrics

### MVP Success (Day 42)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Activity facet accuracy | >= 85% | Manual benchmark of 200+ real calls |
| Domain facet accuracy | >= 85% | Manual benchmark (where team metadata available: >= 95%) |
| Project detection rate | >= 90% | % of calls with non-"unattributed" project (when git signals present) |
| Artifact facet accuracy | >= 95% | Rule-based, nearly deterministic |
| Prompt parser accuracy | 100% | Deterministic regex, must be exact |
| LLM safety of preserved tags | No unintended behavior | Manual verification across 3 agents |
| In-prompt override respect | 100% | User tags override auto-detection |
| Latency impact | < 5ms average | Timer around classifier in callback |
| Setup time | < 5 minutes | From existing LiteLLM proxy to working classifier |
| Domain packs shipped | >= 3 | Engineering, Legal, Marketing at minimum |
| Pack auto-suggestion accuracy | >= 80% | % of suggested packs that users accept |
| Pack false-positive rate | < 5% | Packs suggested that don't match user's work |
| Zero-config startup | Works with no setup | User installs, types first prompt, gets classification |
| Profiles shipped | >= 4 | Solo dev, engineering team, enterprise, legal |
| Dependencies | < 8 Python packages | Keep lightweight |

### Month 3 Success

| Metric | Target | Measurement |
|--------|--------|-------------|
| Activity facet accuracy | >= 90% | Expanded benchmark + user correction data |
| Domain facet accuracy | >= 92% | With trained ML classifier |
| GitHub stars | >= 100 | Organic adoption signal |
| Active users | >= 10 | Distinct LiteLLM installations using the plugin |
| Domain packs shipped | >= 6 | All planned packs |
| Enterprise pilots | >= 2 | Multi-team organizations using domain+project facets |

### Accuracy Threshold

Research confirms **85-90% is the adoption threshold**, not 99%:
- Mint's auto-categorization: 85-90% accuracy drove 68% higher retention vs manual tracking
- Users accept correcting 10-15% if the alternative is 100% manual tagging
- Below 80%: users abandon the tool (correction burden too high)
- Above 95%: diminishing returns on improvement effort

---

## Appendix A: Academic References

### Hierarchical Text Classification
- "Revisiting Hierarchical Text Classification: Inference and Metrics" (2024) -- arxiv.org/html/2410.01305v1
- "HTC vs XML: Two Sides of the Same Medal" (2024) -- arxiv.org/html/2411.13687v2
- "Hierarchical Text Classification and Its Foundations: A Review" (MDPI 2024)
- "Hierarchical Text Classification Using Black Box LLMs" (2025) -- arxiv.org/html/2508.04219v1

### Software Engineering Activity Classification
- Lientz & Swanson, "Software Maintenance Management" (1980) -- foundational taxonomy
- Schach et al., "Determining the Distribution of Maintenance Categories" (Empirical SE 2003)
- evidencebp/commit-classification -- 93% accuracy on corrective commit detection
- Conventional Commits Specification -- conventionalcommits.org

### Active Learning
- "Small-Text: Active Learning for Text Classification in Python" (EACL 2023 Best Demo)
- "SetFit: Efficient Few-Shot Learning Without Prompts" (HuggingFace)
- "Enhancing Text Classification through LLM-Driven Active Learning" (2024)
- "Cold-start Active Learning through Self-supervised Language Modeling" (EMNLP 2020)

### Memory Systems
- MemPalace -- github.com/milla-jovovich/mempalace
- Aeon neuro-symbolic cognitive OS -- arxiv.org/abs/2601.15311
- MemGPT/Letta -- docs.letta.com
- Mem0 -- arxiv.org/abs/2504.19413
- A-MEM Zettelkasten -- arxiv.org/abs/2502.12110 (NeurIPS 2025)
- HippoRAG -- arxiv.org/abs/2405.14831 (NeurIPS 2024)

### Taxonomy Management
- TnT-LLM -- arxiv.org/abs/2403.12173 (KDD 2024)
- TaxoAdapt -- arxiv.org/abs/2506.10737 (ACL 2025)
- TaxMorph -- arxiv.org/html/2601.18375 (EACL 2026)
- OLLM ontology learning -- github.com/andylolu2/ollm (NeurIPS 2024)

### Faceted Classification & Knowledge Work Taxonomies
- Ranganathan, "Colon Classification" (1933) -- PMEST faceted classification theory
- Reinhardt et al., "Knowledge Worker Roles and Actions" (Knowledge and Process Management, 2011) -- 10 roles, 13 knowledge actions
- O*NET Generalized Work Activities -- onetonline.org/find/descriptor/browse/Work_Activities/
- SOC 2018 Major Groups -- bls.gov/soc/2018/major_groups.htm
- UTBMS Activity Codes -- utbms.com/aba-activity-codes/
- Anderson & Krathwohl, "Revised Bloom's Taxonomy" (2001) -- 6 cognitive x 4 knowledge dimensions
- Davenport, "Thinking for a Living" (2005) -- Complexity/Interdependence knowledge work matrix
- Cal Newport, "Deep Work" (2016) -- Deep/shallow work classification
- Gene Kim, "The Phoenix Project" (2013) -- 4 types of work in DevOps
- McKinsey Global Institute, "A Future That Works" (2017) -- 7 work activity categories
- Workday Foundation Data Model -- driver/related worktag architecture
- GitClear/Pluralsight Flow -- production auto-classification of commits
- Conventional Commits -- conventionalcommits.org
- SKOS Reference -- w3.org/TR/skos-reference/
- DOLCE Upper Ontology -- arxiv.org/pdf/2308.01597
- Faceted Classification Theory -- berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/
- Miller, "The Magical Number Seven" (1956) -- cognitive load limits
- Cowan, "The Magical Number Four" (2001) -- revised working memory capacity

### Multi-Output Classification
- scikit-learn MultiOutputClassifier -- sklearn.org/stable/modules/generated/sklearn.multioutput.MultiOutputClassifier.html
- ClassifierChain for correlated dimensions -- sklearn.org/stable/modules/generated/sklearn.multioutput.ClassifierChain.html
- Joint Intent Detection and Slot Filling Survey (ACM Computing Surveys 2022)
- Multi-Task Learning with shared encoder -- ruder.io/multi-task/
- Multi-Dimensional Classification (Neurocomputing 2023) -- cross-dimension correlation modeling

### In-Prompt Command Syntax
- Slack Slash Commands -- docs.slack.dev/interactivity/implementing-slash-commands/
- Kubernetes Prow ChatOps -- docs.prow.k8s.io/docs/components/plugins/approve/approvers/
- Probot Commands -- github.com/probot/commands -- Line-anchored `/command` pattern
- GitLab Quick Actions -- docs.gitlab.com/user/project/quick_actions/
- Jira Smart Commits -- support.atlassian.com/jira-software-cloud/docs/process-issues-with-smart-commits/
- Twitter-text regex reference -- github.com/twitter/twitter-text -- Hashtag standard
- Obsidian Tags -- help.obsidian.md/tags -- Nested tag pattern with `/`
- Hubot / Errbot / Lita -- classic IRC-style `!` bot command precedent
- Claude Code Hooks reference -- code.claude.com/docs/en/hooks -- `UserPromptSubmit` event
- Claude Code in Slack -- code.claude.com/docs/en/slack -- Production intent routing classifier
- OWASP LLM01:2025 Prompt Injection -- genai.owasp.org/llmrisk/llm01-prompt-injection/
- "I Sent the Same Prompt Injection to Ten LLMs. Three Complied" -- instruction-shaped token risk analysis
- LLMON: LLM-native markup language -- arxiv.org/html/2603.22519v1 -- structured metadata in prompts

### Cost/Model Benchmarks
- OpenAI Pricing -- developers.openai.com/api/docs/pricing
- Anthropic Pricing -- platform.claude.com/docs/en/about-claude/pricing
- Gemini API Pricing -- ai.google.dev/gemini-api/docs/pricing
- DeepSeek Pricing -- api-docs.deepseek.com/quick_start/pricing
- Lambda Labs GPU Pricing -- lambda.ai/pricing
- RunPod Serverless Pricing -- docs.runpod.io/serverless/pricing
