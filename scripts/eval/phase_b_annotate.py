"""
Phase B annotation — submits the DES samples to Anthropic Batch API for
5-facet labeling, then writes annotations.jsonl.

Inputs:
  data/eval/des-4000/samples.jsonl   (from phase_b_sample.py)

Outputs:
  data/eval/des-4000/batch_id.txt        (the submitted batch ID)
  data/eval/des-4000/annotations.jsonl   (parsed, validated 5-facet labels)
  data/eval/des-4000/annotations-failed.jsonl  (samples that didn't validate)

Configuration:
  Default model:  claude-sonnet-4-6  (Opus 4.7 cross-check uses --model claude-opus-4-7)
  Cache TTL:      1 hour (system prompt + few-shot + taxonomy ≈ 9K tokens)
  Output format:  output_config.format with json_schema (guaranteed parseable)
  Effort:         low + thinking disabled (deterministic classification, no reasoning needed)

Run:
    pip install -e "./sources/declawsified-eval[anthropic]"  # if not already
    export ANTHROPIC_API_KEY=...
    python scripts/eval/phase_b_annotate.py                  # submits + waits + collects
    python scripts/eval/phase_b_annotate.py --submit-only    # submit, exit immediately
    python scripts/eval/phase_b_annotate.py --collect <bid>  # collect prior batch
    python scripts/eval/phase_b_annotate.py --limit 100      # dev run on first 100 samples
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Add prompts/ for the sibling import.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "prompts"))
from des_annotation import (  # type: ignore[import-not-found]  # noqa: E402
    output_schema,
    render_user_message,
    system_prompt_blocks,
)

import anthropic  # noqa: E402
from anthropic.types.message_create_params import (  # noqa: E402
    MessageCreateParamsNonStreaming,
)
from anthropic.types.messages.batch_create_params import Request  # noqa: E402


_REPO_ROOT = Path(__file__).resolve().parents[2]
DES_DIR = _REPO_ROOT / "data" / "eval" / "des-4000"
SAMPLES_PATH = DES_DIR / "samples.jsonl"
BATCH_ID_PATH = DES_DIR / "batch_id.txt"
ANNOTATIONS_PATH = DES_DIR / "annotations.jsonl"
ANNOTATIONS_FAILED_PATH = DES_DIR / "annotations-failed.jsonl"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 512
POLL_INTERVAL_SECONDS = 30


# ---------------------------------------------------------------------------
# Loading samples
# ---------------------------------------------------------------------------


@dataclass
class Sample:
    id: str
    text: str
    metadata: dict


def load_samples(path: Path, limit: int | None) -> list[Sample]:
    out: list[Sample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out.append(Sample(id=row["id"], text=row["text"], metadata=row.get("metadata", {})))
            if limit is not None and len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------------------
# Batch submission
# ---------------------------------------------------------------------------


def build_batch_requests(
    samples: list[Sample],
    model: str,
    max_tokens: int,
) -> list[Request]:
    sys_blocks = system_prompt_blocks()
    schema = output_schema()
    requests: list[Request] = []
    for s in samples:
        requests.append(Request(
            custom_id=s.id,
            params=MessageCreateParamsNonStreaming(
                model=model,
                max_tokens=max_tokens,
                system=sys_blocks,
                messages=[{"role": "user", "content": render_user_message(s.text)}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
                thinking={"type": "disabled"},
            ),
        ))
    return requests


def submit_batch(client: anthropic.Anthropic, requests: list[Request]) -> str:
    print(f"submitting batch of {len(requests)} requests...")
    batch = client.messages.batches.create(requests=requests)
    print(f"  batch_id: {batch.id}")
    print(f"  status:   {batch.processing_status}")
    BATCH_ID_PATH.write_text(batch.id, encoding="utf-8")
    return batch.id


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


def wait_for_batch(client: anthropic.Anthropic, batch_id: str) -> object:
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        c = batch.request_counts
        print(
            f"  [{datetime.now().strftime('%H:%M:%S')}] status={batch.processing_status:<12} "
            f"processing={c.processing} succeeded={c.succeeded} errored={c.errored} "
            f"canceled={c.canceled} expired={c.expired}"
        )
        if batch.processing_status == "ended":
            return batch
        time.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


def parse_results(client: anthropic.Anthropic, batch_id: str, samples: dict[str, Sample]) -> tuple[int, int]:
    """Stream results, write annotations.jsonl + failures."""
    n_ok = 0
    n_fail = 0
    with ANNOTATIONS_PATH.open("w", encoding="utf-8") as ok_f, \
         ANNOTATIONS_FAILED_PATH.open("w", encoding="utf-8") as fail_f:
        for result in client.messages.batches.results(batch_id):
            cid = result.custom_id
            sample = samples.get(cid)
            if result.result.type != "succeeded":
                fail_f.write(json.dumps({
                    "id": cid,
                    "result_type": result.result.type,
                    "error": getattr(result.result, "error", None) and getattr(result.result.error, "type", None),
                }) + "\n")
                n_fail += 1
                continue

            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                facets = json.loads(text)
            except Exception as exc:
                fail_f.write(json.dumps({
                    "id": cid, "result_type": "json_parse_failed",
                    "error": f"{type(exc).__name__}: {exc}", "raw": text[:500],
                }) + "\n")
                n_fail += 1
                continue

            if not _validate_facets(facets):
                fail_f.write(json.dumps({
                    "id": cid, "result_type": "schema_validation_failed",
                    "raw": text[:500], "parsed": facets,
                }) + "\n")
                n_fail += 1
                continue

            record = {
                "id": cid,
                "annotator": msg.model,
                "annotated_at": datetime.now(timezone.utc).isoformat(),
                "facets": {
                    "context":  facets["context"],
                    "domain":   facets["domain"],
                    "activity": facets["activity"],
                    "project":  facets["project"],
                    "tags":     facets["tags"],
                },
                "notes": facets.get("notes", ""),
                "usage": {
                    "input_tokens":              msg.usage.input_tokens,
                    "output_tokens":             msg.usage.output_tokens,
                    "cache_creation_input_tokens": msg.usage.cache_creation_input_tokens,
                    "cache_read_input_tokens":   msg.usage.cache_read_input_tokens,
                },
                "weak_labels": (sample.metadata.get("weak_labels") if sample else None) or {},
                "source": (sample.metadata.get("source") if sample else None)
                          or (sample.metadata.get("weak_labels", {}).get("source_dataset") if sample else None)
                          or "unknown",
            }
            ok_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_ok += 1
    return n_ok, n_fail


def _validate_facets(d: dict) -> bool:
    """Cheap structural check — schema enforced server-side, but be defensive."""
    from des_annotation import ACTIVITY_VALUES, CONTEXT_VALUES, DOMAIN_VALUES
    try:
        return (
            isinstance(d.get("context"), str) and d["context"] in CONTEXT_VALUES
            and isinstance(d.get("domain"), str) and d["domain"] in DOMAIN_VALUES
            and isinstance(d.get("activity"), str) and d["activity"] in ACTIVITY_VALUES
            and isinstance(d.get("project"), list)
            and isinstance(d.get("tags"), list)
            and all(isinstance(x, str) for x in d["project"])
            and all(isinstance(x, str) for x in d["tags"])
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cost summary
# ---------------------------------------------------------------------------


def summarize_usage(annotations_path: Path) -> None:
    if not annotations_path.exists():
        return
    cw = cr = inp = out = 0
    n = 0
    with annotations_path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            u = row.get("usage", {})
            cw += u.get("cache_creation_input_tokens", 0) or 0
            cr += u.get("cache_read_input_tokens", 0) or 0
            inp += u.get("input_tokens", 0) or 0
            out += u.get("output_tokens", 0) or 0
            n += 1
    # Sonnet 4.6 batch pricing (50% discount on standard rates)
    # Standard: input $3/M, output $15/M, cache_write_1h ~$3.75/M, cache_read $0.30/M
    cost_input  = inp * 3.0  / 1_000_000 * 0.5
    cost_output = out * 15.0 / 1_000_000 * 0.5
    cost_cw     = cw  * 3.75 / 1_000_000 * 0.5
    cost_cr     = cr  * 0.30 / 1_000_000 * 0.5
    print(f"\nUsage summary (n={n}):")
    print(f"  input_tokens         {inp:>10,}  ${cost_input:>7.4f}")
    print(f"  output_tokens        {out:>10,}  ${cost_output:>7.4f}")
    print(f"  cache_creation       {cw:>10,}  ${cost_cw:>7.4f}")
    print(f"  cache_read           {cr:>10,}  ${cost_cr:>7.4f}")
    print(f"  TOTAL                                  ${cost_input+cost_output+cost_cw+cost_cr:>7.4f}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main(args: argparse.Namespace) -> int:
    DES_DIR.mkdir(parents=True, exist_ok=True)
    samples = load_samples(SAMPLES_PATH, args.limit)
    samples_by_id = {s.id: s for s in samples}
    print(f"loaded {len(samples)} samples from {SAMPLES_PATH}")

    client = anthropic.Anthropic()

    if args.collect:
        batch_id = args.collect
    else:
        requests = build_batch_requests(samples, args.model, args.max_tokens)
        batch_id = submit_batch(client, requests)
        if args.submit_only:
            print(f"submit-only — batch_id saved to {BATCH_ID_PATH}. "
                  f"To collect later: --collect {batch_id}")
            return 0

    print(f"\npolling batch {batch_id} every {POLL_INTERVAL_SECONDS}s ...")
    wait_for_batch(client, batch_id)

    print("\nfetching results...")
    n_ok, n_fail = parse_results(client, batch_id, samples_by_id)
    print(f"  succeeded:  {n_ok}")
    print(f"  failed:     {n_fail}")
    print(f"  out: {ANNOTATIONS_PATH}")
    if n_fail:
        print(f"  failures:   {ANNOTATIONS_FAILED_PATH}")
    summarize_usage(ANNOTATIONS_PATH)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--limit", type=int, default=None,
                    help="cap on samples; useful for dev runs")
    ap.add_argument("--submit-only", action="store_true",
                    help="submit batch, save batch_id, exit")
    ap.add_argument("--collect", default=None,
                    help="skip submission, collect this batch_id instead")
    args = ap.parse_args()
    raise SystemExit(main(args))
