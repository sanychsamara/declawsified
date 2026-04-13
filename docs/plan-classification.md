# Declawsified Classification Design

**Scope:** Design of the classification intelligence layer -- the taxonomy, the classifier engine, the cost model, and the memory/taxonomy research informing the design. This is a companion to `plan.md` which covers architecture, UI surfaces, repository structure, execution steps, and success metrics.

**Companion doc:** [`plan.md`](./plan.md) -- top-level architecture, repo structure, execution plan, success criteria.

---
## EDITOR TODO 

1. Extract "Personal/Life" classification from "Packs" into it's own "context" classification (personal vs business), that should be available by default. Unify language across personal and business classification. Replace "area" with "project" for describing areas of interest in personal context. 

2. Drop personal goals detection completely. 

3. Drop "Privacy Architecture for Personal Classification" and all privacy related discussion completely.

4. Drop "Personal Pack UI Considerations"

5. Drop "Facet 4: `artifact`" completely - this is too granular classification, no value

6. Rename " Primary Discovery Mechanism: Tree-Path Classification Against a Hybrid Taxonomy" to "Personal Projects Discovery". Outline multiple possible options (some of them are shared from business projects discovery) with one of them being current "Tree-Path Classification Against a Hybrid Taxonomy"

7. Add explicit section on "Business Project Discovery", summarize all explored strategies during research (using working dir, names from shared documents, manual override)

8. Create new section "Project Discovery", move Personal Project Discovery and Business Project Discovery there. Rewrite to remove duplicates, extract shared section that applies to both contexts

9. Create new section for each of other facets discovery "Activity Discovery", "Domain Discovery"

10. Rewrite introduction to "Classification Taxonomy Design", outlining core principles (and decision already made during research phase), which are:

- No single taxonomy can satisfy all use cases
- Faceted classification with 5-6 fixed taxonomies is a reasonable start
- Domain classification changes activity facet taxonomy with "domain packs" 
- Context (personal vs business) changes how projects are being discovered

11. Delete "1.1 The Problem with a Single Flat Taxonomy" after creating introduction section with core design principals

12. Move all details about domains packs into a separate document called plan-domain-packs.md



## Table of Contents

1. [Classification Taxonomy Design](#1-classification-taxonomy-design)
   - [1.1 The Problem with a Single Flat Taxonomy](#11-the-problem-with-a-single-flat-taxonomy)
   - [1.2 Faceted Classification: The Architectural Foundation](#12-faceted-classification-the-architectural-foundation)
   - [1.3 MVP Facet Schema (6 Dimensions)](#13-mvp-facet-schema-6-dimensions) -- context, domain, activity, project, artifact, phase
   - [1.4 Domain-Specific Activity Taxonomies (Industry Packs)](#14-domain-specific-activity-taxonomies-industry-packs) -- engineering, legal, marketing, research, finance, personal
   - [1.5 Automatic Project Detection](#15-automatic-project-detection)
   - [1.6 Multi-Dimensional Tag Output Format](#16-multi-dimensional-tag-output-format)
   - [1.7 The Combinatorial Power](#17-the-combinatorial-power-why-this-matters)
   - [1.8 Taxonomy Evolution Strategy](#18-taxonomy-evolution-strategy)
   - [1.9 Taxonomy Library: Starting Points by Setting](#19-taxonomy-library-starting-points-by-setting) -- solo dev, startup, enterprise, law firm, agency, university
   - [1.10 Cross-Dimensional Intelligence](#110-cross-dimensional-intelligence)
   - [1.11 In-Prompt Communication Layer](#111-in-prompt-communication-layer) -- `#tags` and `!commands` for power users
   - [1.12 Academic Foundations](#112-academic-foundations-for-this-design)
2. [Classification Engine: Research & Approach](#2-classification-engine-research--approach)
3. [Classification Technique Cost Analysis](#3-classification-technique-cost-analysis)
4. [Memory & Taxonomy System Research](#4-memory--taxonomy-system-research)

---
## 1. Classification Taxonomy Design

### 1.1 The Problem with a Single Flat Taxonomy

The original plan proposed 6 software engineering categories (debugging, feature-dev, refactoring, testing, research, devops). This fails on two fronts:

**It only serves individual software engineers.** At a company like Google or Meta, AI agents are used by legal teams drafting patents, marketing teams writing campaigns, researchers analyzing data, PMs coordinating across teams, security teams auditing code, and hardware engineers running simulations. A "debugging vs. feature-dev" taxonomy is invisible to 80% of knowledge workers.

**It collapses multiple independent dimensions into one.** A legal researcher debugging a contract analysis script is simultaneously doing: domain=Legal, activity=Debugging, project=Contract-Analyzer, artifact=Source, phase=Maintenance. Forcing this into a single "debugging" tag destroys the information that matters most to the CFO (Legal is spending $X on AI) and the engineering manager (debugging cost $Y this week).

### 1.2 Faceted Classification: The Architectural Foundation

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

**References**
- Ranganathan, "Colon Classification" (1933) -- PMEST faceted classification theory
- Faceted Classification Theory -- [berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/](https://berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/)
- SKOS Reference -- [w3.org/TR/skos-reference/](https://www.w3.org/TR/skos-reference/)
- DOLCE Upper Ontology -- [arxiv.org/pdf/2308.01597](https://arxiv.org/pdf/2308.01597)
- Miller, "The Magical Number Seven" (1956) -- cognitive load limits
- Cowan, "The Magical Number Four" (2001) -- revised working memory capacity

### 1.3 MVP Facet Schema (6 Dimensions)

Every API call is classified along all 6 dimensions simultaneously. Each facet has its own classifier, they run independently and in parallel.

```
API Call arrives
    |
    v
+-- Facet Extractors (independent, parallel) --------+
|                                                      |
|  [context_classifier]  -> context=business           |
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
  auto:context:business
  auto:agent:claude-code
  auto:domain:engineering
  auto:activity:debugging
  auto:artifact:source
  auto:project:auth-service
  auto:phase:maintenance
  auto:confidence:activity:0.91
  auto:confidence:phase:0.78
```

#### Facet 0: `context` -- Personal or Business (WHAT KIND OF USE)

This is the meta-facet. It runs first because it scopes the vocabulary of other facets (particularly `project` and `domain`). Same user, same machine can generate both personal and business calls; classifying each correctly unlocks every other facet.

**Values (MVP)**: `business`, `personal`.

**Why this matters**:
- `project=marathon-training` makes sense only when `context=personal`
- `project=auth-service` makes sense only when `context=business`
- Mixing them in the same bucket destroys every downstream report
- CFO wants business-only; individual users want personal-only

**Enabled by default.** Unlike domain packs (which are opt-in overlays), `context` classification is always on. A user doing only business work sees `context=business` on every call -- no harm done. A user with mixed use gets the split they need.

**Detection (signal-first, content-fallback)**:

| Signal | Direction | Strength |
|--------|-----------|----------|
| Time of day: 6pm-11pm local | personal | Medium |
| Time of day: 5am-8am local | personal | Weak |
| Day of week: Saturday/Sunday | personal | Strong |
| Working directory: `~/Documents/Personal/`, `~/Taxes/`, `~/Recipes/`, `~/Health/`, `~/Journal/`, `~/Finances/` | personal | Very Strong |
| Working directory: `~/dev/`, `~/src/`, `~/projects/`, `~/work/`, `/Users/*/Code/` | business | Very Strong |
| File types: `.py`, `.ts`, `.go`, `.rs`, `.java` | business | Strong |
| File types: `.md` (personal notes), `.docx` (non-legal), recipe formats | personal | Medium |
| No git repository in workdir | personal | Medium |
| Tool mix: Bash/Grep-heavy code work | business | Strong |
| Tool mix: Read/Write on prose, no Bash | personal | Medium |
| Account email domain (gmail, icloud, outlook) | personal | Medium |
| Account email domain (corporate) | business | Medium |
| Pronouns: "I/me/my/my wife/my kid" | personal | Strong (needs prompt reading) |
| Pronouns: "we/our team/our customer" | business | Strong (needs prompt reading) |

**Override via in-prompt command**: `!context personal` or `!context business` forces the classifier for the current call and session (see §1.11).

**Decision rule**: Sum weighted signals. If `personal_score > business_score + 0.3` -> `context=personal`. Otherwise -> `context=business` (the safer default for enterprise deployments). Ambiguous calls get tagged with lower confidence; users can correct via `!correct context=personal`.

See §1.4 for the personal-context project vocabulary (the 10 default life areas used as project identifiers when context=personal) and the tree-path discovery mechanism for growing that vocabulary.

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

| Original    | New Universal   | Notes                                          |
| ----------- | --------------- | ---------------------------------------------- |
| debugging   | `investigating` | Same action, domain-neutral name               |
| feature-dev | `building`      | Same action, domain-neutral name               |
| refactoring | `improving`     | Same action, domain-neutral name               |
| testing     | `verifying`     | Same action, domain-neutral name               |
| research    | `researching`   | Same action, already domain-neutral            |
| devops      | `configuring`   | Same action, domain-neutral name               |
| (new)       | `planning`      | Was missing -- critical for PM, legal, product |
| (new)       | `communicating` | Was missing -- significant AI use case         |
| (new)       | `reviewing`     | Was missing -- code review, document review    |
| (new)       | `coordinating`  | Was missing -- cross-team work, project mgmt   |

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

**Personal-context values**: When `context=personal` (§1.3 Facet 0), `project` values are personal projects: default life areas (health, finances, etc.) or user-declared personal initiatives (marathon-training, home-renovation-2026). Same facet, different vocabulary. See §1.4 Personal Context subsection for the default values and discovery mechanism.

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

**References**
- Reinhardt et al., "Knowledge Worker Roles and Actions" (Knowledge and Process Management, 2011) -- 10 roles, 13 knowledge actions, basis for our universal activities
- O*NET Generalized Work Activities -- [onetonline.org/find/descriptor/browse/Work_Activities/](https://www.onetonline.org/find/descriptor/browse/Work_Activities/)
- SOC 2018 Major Groups (US BLS) -- [bls.gov/soc/2018/major_groups.htm](https://www.bls.gov/soc/2018/major_groups.htm)
- Anderson & Krathwohl, "Revised Bloom's Taxonomy" (2001) -- 6 cognitive x 4 knowledge dimensions
- Davenport, "Thinking for a Living" (2005) -- complexity/interdependence matrix
- Cal Newport, "Deep Work" (2016) -- deep/shallow work classification
- Gene Kim, "The Phoenix Project" (2013) -- 4 types of work in DevOps
- McKinsey Global Institute, "A Future That Works" (2017) -- 7 work activity categories
- Workday Foundation Data Model -- driver/related worktag architecture
- scikit-learn MultiOutputClassifier -- [sklearn.org/stable/modules/generated/sklearn.multioutput.MultiOutputClassifier.html](https://scikit-learn.org/stable/modules/generated/sklearn.multioutput.MultiOutputClassifier.html)
- ClassifierChain (correlated dimensions) -- [sklearn.org/stable/modules/generated/sklearn.multioutput.ClassifierChain.html](https://scikit-learn.org/stable/modules/generated/sklearn.multioutput.ClassifierChain.html)
- Joint Intent Detection and Slot Filling Survey (ACM Computing Surveys 2022)
- Multi-Task Learning with shared encoder -- [ruder.io/multi-task/](https://ruder.io/multi-task/)
- Multi-Dimensional Classification (Neurocomputing 2023) -- cross-dimension correlation modeling

### 1.4 Domain-Specific Activity Taxonomies (Industry Packs)

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

#### Personal Context: Project Taxonomy and Discovery

When `context=personal` (see §1.3 Facet 0), the `project` facet uses a different vocabulary than business. Instead of specific work initiatives (auth-service, patent-q3), personal projects are ongoing life areas (health, finances, relationships) plus any user-declared personal initiatives (marathon-training, home-renovation-2026, etc.).

The same 6 facets apply across both contexts -- only the values change. There is no separate personal "area" facet; `project` handles it uniformly:

| Facet | context=business | context=personal |
|-------|------------------|------------------|
| `project` | auth-service, patent-q3-filings, frontend-redesign | health, finances, marathon-training, home-renovation-2026 |
| `activity` | same 10 universal activities | same 10 universal activities |
| `domain` | engineering, legal, marketing, ... | (less relevant; can default to `life`) |
| `artifact` | source, test, config, infra, ... | notes, docs, receipts, photos, ... |
| `phase` | discovery, implementation, review, ... | (less structured in personal use) |

This is not a pack -- there is no "personal pack" to activate. Context detection (§1.3) does the switch automatically. The content below describes **what personal project values look like** and **how they get discovered**.

##### Default Personal Projects (10 Life Areas)

Synthesized across PARA (Forte), Wheel of Life (coaching), PERMA (Seligman positive psychology), Flourishing Life Model, and Maslow's hierarchy. These 7 core + 3 extended appear in 5+ frameworks each. They serve as **default `project` values when no user-declared personal project matches**:

| Project | Description | Common Sub-Projects |
|---------|-------------|---------------------|
| `health` | Physical + mental wellbeing, fitness, medical, sleep, nutrition | fitness, nutrition, sleep, medical-care, mental-health, chronic-conditions |
| `finances` | Budgeting, taxes, investing, debt, major purchases | budgeting, taxes, investing, debt-management, major-purchases, retirement-planning |
| `relationships` | Family, friends, romantic, social connections | family, friends, romantic, social, networking-personal, conflict-resolution |
| `parenting` | Kids, school, family logistics (distinct from relationships) | school, kids-activities, child-development, family-logistics, discipline, milestones |
| `home` | Household management, repairs, shopping, meal planning | meal-planning, chores, repairs, shopping, decor, organization |
| `career-personal` | Job search, skills, certifications, professional growth outside of current job | job-search, resume, interview-prep, certifications, side-hustle, networking |
| `learning` | Reading, courses, languages, self-education (not for a specific job) | reading, courses, languages, hobbies-skill, tutorials, note-taking |
| `fun-hobbies` | Recreation, creative pursuits, travel planning, games | travel, creative-project, gaming, sports-hobby, entertainment, crafts |
| `personal-growth` | Journaling, therapy, meditation, identity work, reflection | journaling, therapy-notes, meditation, values-reflection, habits, mindset |
| `admin` | Bills, scheduling, errands, documents, government forms | bills, scheduling, documents, government, insurance, subscriptions |

**Extended defaults** (opt-in for users who want them):
- `spirituality` -- faith practice, prayer, spiritual reading, religious community
- `community-service` -- volunteering, activism, donations, civic engagement
- `creative-self-expression` -- separate from hobbies when it's identity-level (writing, music, art)

User-declared personal projects (e.g., `!new-project marathon-training`) override the defaults. Tree-path discovery (below) surfaces recurring patterns as candidates for new personal projects.

##### Personal-Context Activity Examples

The `activity` facet uses the **same 10 universal activities** across both contexts (no separate personal taxonomy -- this is what "unify language" means). Example expressions in personal use:

| Activity | Personal-Context Examples |
|----------|--------------------------|
| `investigating` | symptom-checking, troubleshooting an appliance, diagnosing, researching a medical question |
| `building` | meal-planning, workout-creation, creative-project, side-project, decor-planning |
| `improving` | habit-building, skill-practice, editing, refinement, form-correction |
| `verifying` | checking-facts, fact-verification, second-opinion, proofreading |
| `researching` | learning, reading, comparing-options, medical-research, product-research |
| `planning` | trip-planning, budget-planning, schedule-planning, life-planning |
| `communicating` | email-draft, journaling, difficult-conversation-prep, card-writing, social-post |
| `configuring` | account-setup, app-setup, home-setup, tool-configuration |
| `reviewing` | self-reflection, checking-progress, evaluating-options |
| `coordinating` | family-scheduling, group-trip-planning, event-coordination |

##### Personal-Project Vocabulary Signals

Detecting **which personal project** a call belongs to (e.g., `project=health` vs `project=finances`) uses per-project vocabulary inventories. These do not decide `context` (that's §1.3) -- they decide which default life-area project applies once context is already personal.

```yaml
personal-project-vocab:
  health: [symptom, diagnosis, workout, diet, medication, therapy, doctor, hospital]
  finances: [budget, 401k, mortgage, tax, savings, debt, invest, retirement]
  relationships: [partner, spouse, breakup, marriage, dating, friend, family]
  parenting: [school, homework, teacher, pediatrician, playdate, tantrum, baby]
  home: [recipe, dinner, grocery, laundry, repair, plumber, landlord]
  career-personal: [resume, interview, offer letter, job hunt, networking]
  learning: [tutorial, course, book, language, practice]
  fun-hobbies: [vacation, travel, hobby, game, movie, concert]
  personal-growth: [journal, meditate, therapy, reflection, habit, identity]
  admin: [bill, subscription, renewal, appointment, form, document]
```

Rules for scoring are the same as business domain signals (strong/medium/weak with TF-IDF-style normalization) -- see the Pack Auto-Detection content later in this section for the shared algorithm.

##### Personal Projects Discovery: Tree-Path Classification Against a Hybrid Taxonomy

The core problem: **how do we let a user's individual areas emerge without burdening them with taxonomy management?** We've established that fixed taxonomies are too rigid and pure clustering produces unlabeled, unstable output. Academic research on Pinterest's Pin2Interest, Netflix's altgenres, and Amazon's hierarchical product classification points to a superior approach:

**Classify each prompt into paths in a large hierarchical taxonomy, then infer user areas from path frequency and stability.**

The key insight: if we match each prompt against a taxonomy like `hobby/sports/soccer/arsenal`, `hobby/sports/soccer/worldcup`, `hobby/sports/running`, then **areas emerge from which ancestors are stable across calls** (soccer, running) and **sub-areas emerge from stable paths beneath those ancestors** (arsenal, worldcup under soccer).

This approach is validated by extensive academic precedent:

| System | Scale | Approach | Lesson |
|--------|-------|----------|--------|
| Pinterest Pin2Interest | 200B+ pins, 10-level hierarchy, ~10K interests | Text+visual embeddings to taxonomy paths | Works at massive scale in production |
| Netflix altgenres | 76,897 micro-genres | Tag combinations over curated base | Combinatorial paths > fixed leaves |
| Spotify / Every Noise at Once | ~6,291 genres | Listening co-occurrence clusters → names | Clustering-then-labeling is viable alternative |
| Microsoft Academic Graph | 700K fields, 5 levels | Hierarchical classifier + subsumption | Large taxonomy + classifier works |
| Amazon product classifier | 3M SKUs | Deep hierarchical BERT + LLM dual-expert | 91.6% accuracy on 3rd tier |

**Why tree-path classification beats pure clustering** (Section's previous HDBSCAN-only approach):

| Property | Pure Clustering (HDBSCAN) | Tree-Path Classification |
|----------|--------------------------|--------------------------|
| Cold start | Need 20+ calls to form clusters | Works from call #1 |
| Interpretability | Unlabeled clusters require naming | Paths are human-readable |
| Cross-user comparability | Cluster IDs are user-specific | Same taxonomy paths across users |
| Stability | Cluster IDs change as data grows | Paths are stable |
| Cross-customer learning | Requires shared embedding space | Direct path-level aggregation (k-anonymity) |
| Novel pattern detection | Excellent | Requires taxonomy expansion mechanism |

**Conclusion**: Tree-path classification is the **primary mechanism**. HDBSCAN clustering is retained as a **secondary mechanism for taxonomy expansion** (discovering paths the taxonomy doesn't yet have).

##### The Hybrid Declawsified Taxonomy

No existing open taxonomy fits "things people ask AI about." Research confirms: IAB is ad-centric, Wikipedia is cyclical, Curlie is web-page-oriented, MAG is academic-only. We build a hybrid:

| Layer | Source | Size | Purpose |
|-------|--------|------|---------|
| **Root** | Declawsified core | ~15 nodes | Universal domains + personal areas (from §1.3/1.4) |
| **Mid-tree** | Declawsified curated + domain packs | ~500-1,000 nodes | Work activities + common personal sub-areas |
| **Long tail (work)** | MAG Fields of Study (academic), custom work sub-activities | ~5,000 nodes | Deep specialization in work contexts |
| **Long tail (personal)** | Curated from Curlie/Wikipedia categories | ~20,000-50,000 nodes | Coverage of common hobbies, interests, life activities |
| **Emergent layer** | Neural Taxonomy Expansion (user-proposed) | Grows over time | User-specific additions |

**MVP scope**: Ship with a 2,000-node hybrid taxonomy. Root + mid-tree curated by Declawsified team + 1,500 nodes curated from Curlie (fun-hobbies subtree, learning subtree) and MAG (research subtree). Long-tail nodes emerge over time via expansion mechanism.

**Taxonomy file format** (SKOS-compatible YAML, can export to standard SKOS RDF):

```yaml
# taxonomy/hybrid-v1.yaml
version: 0.1.0
root:
  work:
    engineering:
      software-development:
        backend: [api-design, database, auth, performance]
        frontend: [ui-components, state-management, styling]
        devops: [ci-cd, deployment, monitoring]
      # ... from engineering pack
    legal:
      # ... from legal pack + UTBMS codes
    # ... other domains
  personal:
    health:
      fitness:
        strength-training: [weightlifting, bodyweight, crossfit]
        endurance:
          running: [5k, 10k, half-marathon, marathon, ultra, trail-running, track]
          cycling: [road, mountain, gravel, commuting, touring]
          swimming: [freestyle, open-water, triathlon]
        yoga: [hatha, vinyasa, yin, hot-yoga]
      nutrition: [meal-planning, dietary-restrictions, macros, recipes-health]
      # ...
    fun-hobbies:
      sports:
        soccer:
          teams:
            premier-league: [arsenal, chelsea, liverpool, manchester-city, manchester-united, tottenham]
            la-liga: [real-madrid, barcelona, atletico-madrid]
            # ... full club list
          competitions: [worldcup, euros, champions-league, copa-america]
          topics: [transfers, tactics, history, statistics, fantasy-football]
        basketball:
          leagues: [nba, wnba, college, euroleague]
          # ...
        # ... other sports
      gardening:
        # ... content from the gardening specialization
      # ... other hobbies
```

**Scale check**: a 50K-node taxonomy is well within PECOS's <1ms inference range (production-validated at 2.8M labels). Pinterest runs 10K-node hierarchies with tens of thousands of interests at 200B+ pin scale. Our target scale is well-understood.

##### Classification Pipeline: Retrieval + Walk-the-Tree

Each prompt goes through a 3-tier cascade (distinct from the §2 activity-classification cascade — this one classifies into the TAXONOMY, not just facets):

**Tier 1: Retrieval (<5ms, O(log n))**

Pre-compute embeddings for every taxonomy node (using sentence-transformers: all-MiniLM-L6-v2 or gte-small). For each prompt:
1. Embed the prompt (or extract signal tokens if in signal-only mode)
2. Find top-K=20 nearest taxonomy nodes via cosine similarity (HNSW index)
3. Prune the tree to the subtree containing these K candidates

Cost: ~5-15ms on CPU. No LLM invocation. Near-zero marginal cost.

**Tier 2: LLM walk-the-tree with beam search (accurate, ~200ms)**

Starting from the root of the pruned subtree:
1. Present the LLM with: (a) prompt snippet, (b) current node, (c) list of children
2. LLM picks top-2 children to descend into (beam=2)
3. Repeat until: leaf reached, LLM says "no deeper match", or confidence drops below threshold
4. Emit 1-3 paths (may be multiple if prompt spans multiple topics)

This is the TELEClass / HierPrompt approach. Research shows matches flat classification accuracy without training, with dramatically better interpretability.

**Tier 3: Hierarchical rejection (Deep-RTC style)**

If confidence at depth D drops below threshold, stop and emit path to depth D-1. "Better correct at depth 2 than wrong at depth 5." Enforce per-node confidence thresholds:
- Level 1 (root): require ≥0.85 confidence
- Level 2: require ≥0.75 confidence
- Level 3: require ≥0.65 confidence
- Level 4+: require ≥0.55 confidence

Paths too shallow to be useful (root only) get tagged `unattributed`.

**Cost analysis for classification pipeline**:
- Tier 1 (retrieval): ~$0.00 (local embedding, indexed lookup)
- Tier 2 (LLM walk-the-tree): ~3-5 LLM calls per classification, ~$0.0003 per prompt using Gemini Flash Lite
- Total per-call cost: ~$0.0003, about 5x the flat classification cost, but with dramatically richer output

**Caching optimizations**:
- Pin retrieval results for the session (same topic → same subtree)
- Cache LLM walk-the-tree decisions for repeated subtree queries
- Expected cache hit rate: 60-80% in active sessions → effective cost <$0.0001/call

##### Path Frequency + Stability Analysis: The User's Insight Operationalized

Given a stream of classified paths, identify the user's active areas:

```python
def analyze_path_stability(
    paths: list[Path],        # all classified paths for this user
    time_range: timedelta,    # analysis window (e.g., last 30 days)
    min_calls: int = 5,       # minimum calls to surface a node
    min_weeks: int = 2,       # minimum temporal span
) -> Subtree:
    """
    Apply MDL summary-tree algorithm (Karloff & Shirley 2013) to produce
    the user's personalized taxonomy subtree.
    """
    # 1. Count calls per node (including ancestor counts)
    #    If user has a path /hobby/sports/soccer/arsenal, increment
    #    count at arsenal, soccer, sports, hobby (each +1)
    node_counts = {}
    for path in paths:
        for ancestor in path.ancestors_inclusive():
            node_counts[ancestor] = node_counts.get(ancestor, 0) + 1

    # 2. Compute temporal span per node (diversity of weeks)
    node_weeks = {}
    for path in paths:
        for ancestor in path.ancestors_inclusive():
            node_weeks.setdefault(ancestor, set()).add(path.week_number())

    # 3. Filter to stable nodes
    stable_nodes = {
        n for n in node_counts
        if node_counts[n] >= min_calls
        and len(node_weeks[n]) >= min_weeks
    }

    # 4. Apply MDL summary algorithm:
    #    For each ancestor chain, keep the deepest node where
    #    count is "meaningful" relative to parent
    #    (child_count / parent_count) > 0.4 => surface child
    #    else => show parent, treat children as aggregated
    surfaced = mdl_prune(stable_nodes, node_counts)

    return Subtree(root=surfaced.root, nodes=surfaced)
```

**Example** (user's actual behavior):

Classified paths over 30 days:
```
/hobby/sports/soccer/arsenal        (5 calls, 3 weeks)
/hobby/sports/soccer/worldcup       (3 calls, 2 weeks)
/hobby/sports/soccer/transfers      (2 calls, 2 weeks)
/hobby/sports/running/marathon      (8 calls, 4 weeks)
/hobby/sports/running/training      (4 calls, 3 weeks)
/hobby/cooking/italian              (3 calls, 2 weeks)
/hobby/cooking/bbq                  (2 calls, 1 week)
```

Node counts (with ancestors):
- `hobby`: 27 calls
- `hobby/sports`: 22 calls
- `hobby/sports/soccer`: 10 calls
- `hobby/sports/soccer/arsenal`: 5 calls
- `hobby/sports/soccer/worldcup`: 3 calls
- `hobby/sports/running`: 12 calls
- `hobby/sports/running/marathon`: 8 calls
- `hobby/cooking`: 5 calls

Stability filter (min_calls=5, min_weeks=2):
- Pass: `hobby`, `hobby/sports`, `hobby/sports/soccer`, `hobby/sports/soccer/arsenal`, `hobby/sports/running`, `hobby/sports/running/marathon`, `hobby/cooking`

MDL pruning decisions:
- `hobby/sports/soccer/arsenal` (5/10 = 50% of parent) → surface arsenal as sub-area
- `hobby/sports/soccer/worldcup` (3/10 = 30% of parent, below threshold) → aggregate under soccer
- `hobby/sports/running/marathon` (8/12 = 67% of parent) → surface marathon as sub-area

Final surfaced taxonomy for this user:

```
fun-hobbies  (27 calls)
├── sports  (22 calls)
│   ├── soccer  (10 calls)
│   │   └── arsenal  (5 calls)      <- stable sub-sub-area
│   │   └── [other soccer topics]   <- aggregated (worldcup, transfers)
│   └── running  (12 calls)
│       └── marathon  (8 calls)      <- stable sub-sub-area
│       └── [other running topics]  <- aggregated (training)
└── cooking  (5 calls, shallow)
```

This is exactly the insight from the user's example. No clustering required, no embedding space maintenance, pure path-frequency analysis.

##### Dynamic Depth: Coarsen and Deepen

The surfaced taxonomy **adapts to each user's data volume**. A user with 1,000 calls sees a deeper tree; a user with 50 calls sees a coarser one. The same MDL algorithm run with different `min_calls` thresholds produces different levels of detail.

**UX controls**:
- Default: `min_calls=5, min_weeks=2`
- "Summary view": `min_calls=20, min_weeks=4` (show only major areas)
- "Detailed view": `min_calls=2, min_weeks=1` (show everything)

This replaces the previous "configuration yaml" approach with something **self-tuning**: the system picks sensible defaults and the user can coarsen/deepen with a slider.

##### Neural Taxonomy Expansion: Handling Novel Patterns

Some user prompts will not map cleanly to any taxonomy node. These get tagged `unattributed` at some depth. When unattributed calls accumulate:

1. **Cluster unattributed calls** (HDBSCAN, as in the previous section -- now used as a secondary, targeted mechanism)
2. **For each cluster**, apply Pinterest's Neural Taxonomy Expansion:
   - Compute cluster centroid embedding
   - Find top-3 candidate parents in the existing taxonomy (nearest existing nodes)
   - Use LLM to propose a name from distinctive terms + candidate parents
3. **Propose to user**:
   ```
   [Declawsified] 12 recent calls cluster together but don't match existing taxonomy.
   Distinctive terms: sourdough, autolyse, levain, starter, crumb, bulk-ferment
   Suggested: add 'sourdough' under fun-hobbies/cooking/bread?

   [ Accept ] [ Rename parent ] [ Propose different parent ] [ Reject ]
   ```
4. **On accept**: new node added to user's personal taxonomy extension, retroactively re-classifies the 12 calls

This is the HDBSCAN approach from the previous section, now **scoped to the taxonomy-expansion role** rather than being the primary discovery mechanism.

##### Cross-User Taxonomy Evolution

Because all users share the same base taxonomy, cross-user learning becomes trivial at the path level:

**What's aggregated** (k-anonymous, k≥50, opt-in):
- Which taxonomy paths are most-used by users who opted into the personal pack
- User-proposed expansions that many users accept independently
- Path co-occurrences ("users with gardening also have woodworking")

**Taxonomy evolution cycle**:
1. Users accept expansions individually
2. When 50+ users independently add the same path with the same parent, it becomes a candidate for the next shared taxonomy release
3. Quarterly taxonomy updates incorporate validated community additions
4. Users receive the update; their local expansions get promoted to canonical nodes

This mirrors Pinterest's NTE + human review pattern. Over time, the shared taxonomy grows to cover more of the long tail without requiring manual curation.

##### Comparison: Tree-Path Classification vs Previous HDBSCAN-Only Approach

| Property | HDBSCAN-only (previous) | Tree-Path (primary) + HDBSCAN (expansion) |
|----------|--------------------------|-------------------------------------------|
| Cold start | 20+ calls needed | Works from call #1 |
| Classification latency | Low (no LLM) | Low-medium (LLM walk-the-tree, cached) |
| Classification cost | $0.00 | ~$0.0003/call (Gemini Flash Lite) |
| Interpretability | Requires post-hoc naming | Human-readable paths immediately |
| Cross-user learning | Hard (embedding alignment) | Trivial (path-level aggregation) |
| Novel pattern detection | Excellent | Via HDBSCAN expansion mechanism |
| Stability | Cluster IDs shift | Paths are stable |
| User mental model | "The system found a cluster" | "I'm spending time on sports/soccer/arsenal" |

The tree-path approach is strictly better on most dimensions. HDBSCAN remains essential but in a targeted role.

##### Dynamic Sub-Area Discovery: Personalization Through Observation

The 10 life areas are a **starting point, not a ceiling**. A real user's taxonomy is deeply individual:

- An avid hobbyist has `fun-hobbies` subdivided into `gardening`, `hiking`, `board-games`, `cooking`, each with their own rhythms and vocabularies
- A professional gardener operating a nursery has `career-personal` (or a work domain) with deep sub-areas: `permaculture`, `seed-saving`, `pest-management`, `customer-orders`, `tool-maintenance`
- A parent of three has `parenting` subdivided by child: `child-1-school`, `child-2-sports`, `child-3-health`
- A new runner has `health` with a growing `running` sub-area that might deepen into `training-plans`, `injury-recovery`, `race-prep` as their expertise grows

**Auto-discovery of sub-areas is the core product value for personal use**, not a post-MVP feature. Users should never have to configure a taxonomy -- the system learns theirs by watching.

Three tiers of personalization emerge:

| Tier | Source | Example |
|------|--------|---------|
| **Tier 1: Universal areas** | Fixed defaults (10 areas) | `fun-hobbies` |
| **Tier 2: Discovered sub-areas** | Observed user patterns (personalized) | `fun-hobbies/gardening` |
| **Tier 3: Specializations** | Imported community templates or auto-deepened | `fun-hobbies/gardening/permaculture` |

##### Sub-Area Discovery Algorithm

Sub-areas emerge from observed data, not predefined templates. The algorithm borrows from the taxonomy management research already integrated (TnT-LLM, TaxoAdapt) but tuned for personal-use data volumes.

```python
def discover_subareas(area: str, calls: list[Call], min_size: int = 8) -> list[SubArea]:
    """
    Run periodically (daily/weekly) per active area.
    Proposes new sub-areas based on observed clustering of calls within the area.
    """
    if len(calls) < 20:
        return []  # not enough data yet

    # 1. Embed prompts (or signals only, if configured)
    embeddings = embed_calls(calls)

    # 2. Density-based clustering (HDBSCAN or DBSCAN)
    #    HDBSCAN picks natural cluster counts and labels noise
    clusters = hdbscan_cluster(embeddings, min_cluster_size=min_size)

    # 3. For each discovered cluster:
    subareas = []
    for cluster_id, cluster_calls in clusters.items():
        if cluster_id == -1:
            continue  # noise, ignore

        # 4. Extract distinguishing vocabulary (TF-IDF within area)
        distinctive_terms = tfidf_distinctive(
            cluster_calls,
            background=calls,  # compare against whole area
            top_k=8
        )

        # 5. Check cohesion (intra-cluster similarity)
        cohesion = intra_cluster_cosine(cluster_calls)
        if cohesion < 0.55:
            continue  # not cohesive enough

        # 6. Generate candidate name via LLM (one-shot, local if possible)
        name = propose_subarea_name(
            distinctive_terms,
            sample_prompts=redact(cluster_calls[:3])  # redacted samples
        )

        subareas.append(SubArea(
            parent=area,
            proposed_name=name,
            distinctive_terms=distinctive_terms,
            call_count=len(cluster_calls),
            cohesion=cohesion,
            first_seen=min(c.timestamp for c in cluster_calls),
            last_seen=max(c.timestamp for c in cluster_calls),
        ))

    return subareas
```

**Key design choices**:
- **HDBSCAN over k-means**: HDBSCAN finds natural clusters without specifying k, handles noise, produces variable-density clusters. Personal life areas don't have uniform granularity -- a user may have 1 big "gardening" cluster and 5 smaller ones.
- **Min cluster size 8**: Balances signal vs noise. 8 recurring calls on the same sub-theme is a pattern worth naming.
- **Cohesion threshold 0.55**: Prevents naming clusters that are coincidentally co-located but not actually about the same thing.
- **Redacted samples for LLM naming**: Never send raw prompts to the naming call -- only vocabulary signals + redacted snippets.

##### Surfacing Discoveries to the User

The system never auto-creates sub-areas. It proposes them:

```
[Declawsified]  Last 30 days, under `fun-hobbies` we noticed a pattern:
  Cluster: 23 calls, cohesion 0.78
  Distinctive terms: seeds, soil, tomato, compost, zone, bed, raised, mulch
  Sample themes (redacted): planning spring garden, soil amendments, ...

  Proposed sub-area:  fun-hobbies/gardening

  [ Accept ] [ Rename ] [ Reject ] [ Remind me later ]
```

**UX principles**:
- Propose at most 2 new sub-areas per user per week (avoid nagging)
- Batch proposals weekly, not per-call
- Let users rename before accepting
- "Reject" remembers the cluster and stops surfacing it for 90 days
- Applied retroactively: once accepted, all past calls in that cluster are re-tagged

##### Expertise Detection: Hobby vs Professional

A user who asks "how do I grow tomatoes?" once is a beginner. A user who asks about "companion planting for heirloom tomatoes in USDA zone 7b with cover crop rotation" is several tiers deeper. The system should detect this and offer **specialization depth** dynamically.

**Expertise signals per sub-area**:

| Signal | Weight | What It Indicates |
|--------|--------|-------------------|
| Vocabulary depth (distinct technical terms per call) | +0.3 | Advanced knowledge |
| Question complexity (multiple sub-questions, conditionals) | +0.2 | Mature mental model |
| Specific references (brand names, species, cultivar names, standards) | +0.3 | Deep domain |
| Sustained frequency (> 3 calls/week for 4+ weeks) | +0.2 | Ongoing investment |
| Teaching language ("I'm helping my friend with...") | +0.3 | Expert teaching others |
| Professional context leak ("my client's garden", "our nursery", "my farm") | +0.5 | Likely professional |
| Advanced-only vocabulary hits (cultivar, scion, grafting, polyculture) | +0.4 | Advanced hobbyist or pro |
| Beginner-phrases ("what is", "how do I start", "I'm new to") | -0.3 | Early learner |

**Expertise tiers**:

| Score | Tier | System Behavior |
|-------|------|-----------------|
| 0.0-0.3 | `beginner` | Simple sub-area, no specialization offered |
| 0.3-0.6 | `hobbyist` | Offer sub-area creation, shallow sub-structure |
| 0.6-0.9 | `advanced-hobbyist` | Offer specialization library: "You seem deeply interested in gardening. Import the advanced gardening specialization?" |
| 0.9+ | `professional` | Suggest moving to a domain rather than a life area: "This looks like professional work. Reclassify as domain=agriculture with project=nursery-operations?" |

##### Specialization Library: Community Patterns

Auto-discovery is powerful, but **users benefit from pre-curated depth for common interests**. The specialization library is a growing collection of community-sourced sub-area taxonomies users can import with one command.

**Structure of a specialization**:

```yaml
# specializations/gardening-advanced.yaml
name: gardening-advanced
parent_area: fun-hobbies
description: Deep taxonomy for serious home gardeners
author: declawsified-community
version: 1.2

sub_areas:
  planning:
    description: Garden design, crop rotation, seasonal planning
    vocab: [plan, design, rotation, companion, zone, hardiness]

  seeds-starting:
    description: Seed selection, germination, seed-starting
    vocab: [seed, germination, stratification, heirloom, hybrid, F1]

  soil-composting:
    description: Soil health, amendments, composting
    vocab: [compost, amendment, pH, nitrogen, mulch, tilth, organic-matter]

  pests-diseases:
    description: Pest identification, organic control, disease management
    vocab: [pest, aphid, blight, fungicide, neem, integrated-pest-management]

  pruning-training:
    description: Pruning techniques, espalier, trellising
    vocab: [prune, espalier, trellis, pinch, thin, graft]

  harvesting-preserving:
    description: Harvest timing, preservation, storage
    vocab: [harvest, canning, freezing, dehydrate, curing, storage]

  specialization-areas:
    permaculture: {vocab: [swale, guild, food-forest, polyculture]}
    hydroponics: {vocab: [nutrient-solution, DWC, NFT, EC, ppm]}
    native-plants: {vocab: [native, ecotype, wildlife-garden, pollinator]}
    edible-landscaping: {vocab: [edible, foodscape, fruit-tree, perennial-vegetable]}
```

**Specializations ship with the tool** for common interests identified from cross-customer aggregate data (opt-in):

| Area | Shipped Specializations |
|------|------------------------|
| `fun-hobbies` | gardening, running, cycling, photography, cooking, board-games, reading, woodworking, knitting, birdwatching |
| `health` | strength-training, endurance-training, yoga, weight-loss, chronic-condition-X, mental-health |
| `parenting` | newborn, toddler, school-age, teenager, special-needs, co-parenting |
| `finances` | investing-stocks, real-estate, retirement-planning, tax-optimization, frugal-living |
| `career-personal` | job-search-tech, job-search-general, interview-prep, side-hustle, remote-work |
| `learning` | language-learning, programming-learning, music-learning, test-prep |
| `personal-growth` | journaling, therapy-prep, habit-building, relationship-growth |

**User workflow**:

```bash
$ declawsified specializations list --area fun-hobbies
Available specializations under fun-hobbies:
  * gardening       (community, v1.2)   [auto-suggested, 67% match]
    running         (community, v1.0)
    photography     (community, v2.0)
    cooking         (community, v1.1)
    ... 6 more ...

$ declawsified specializations install gardening
Installed fun-hobbies/gardening specialization (7 sub-areas + depth categories).
Retroactively re-tagging 23 recent calls...
Done. 18 of 23 calls auto-mapped. 5 remain at fun-hobbies/gardening (no sub-area match).
```

**Auto-suggestion of specializations**:

When sub-area discovery proposes a new sub-area AND that sub-area name matches a shipped specialization, the system offers the specialization instead:

```
[Declawsified] Discovered new sub-area: fun-hobbies/gardening (23 calls).

We also have a community 'gardening' specialization with 7 sub-areas and
4 depth categories (permaculture, hydroponics, etc.). Import it?

  [ Just create sub-area ] [ Import specialization ] [ Rename ] [ Skip ]
```

##### Cross-Customer Pattern Learning (The Flywheel)

The CrowdStrike-style data moat applies to personal use too.

**What's shared (opt-in, aggregated)**:
- Sub-area names that users accept (not sub-area vocabularies or content)
- Specialization usage statistics
- Common sub-area co-occurrences ("users with gardening also have woodworking")

**What's never shared**:
- Individual call content
- User-specific vocabularies

**What this enables**:
- Growing the specialization library: popular user-accepted sub-areas become candidates for new shipped specializations
- Cold-start better defaults: "Most new users in `fun-hobbies` develop sub-areas for: cooking (34%), gardening (28%), reading (22%)..."
- Trend detection: "Users in 2026 are increasingly adding AI-assisted sub-areas around homesteading, LLM-development, climate-adaptation"

**Aggregation threshold**: A sub-area name is only published as a shared default after 50+ users have it independently. This avoids singleton or small-cohort patterns shaping the default library.

##### Sub-Area Lifecycle

Sub-areas are not forever. They can:

**Emerge**: Discovered from 20+ calls clustering within an area. Proposed to user.
**Accepted**: User accepts; sub-area becomes active, retroactive re-tagging applied.
**Evolve**: Additional clusters within an accepted sub-area trigger nested sub-area proposals (3 levels max: area > sub-area > sub-sub-area).
**Consolidate**: If two sub-areas have > 0.8 overlap in vocabulary and calls, suggest merging.
**Split**: If a sub-area contains distinct clusters > cohesion threshold, suggest splitting.
**Archive**: No calls for 90 days; system proposes archiving (keeps tag searchable but stops auto-classifying to it).
**Graduate**: Expertise tier crosses into `professional` → suggest moving from life area to domain.

##### Configuration: User Control Over Dynamic Taxonomy

```yaml
# ~/.declawsified/config.yaml (personal profile)
personal:
  area_discovery:
    enabled: true
    proposal_frequency: weekly  # weekly | daily | on-demand
    max_proposals_per_week: 2
    min_cluster_size: 8
    cohesion_threshold: 0.55
    auto_accept_threshold: 0.0  # 0 = never auto-accept, 1.0 = always

  specializations:
    auto_suggest: true
    installed: [gardening, running, job-search-tech]

  expertise_detection:
    enabled: true
    suggest_specialization_at: 0.6
    suggest_professional_reclassification_at: 0.9

  cross_customer_sharing:
    enabled: false  # opt-in, default off
    shared_areas: []  # user picks per-area: [fun-hobbies, learning]
```

##### How This Generalizes to Work Packs

Dynamic sub-area discovery isn't unique to personal use -- it applies to work packs too. An engineer's `activity=investigating` might organically subdivide into `error-tracing` / `performance-profiling` / `integration-debugging` without predefinition. The personal pack is just the **most urgent** case because personal interests are fundamentally heterogeneous.

The same algorithm runs for work packs, with these differences:

| Aspect | Personal | Work |
|--------|----------|------|
| Min cluster size | 8 | 25 |
| Proposal frequency | weekly | monthly |
| Specialization library | Hobby/life templates | Industry/role templates |
| Cross-customer sharing | Opt-in per area | Opt-in per org |

Post-MVP, work packs inherit this dynamic discovery mechanism for domain-specific sub-activities.

#### Pack: Personal / Education

**Note on Education vs Personal**: The educational use case (students using AI for coursework) is a specialized subset of personal use. An educational overlay adds sub-activities like `homework`, `exam-prep`, `thesis-work` within the personal pack's areas (primarily `learning`, `career-personal`, `personal-growth`).

For the MVP, the personal pack covers both. A dedicated education pack is post-MVP.

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

For power users and edge cases, the in-prompt command layer (§1.11) supports pack control:

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

The system learns progressively as calls accumulate:

**Stage 1 (calls 1-50)**: Universal taxonomy only. Observation mode. Pack scores accumulating.

**Stage 2 (calls 50-200)**: First pack suggestion surfaces. User accepts (most common case) or declines. Pack-specific sub-activity classification begins for accepted packs.

**Stage 3 (calls 200-1,000)**: Classifier confusion analysis per pack. User corrections refine pack detection signals. Secondary pack may surface if work is cross-domain.

**Stage 4 (calls 1,000+)**: Pack detection is mature. Cross-customer aggregate data improves baseline (the CrowdStrike flywheel). Signal inventories refined based on real-world term distributions.

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

### 1.5 Automatic Project Detection

Project detection is not optional and cannot wait for post-MVP. It is the #1 value proposition for any organization beyond a single developer.

#### Detection Algorithm

```python
def detect_project(call_metadata: dict, project_registry: dict) -> str:
    """
    Returns project identifier. Runs as part of Facet 3 extraction.
    Priority order ensures most-specific signal wins.
    """
    # Priority 0: In-prompt command (100% confidence, see §1.11)
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

**Note on Priority 0**: User-typed tags and commands in the prompt text are the **highest-priority signal** because they represent direct, intentional user communication. The in-prompt layer (§1.11) gives users the lowest-friction way to override automatic detection when they know better than the signals.

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

### 1.6 Multi-Dimensional Tag Output Format

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

### 1.7 The Combinatorial Power: Why This Matters

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

### 1.8 Taxonomy Evolution Strategy

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

**References**
- TnT-LLM -- [arxiv.org/abs/2403.12173](https://arxiv.org/abs/2403.12173) (KDD 2024) -- iterative taxonomy generation via minibatch LLM refinement
- TaxoAdapt -- [arxiv.org/abs/2506.10737](https://arxiv.org/abs/2506.10737) (ACL 2025) -- density-based dynamic taxonomy expansion
- TaxMorph -- [arxiv.org/html/2601.18375](https://arxiv.org/html/2601.18375) (EACL 2026) -- 4 refinement operations, +2.9 F1
- OLLM ontology learning -- [github.com/andylolu2/ollm](https://github.com/andylolu2/ollm) (NeurIPS 2024)

### 1.9 Taxonomy Library: Starting Points by Setting

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

#### Profile: Personal Use (Individual, No Work)

```yaml
profile: personal
context_default: personal                   # short-circuit context detection
domain_facet: disabled                      # not used in personal context
active_packs: []                            # no business packs needed
primary_view: project + activity
project_detection: signal-only (time, workdir, vocabulary, user-declared)
cross_customer_sharing: opt-in-per-project
dashboard_view: life-wheel                  # radial chart, not bar/line
```

#### Profile: Personal + Professional (Hybrid User)

For the common case: professional using AI for both work and personal tasks on the same machine.

```yaml
profile: hybrid
context_default: auto                       # classify context per-call
active_packs: [engineering]                 # business-context packs
primary_view: context + project + activity
project_detection: enabled (both contexts; different vocabularies)
session_split: automatic                    # session can contain both contexts, classified per-call
```

**Key behavior**: The context classifier (§1.3 Facet 0) runs first. Business calls get business-pack sub-activity classification and business-project vocabulary. Personal calls get the personal-project vocabulary (life-area defaults + tree-path discovery). Same user, same session, classified per-call.

#### Profile: Student

```yaml
profile: student
context_default: personal                   # students are mostly personal context
active_packs: [education-overlay]
primary_view: project + activity + assignment
project_detection: course codes (CS101, MATH240) + assignment names + life-area defaults
custom_facets: [course, assignment, exam]
```

### 1.10 Cross-Dimensional Intelligence

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

### 1.11 In-Prompt Communication Layer

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
| `!context <personal\|business>` | Force context for this call and session | `!context personal` |
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
| `!subarea <parent>/<name>` | Create or assign personal sub-area | `!subarea fun-hobbies/gardening` |
| `!specialization install <name>` | Import community specialization template | `!specialization install gardening` |
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
| Prompt handling | Three modes: preserve / strip / normalize |
| Backwards compat | Tags are harmless text if Declawsified isn't installed |

**References**
- Slack Slash Commands -- [docs.slack.dev/interactivity/implementing-slash-commands/](https://docs.slack.dev/interactivity/implementing-slash-commands/)
- Kubernetes Prow ChatOps -- [docs.prow.k8s.io/docs/components/plugins/approve/approvers/](https://docs.prow.k8s.io/docs/components/plugins/approve/approvers/)
- Probot Commands -- [github.com/probot/commands](https://github.com/probot/commands) -- line-anchored `/command` pattern
- GitLab Quick Actions -- [docs.gitlab.com/user/project/quick_actions/](https://docs.gitlab.com/user/project/quick_actions/)
- Jira Smart Commits -- [support.atlassian.com/jira-software-cloud/docs/process-issues-with-smart-commits/](https://support.atlassian.com/jira-software-cloud/docs/process-issues-with-smart-commits/)
- Twitter-text regex reference -- [github.com/twitter/twitter-text](https://github.com/twitter/twitter-text) -- hashtag standard
- Obsidian Tags -- [help.obsidian.md/tags](https://help.obsidian.md/tags) -- nested tag pattern with `/`
- Hubot / Errbot / Lita -- classic IRC-style `!` bot command precedent
- Claude Code Hooks reference -- [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks) -- `UserPromptSubmit` event
- Claude Code in Slack -- [code.claude.com/docs/en/slack](https://code.claude.com/docs/en/slack) -- production intent routing classifier
- OWASP LLM01:2025 Prompt Injection -- [genai.owasp.org/llmrisk/llm01-prompt-injection/](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- "I Sent the Same Prompt Injection to Ten LLMs. Three Complied" -- instruction-shaped token risk analysis
- LLMON: LLM-native markup language -- [arxiv.org/html/2603.22519v1](https://arxiv.org/html/2603.22519v1) -- structured metadata in prompts

### 1.12 Academic Foundations for This Design

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

## 2. Classification Engine: Research & Approach

### 2.1 Academic Foundations

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

**References**
- "Revisiting Hierarchical Text Classification: Inference and Metrics" (2024) -- [arxiv.org/html/2410.01305v1](https://arxiv.org/html/2410.01305v1)
- "HTC vs XML: Two Sides of the Same Medal" (2024) -- [arxiv.org/html/2411.13687v2](https://arxiv.org/html/2411.13687v2)
- "Hierarchical Text Classification and Its Foundations: A Review" (MDPI 2024)
- "Hierarchical Text Classification Using Black Box LLMs" (2025) -- [arxiv.org/html/2508.04219v1](https://arxiv.org/html/2508.04219v1)
- HTCInfoMax (NAACL 2021), HGCLR (ACL 2022), HiTIN (ACL 2023), HiGen (2025) -- hierarchy-aware classifiers
- Lientz & Swanson, "Software Maintenance Management" (1980) -- foundational SE activity taxonomy
- Schach et al., "Determining the Distribution of Maintenance Categories" (Empirical SE 2003)
- evidencebp/commit-classification -- 93% accuracy on corrective commit detection
- Conventional Commits Specification -- [conventionalcommits.org](https://www.conventionalcommits.org/)
- Minelli et al. -- IDE telemetry, 70% of developer time on comprehension
- Damevski et al. -- HMM on IDE actions for latent task-state detection

### 2.2 Recommended Classification Architecture: Tiered Cascade

Academic literature on cascade classifiers supports a tiered approach where classifiers are applied sequentially, with each tier handling progressively harder cases.

#### Tier 1: Metadata Rules (zero cost, <0.1ms)

Signal-only classification without reading prompt content. Runs independently per facet.

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

**Project facet signals**: See §1.5 detection algorithm.

**Expected Tier 1 coverage**: 25-35% of `activity` calls resolved. 70-80% of `artifact` calls resolved. 90%+ of `project` calls resolved (when metadata or git signals present).

#### Tier 2: Keyword/Content Classifier (<1ms)

For calls not resolved by Tier 1. Reads prompt content.

**Phase A (no training data)**: keyword matching for `activity` facet

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

**Phase B (with initial training data)**: TF-IDF + Logistic Regression per facet

- Independent classifier per facet (MultiOutputClassifier pattern)
- Trains in <1 second per facet on a laptop
- Inference <1ms per classification across all facets
- Expected accuracy: 82-86% per facet with 200-500 labeled examples per value
- Library: scikit-learn, zero GPU required

**Phase C (with accumulated training data)**: SetFit or Sentence Transformers + KNN

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

### 2.3 Active Learning for Bootstrapping

**Core finding**: Active learning reduces labeling needs by 50-70% compared to random sampling.

**Bootstrap plan** (per facet, `activity` is the hardest -- other facets are mostly rule-based):

| Stage | Labeled Examples | Activity Accuracy | Domain Accuracy | Method |
|-------|-----------------|-------------------|-----------------|--------|
| Cold start | 0 | 60-75% | 80-90% (from team metadata) | Rules + keywords |
| Few-shot | ~80 (8 per activity) | 80-87% | 85-92% | SetFit few-shot per facet |
| Active learning | 200-500 | 87-92% | 90-94% | Uncertainty/diversity sampling per facet |
| Trained | 1,000+ | 90-95% | 93-97% | Trained classifiers + correction flywheel |

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

**References**
- Small-Text -- "Active Learning for Text Classification in Python" (EACL 2023 Best Demo)
- SetFit -- "Efficient Few-Shot Learning Without Prompts" (HuggingFace)
- "Enhancing Text Classification through LLM-Driven Active Learning" (2024)
- "Cold-start Active Learning through Self-supervised Language Modeling" (EMNLP 2020)

### 2.4 Goal/Task Detection

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

## 3. Classification Technique Cost Analysis

### 3.1 Per-Call Cost Comparison

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

### 3.2 Monthly Cost at Scale

| Technique | 100/day | 1,000/day | 10,000/day |
|-----------|---------|-----------|------------|
| GPT-4.1-nano (pure) | $0.17 | $1.74 | $17.40 |
| Gemini Flash Lite (pure) | $0.13 | $1.32 | $13.20 |
| Hybrid (rules 60% + nano 40%) | $0.05 | $0.52 | $5.22 |
| Traditional ML (self-hosted) | ~$0.00 | ~$0.00 | ~$0.00 |
| Self-hosted GPU (always-on L4) | $350 | $350 | $350 |

### 3.3 Cost Decision

**Recommendation**: Hybrid (Tier 1 rules + Tier 2 keywords + Tier 3 GPT-4.1-nano/Gemini Flash Lite).

At $0.52/month for 1,000 calls/day, the classification cost is negligible compared to the LLM API calls being classified (which cost $0.01-$0.10+ each). The classification cost is <0.1% of the cost being tracked.

Self-hosted models (local 3B on GPU) are only cost-effective at >50K calls/day sustained, and add significant operational complexity. Not recommended for MVP.

### 3.4 Local Model Option (Privacy-Sensitive Deployments)

For enterprise users who cannot send prompt content to external APIs:

- **Tier 1 + Tier 2 only** (metadata rules + keywords/ML): 80-87% accuracy at $0.00/call
- **Tier 3 local via Ollama** (Phi-4-mini, Qwen 2.5 3B): 80-88% accuracy, 500-1500ms latency, runs on consumer hardware
- **Sentence Transformers locally** (all-MiniLM-L6-v2, 22MB model): 85-92% accuracy, 5-15ms latency, runs on CPU

**References**
- OpenAI Pricing -- [platform.openai.com/docs/pricing](https://platform.openai.com/docs/pricing)
- Anthropic Pricing -- [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Gemini API Pricing -- [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)
- DeepSeek Pricing -- [api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)
- Lambda Labs GPU Pricing -- [lambda.ai/pricing](https://lambda.ai/pricing)
- RunPod Serverless Pricing -- [docs.runpod.io/serverless/pricing](https://docs.runpod.io/serverless/pricing)

---

## 4. Memory & Taxonomy System Research

### 4.1 Why This Matters

The classification taxonomy is itself a structured knowledge representation. LLM memory systems solve an analogous problem: organizing information into retrievable hierarchies that evolve over time. Key insights from memory system research directly apply to taxonomy design and maintenance.

### 4.2 Key Systems Analyzed

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

**References**
- MemPalace -- [github.com/milla-jovovich/mempalace](https://github.com/milla-jovovich/mempalace)
- Aeon neuro-symbolic cognitive OS -- [arxiv.org/abs/2601.15311](https://arxiv.org/abs/2601.15311)
- MemGPT/Letta -- [docs.letta.com](https://docs.letta.com)
- Mem0 -- [arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413)
- A-MEM Zettelkasten -- [arxiv.org/abs/2502.12110](https://arxiv.org/abs/2502.12110) (NeurIPS 2025)
- HippoRAG -- [arxiv.org/abs/2405.14831](https://arxiv.org/abs/2405.14831) (NeurIPS 2024)

### 4.3 Taxonomy Management Techniques

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

**References**
- TnT-LLM -- [arxiv.org/abs/2403.12173](https://arxiv.org/abs/2403.12173) (KDD 2024)
- TaxoAdapt -- [arxiv.org/abs/2506.10737](https://arxiv.org/abs/2506.10737) (ACL 2025)
- TaxMorph -- [arxiv.org/html/2601.18375](https://arxiv.org/html/2601.18375) (EACL 2026)
- OLLM ontology learning -- [github.com/andylolu2/ollm](https://github.com/andylolu2/ollm) (NeurIPS 2024)

### 4.4 Practical Insights for Declawsified

1. **Hierarchical structure improves accuracy** -- MemPalace's 34% improvement over flat search is strong evidence. Even if we start with flat classification, organizing the training data and rules hierarchically matters.

2. **Semantic caching** (Aeon's SLB) should be implemented for sequential calls. If the last 5 API calls from session X were classified as "debugging," the 6th is very likely "debugging" too. A simple cache hit avoids Tier 3 entirely.

3. **Taxonomy evolution should be data-driven** (TaxoAdapt, TaxMorph) not hand-crafted. Set density thresholds and let the system tell you when to split or merge categories.

4. **Cross-category connections** (MemPalace's "tunnels") model real work patterns: debugging sessions that become refactoring, testing that reveals bugs, research that leads to feature development. Track category transitions within sessions as a signal.

5. **Multi-generational consolidation** prevents category drift. When merging similar subcategories, use vector clustering first (fast, no LLM), then LLM-gated verification (ensures nuance is preserved).

---
