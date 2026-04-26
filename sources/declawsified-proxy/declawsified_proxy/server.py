"""
Transparent reverse proxy with async classification.

Forwards all requests from Claude Code to the real Anthropic API unchanged.
After each /v1/messages response, runs the classification pipeline
asynchronously (never blocking the response to Claude Code) and writes
results to the state file for the statusline plugin.

Handles both non-streaming and streaming (SSE) responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
from aiohttp import web

from declawsified_core.facets.base import FacetClassifier
from declawsified_core.models import ClassifyResult
from declawsified_core.pipeline import classify_with_session
from declawsified_core.session.history import CallHistoryStore
from declawsified_core.session.store import SessionStore

from declawsified_proxy.config import ProxyConfig
from declawsified_proxy.extractor import build_classify_input
from declawsified_proxy.spend_log import SpendLogger
from declawsified_proxy.state import StateManager

logger = logging.getLogger(__name__)

# Headers we must NOT forward (hop-by-hop or set by aiohttp).
_HOP_BY_HOP = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
    "keep-alive", "te", "trailers", "upgrade",
})

# Response headers we must additionally strip: aiohttp auto-decompresses
# the upstream body, so the original Content-Encoding header would lie to
# the client and trigger a decompression error.
_RESPONSE_STRIP = _HOP_BY_HOP | {"content-encoding"}


def _forward_headers(raw_headers: dict[str, str]) -> dict[str, str]:
    """Filter request headers for upstream forwarding."""
    return {
        k: v for k, v in raw_headers.items()
        if k.lower() not in _HOP_BY_HOP
    }


def _response_headers(upstream_headers: dict[str, str]) -> dict[str, str]:
    """Filter upstream response headers for client forwarding.

    Strips Content-Encoding because aiohttp ClientSession auto-decompresses
    the response body — forwarding the original encoding header would
    trigger a ZlibError on the client when it tries to decompress already-
    decompressed bytes.
    """
    return {
        k: v for k, v in upstream_headers.items()
        if k.lower() not in _RESPONSE_STRIP
    }


class ProxyServer:
    """aiohttp-based transparent proxy with classification side-channel."""

    def __init__(
        self,
        config: ProxyConfig,
        classifiers: list[FacetClassifier],
        session_store: SessionStore,
        history: CallHistoryStore,
    ) -> None:
        self._config = config
        self._classifiers = classifiers
        self._session_store = session_store
        self._history = history
        self._state = StateManager(config.state_file)
        self._spend_log = SpendLogger(config.spend_log_dir)
        self._http: aiohttp.ClientSession | None = None

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            # Generous timeout — Claude responses can stream for minutes
            # on long completions. No total cap; rely on socket-read.
            timeout = aiohttp.ClientTimeout(
                total=None, sock_connect=30, sock_read=600,
            )
            self._http = aiohttp.ClientSession(timeout=timeout)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()

    # ------------------------------------------------------------------
    # Classification (runs as a fire-and-forget task)
    # ------------------------------------------------------------------

    async def _classify_turn(
        self,
        request_body: dict,
        response_body: dict,
        raw_headers: dict[str, str],
    ) -> None:
        """Run classification on one completed turn. Never raises.

        Writes a spend-log row for every call we have a session_id for —
        including classifier failures (with `classifier_error` set) and
        meta-agent payloads (with `facets={}` and an explanatory error),
        so cost attribution doesn't silently drop calls.
        """
        classify_input = None
        cost = 0.0
        result = None
        classifier_error: str | None = None

        try:
            classify_input, cost = build_classify_input(
                request_body, response_body, raw_headers,
            )
        except Exception as exc:
            logger.exception("build_classify_input failed (non-fatal)")
            # Without a classify_input we have no session_id / model — can't
            # write a meaningful spend-log row either. Bail.
            return

        if classify_input.session_id is None:
            logger.debug("No session_id — skipping classification + spend log")
            return

        # Meta-agent payloads (compaction / summary / sub-agent) intentionally
        # skip classification — they hit every keyword and pollute every tag.
        # But the call still cost money, so we DO log it with an explanatory
        # `classifier_error` instead of dropping it silently.
        if not classify_input.messages:
            logger.info(
                "Classify skipped (meta-agent payload) session=%s",
                classify_input.session_id[:12],
            )
            self._write_spend_row(
                classify_input=classify_input,
                response_body=response_body,
                cost=cost,
                result=None,
                classifier_error="skipped: meta-agent payload",
            )
            return

        user_text = classify_input.messages[0].content[:200]

        try:
            result, _updates = await classify_with_session(
                classify_input,
                self._classifiers,
                self._session_store,
                self._history,
            )
        except Exception as exc:
            classifier_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Classification failed (non-fatal)")

        if result is not None:
            try:
                self._state.update(classify_input.session_id, result, cost)
            except Exception:
                logger.exception("State update failed (non-fatal)")

            tags = sorted(
                [c for c in result.classifications if c.facet == "tags"],
                key=lambda c: -c.confidence,
            )
            tags_str = ", ".join(
                f"{c.value}:{c.confidence:.2f}({c.source})" for c in tags
            ) or "(none)"
            logger.info(
                "Classify session=%s text=%r tags=[%s]",
                classify_input.session_id[:12],
                user_text,
                tags_str,
            )

        self._write_spend_row(
            classify_input=classify_input,
            response_body=response_body,
            cost=cost,
            result=result,
            classifier_error=classifier_error,
        )

    def _write_spend_row(
        self,
        *,
        classify_input,
        response_body: dict,
        cost: float,
        result,
        classifier_error: str | None,
    ) -> None:
        """Best-effort write to spend.jsonl. Never raises."""
        usage = (response_body or {}).get("usage", {}) or {}
        prompt_text = (
            classify_input.messages[0].content
            if classify_input.messages else ""
        )
        self._spend_log.append(
            call_id=classify_input.call_id,
            session_id=classify_input.session_id,
            timestamp=classify_input.timestamp,
            model=classify_input.model or "unknown",
            agent=classify_input.agent or "unknown",
            cost_usd=cost,
            tokens=usage,
            facets=(result.classifications if result is not None else None),
            prompt_text=prompt_text,
            pipeline_version=(result.pipeline_version if result is not None else None),
            classifier_error=classifier_error,
        )

    # ------------------------------------------------------------------
    # Request handling
    # ------------------------------------------------------------------

    async def _handle_messages(self, request: web.Request) -> web.StreamResponse:
        """Handle POST /v1/messages — the main classification target."""
        body_bytes = await request.read()
        try:
            request_body = json.loads(body_bytes)
        except json.JSONDecodeError:
            request_body = {}

        raw_headers = dict(request.headers)
        is_streaming = request_body.get("stream", False)

        upstream_url = f"{self._config.upstream_url}/v1/messages"
        fwd_headers = _forward_headers(raw_headers)

        http = await self._get_http()

        if is_streaming:
            return await self._handle_streaming(
                request, http, upstream_url, fwd_headers, body_bytes,
                request_body, raw_headers,
            )
        else:
            return await self._handle_non_streaming(
                http, upstream_url, fwd_headers, body_bytes,
                request_body, raw_headers,
            )

    async def _handle_non_streaming(
        self,
        http: aiohttp.ClientSession,
        upstream_url: str,
        fwd_headers: dict[str, str],
        body_bytes: bytes,
        request_body: dict,
        raw_headers: dict[str, str],
    ) -> web.Response:
        """Forward non-streaming request, classify after response."""
        try:
            async with http.post(
                upstream_url, headers=fwd_headers, data=body_bytes,
            ) as upstream_resp:
                resp_bytes = await upstream_resp.read()
                resp_headers = _response_headers(dict(upstream_resp.headers))
                upstream_status = upstream_resp.status

                response = web.Response(
                    status=upstream_status,
                    headers=resp_headers,
                    body=resp_bytes,
                )
        except (aiohttp.ClientConnectionError, ConnectionResetError) as exc:
            logger.warning("Client disconnected before upstream response: %s", exc)
            return web.json_response(
                {
                    "type": "error",
                    "error": {
                        "type": "upstream_error",
                        "message": f"declawsified-proxy client disconnect: {exc!r}",
                    },
                },
                status=502,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.exception("Upstream request failed: %r", exc)
            return web.json_response(
                {
                    "type": "error",
                    "error": {
                        "type": "upstream_error",
                        "message": f"declawsified-proxy upstream error: {exc!r}",
                    },
                },
                status=502,
            )

        # Fire classification asynchronously.
        if upstream_status == 200:
            try:
                response_body = json.loads(resp_bytes)
            except json.JSONDecodeError:
                response_body = {}
            asyncio.create_task(
                self._classify_turn(request_body, response_body, raw_headers)
            )

        return response

    async def _handle_streaming(
        self,
        request: web.Request,
        http: aiohttp.ClientSession,
        upstream_url: str,
        fwd_headers: dict[str, str],
        body_bytes: bytes,
        request_body: dict,
        raw_headers: dict[str, str],
    ) -> web.StreamResponse:
        """Forward SSE stream, accumulate events, classify on completion."""
        try:
            upstream_cm = http.post(
                upstream_url, headers=fwd_headers, data=body_bytes,
            )
            upstream_resp = await upstream_cm.__aenter__()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.exception("Upstream streaming connect failed: %r", exc)
            return web.json_response(
                {
                    "type": "error",
                    "error": {
                        "type": "upstream_error",
                        "message": f"declawsified-proxy upstream error: {exc!r}",
                    },
                },
                status=502,
            )

        try:
            resp_headers = _response_headers(dict(upstream_resp.headers))
            # Force chunked streaming.
            resp_headers.pop("content-length", None)
            resp_headers.pop("Content-Length", None)

            stream_response = web.StreamResponse(
                status=upstream_resp.status,
                headers=resp_headers,
            )
            stream_response.content_type = upstream_resp.content_type
            await stream_response.prepare(request)

            # Accumulate SSE events to reconstruct the full response.
            accumulated: dict[str, Any] = {}
            content_blocks: list[dict] = []
            usage: dict[str, int] = {}

            async for line_bytes in upstream_resp.content:
                # Forward every byte to the client immediately.
                await stream_response.write(line_bytes)

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "message_start":
                    msg = event.get("message", {})
                    accumulated["id"] = msg.get("id")
                    accumulated["model"] = msg.get("model")
                    accumulated["role"] = msg.get("role")
                    usage = msg.get("usage", {})

                elif event_type == "content_block_start":
                    block = event.get("content_block", {})
                    content_blocks.append(dict(block))

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    idx = event.get("index", len(content_blocks) - 1)
                    if 0 <= idx < len(content_blocks):
                        block = content_blocks[idx]
                        if delta.get("type") == "text_delta":
                            block["text"] = block.get("text", "") + delta.get("text", "")
                        elif delta.get("type") == "input_json_delta":
                            block.setdefault("_json_parts", []).append(
                                delta.get("partial_json", "")
                            )

                elif event_type == "message_delta":
                    delta_usage = event.get("usage", {})
                    usage.update(delta_usage)

            await stream_response.write_eof()
            upstream_status = upstream_resp.status
        except (aiohttp.ClientConnectionError, ConnectionResetError) as exc:
            # Client (Claude Code) closed the connection mid-stream. This is
            # normal traffic — the user hit Ctrl+C, the IDE died, the network
            # blipped, etc. Log at WARNING without a stack trace; not a server
            # error worth a 30-line traceback in the log every time.
            logger.warning(
                "Client disconnected mid-stream (recoverable): %s", exc,
            )
            try:
                await stream_response.write_eof()
            except Exception:
                pass
            return stream_response
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # Real upstream-side failure (Anthropic API). Keep the full
            # traceback — these are rare and worth investigating.
            logger.exception("Upstream streaming read failed mid-stream: %r", exc)
            try:
                await stream_response.write_eof()
            except Exception:
                pass
            return stream_response
        finally:
            await upstream_cm.__aexit__(None, None, None)

        # Reconstruct the full response for classification.
        if upstream_status == 200:
            # Finalize tool_use input from accumulated JSON parts.
            for block in content_blocks:
                if "_json_parts" in block:
                    full_json = "".join(block.pop("_json_parts"))
                    try:
                        block["input"] = json.loads(full_json)
                    except json.JSONDecodeError:
                        block["input"] = {}

            response_body: dict[str, Any] = {
                "content": content_blocks,
                "usage": usage,
                "model": accumulated.get("model"),
                "role": accumulated.get("role"),
            }
            asyncio.create_task(
                self._classify_turn(request_body, response_body, raw_headers)
            )

        return stream_response

    async def _handle_passthrough(self, request: web.Request) -> web.Response:
        """Forward any non-messages endpoint unchanged (no classification)."""
        body_bytes = await request.read()
        path = request.path
        upstream_url = f"{self._config.upstream_url}{path}"
        fwd_headers = _forward_headers(dict(request.headers))

        http = await self._get_http()
        method = request.method.upper()

        try:
            async with http.request(
                method, upstream_url, headers=fwd_headers, data=body_bytes,
            ) as upstream_resp:
                resp_bytes = await upstream_resp.read()
                resp_headers = _response_headers(dict(upstream_resp.headers))
                return web.Response(
                    status=upstream_resp.status,
                    headers=resp_headers,
                    body=resp_bytes,
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.exception("Upstream passthrough failed: %r", exc)
            return web.json_response(
                {
                    "type": "error",
                    "error": {
                        "type": "upstream_error",
                        "message": f"declawsified-proxy upstream error: {exc!r}",
                    },
                },
                status=502,
            )

    # ------------------------------------------------------------------
    # App factory
    # ------------------------------------------------------------------

    def create_app(self) -> web.Application:
        """Build the aiohttp application with routes."""
        # Anthropic API allows up to 32MB per request. aiohttp's default
        # client_max_size is 1MB which rejects normal Claude Code traffic
        # (full conversation history + system prompt + tools easily exceeds
        # that). Match Anthropic's limit so we forward without inspecting.
        app = web.Application(client_max_size=32 * 1024 * 1024)

        app.router.add_post("/v1/messages", self._handle_messages)
        # Catch-all for other endpoints (count_tokens, models, etc.)
        app.router.add_route("*", "/{path:.*}", self._handle_passthrough)

        async def on_cleanup(_app: web.Application) -> None:
            await self.close()

        app.on_cleanup.append(on_cleanup)
        return app
