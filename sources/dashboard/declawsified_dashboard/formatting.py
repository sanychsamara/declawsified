"""Tiny formatting helpers used by every page.

Centralised so the dashboard, the CLI report, and any future BI export
agree on rendering — same precision rules for $ ranges, same cache-hit
display semantics.
"""

from __future__ import annotations


def money(x: float) -> str:
    """Currency formatting that adapts precision to magnitude."""
    if x >= 100:
        return f"${x:,.0f}"
    if x >= 1:
        return f"${x:.2f}"
    if x >= 0.001:
        return f"${x:.4f}"
    return f"${x:.6f}"


def pct(p: float) -> str:
    """Render a 0-100 percent number with one decimal, '—' when meaningless."""
    if p is None:
        return "—"
    return f"{p:.1f}%"


def cache_pct(read_tokens: int, total_input_tokens: int) -> str:
    if total_input_tokens <= 0:
        return "—"
    return f"{read_tokens / total_input_tokens * 100:.0f}%"


def humanize_age_seconds(s: float) -> str:
    """'just now', '3 minutes ago', '2 hours ago', '4 days ago'."""
    if s < 5:
        return "just now"
    if s < 60:
        return f"{int(s)}s ago"
    if s < 3600:
        return f"{int(s / 60)}m ago"
    if s < 86400:
        return f"{s / 3600:.1f}h ago"
    return f"{s / 86400:.1f}d ago"
