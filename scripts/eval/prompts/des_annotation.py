"""
DES annotation prompt — system prompt + JSON schema + few-shot.

The system prompt is cached (1-hour TTL via prompt caching). Per-sample
user text is the only thing that varies between requests.
"""

from __future__ import annotations

from pathlib import Path

# Closed-vocabulary enums for the 5 facets.
CONTEXT_VALUES = ["personal", "business", "unknown"]
DOMAIN_VALUES = ["engineering", "marketing", "finance", "legal", "health", "unknown"]
ACTIVITY_VALUES = [
    "investigating", "building", "improving", "verifying", "researching",
    "planning", "communicating", "configuring", "reviewing", "coordinating",
    "unknown",
]


def output_schema() -> dict:
    """JSON schema for the 5-facet annotation. Used with output_config.format."""
    return {
        "type": "object",
        "properties": {
            "context":  {"type": "string", "enum": CONTEXT_VALUES},
            "domain":   {"type": "string", "enum": DOMAIN_VALUES},
            "activity": {"type": "string", "enum": ACTIVITY_VALUES},
            "project":  {"type": "array", "items": {"type": "string"}},
            "tags":     {"type": "array", "items": {"type": "string"}},
            "notes":    {"type": "string"},
        },
        "required": ["context", "domain", "activity", "project", "tags", "notes"],
        "additionalProperties": False,
    }


# ---------- System prompt ----------------------------------------------------

_SYSTEM_INSTRUCTIONS = """You are a classification annotator for the Declawsified evaluation set.
Given a single user message (which may be a question, a request, or the start of a conversation),
output JSON labels for five facets. Use ONLY the values listed below — invented values are
forbidden and will be rejected by validation.

FACETS

context — who is doing this?
  personal — personal life: hobbies, family, health, entertainment, household, finances
  business — paid work in any role
  unknown  — cannot tell from the message alone

domain — only use when the message is clearly about one of these business domains
  engineering — software, infra, devops, data engineering, hardware
  marketing   — campaigns, branding, copy, growth, SEO
  finance     — accounting, budgeting, forecasting, financial reporting
  legal       — contracts, compliance, litigation, IP
  health      — clinical care, medical practice (NOT personal health questions — those go in tags)
  unknown     — message is not in a business domain, or cannot tell

activity — what kind of work is the message doing?
  investigating — debugging, root-causing, "why is X broken / behaving this way"
  building      — creating something new (code, content, plan, doc)
  improving     — refactoring, optimizing, polishing existing work
  verifying     — testing, reviewing for correctness, checking
  researching   — looking up facts, comparing options, learning a topic
  planning      — designing approach, breaking down work, scheduling
  communicating — drafting messages, explanations, replies, summaries for others
  configuring   — settings, environment, tooling, infrastructure setup
  reviewing     — code review, document review, evaluating others' work
  coordinating  — scheduling, status updates, project mgmt across people
  unknown       — cannot tell

project — array of free-text project names if the message names a specific project,
          team, repo, or initiative; otherwise ["unknown"]. Keep entries short (≤30 chars).
          Project is metadata-style attribution, not topic. "auth-service" yes;
          "basketball" no — basketball goes in tags.

tags — array of 0-5 leaves from the taxonomy below. Use the exact leaf name (e.g.
       "basketball", not "Basketball" or "sports"). Pick only leaves the message is
       clearly ABOUT. Do not include the parent (e.g. don't add "sports" if you
       already have "basketball" — pick the most specific leaf that fits).
       Empty list [] is valid when no leaf is clearly relevant.

notes — one short sentence (under 25 words) explaining your top-of-mind reasoning
        for the activity and tags choices. Used for spot-checks only; concise is good.
"""


_FEW_SHOT_EXAMPLES = """EXAMPLES (formatted as: USER text on one line, then JSON output)

USER: Compare LeBron and Jokic NBA playoff stats so far this year
{"context":"personal","domain":"unknown","activity":"researching","project":["unknown"],"tags":["basketball"],"notes":"Personal sports interest, comparing stats."}

USER: My dockerized FastAPI service crashes with SIGSEGV when handling concurrent uploads. How do I debug this?
{"context":"business","domain":"engineering","activity":"investigating","project":["unknown"],"tags":["debugging","python","docker"],"notes":"Engineering debugging request, multiple specific tags fit."}

USER: yes
{"context":"unknown","domain":"unknown","activity":"unknown","project":["unknown"],"tags":[],"notes":"Single affirmation; no signal for any facet."}

USER: Plan a 2-week trip to Japan in March focusing on food markets and cooking classes
{"context":"personal","domain":"unknown","activity":"planning","project":["unknown"],"tags":["travel","food"],"notes":"Personal trip planning combining travel and food themes."}

USER: Write me a blog post announcing our new pricing tiers for the marketing site
{"context":"business","domain":"marketing","activity":"building","project":["unknown"],"tags":[],"notes":"Marketing copy creation; no specific taxonomy leaf is the central topic."}

USER: I think I'm depressed and don't know what to do
{"context":"personal","domain":"unknown","activity":"researching","project":["unknown"],"tags":["mental-health"],"notes":"Personal mental-health concern; sensitive but the leaf 'mental-health' captures it."}

USER: Refactor this CRM sync code to use exponential backoff on 429s and add a feature flag
{"context":"business","domain":"engineering","activity":"improving","project":["crm-sync"],"tags":["python","api-design"],"notes":"Improving existing engineering code; project named in message."}
"""


_TAXONOMY_HEADER = """TAXONOMY (hybrid-v2)

The taxonomy is a tree with a root, work / personal mid-tier branches, and ~300 leaves.
Use ONLY leaf names (the lowest level — the names appearing as keys without further
'children:' below them). Leaf names use kebab-case ('mental-health', not 'mentalHealth').
"""


def _read_taxonomy_yaml() -> str:
    """Inline the hybrid-v2 taxonomy YAML — cached, never changes per request."""
    here = Path(__file__).resolve().parents[3]
    path = here / "sources" / "declawsified-core" / "declawsified_core" / "data" / "taxonomies" / "hybrid-v2.yaml"
    return path.read_text(encoding="utf-8")


def system_prompt_blocks() -> list[dict]:
    """Build the cached system prompt as a list of text blocks.

    Three blocks total. Cache control is on the last one — that single
    breakpoint caches all three plus the taxonomy that immediately
    precedes it.
    """
    taxonomy_yaml = _read_taxonomy_yaml()
    body = (
        _SYSTEM_INSTRUCTIONS
        + "\n\n"
        + _TAXONOMY_HEADER
        + "\n```yaml\n"
        + taxonomy_yaml
        + "\n```\n\n"
        + _FEW_SHOT_EXAMPLES
        + "\nReturn JSON only — no surrounding prose, no markdown fences."
    )
    return [
        {
            "type": "text",
            "text": body,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
    ]


def render_user_message(text: str) -> str:
    """Wrap a sample text into the user prompt body."""
    return f"USER: {text}\nReturn JSON only."
