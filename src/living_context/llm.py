from __future__ import annotations

import json
import os

from living_context.observe import OBSERVATION_SCHEMA

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

INSTALL_HINT = (
    "Model-assisted extraction needs the Anthropic SDK:\n"
    "  pip install 'living-context-engine[llm]'   (or: pip install anthropic)\n"
    "Everything else in the engine runs without it. Without a key, use\n"
    "  lce prompt extract --input <file> > prompt.txt\n"
    "and paste the result into any assistant, then `lce absorb` its JSON reply."
)

SYSTEM = (
    "You convert raw observations into state updates for a Living Context Engine. "
    "You record entities, claims, evidence, and confidence — never document summaries. "
    "Every claim carries provenance. You never reconcile contradictions yourself: when a "
    "source disagrees with existing state, you record the new claim and let the engine "
    "hold both."
)


class LLMUnavailable(RuntimeError):
    """The optional model-assisted path is not usable in this environment."""


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _client():
    try:
        import anthropic
    except ImportError as error:  # pragma: no cover - exercised only without the SDK
        raise LLMUnavailable(INSTALL_HINT) from error
    return anthropic, anthropic.Anthropic()


def _text_from(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def _request(client, anthropic, model: str, effort: str, prompt: str):
    """Ask for the packet, with a server-side fallback if the SDK supports it."""
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": OBSERVATION_SCHEMA},
        },
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        return client.beta.messages.create(
            betas=[FALLBACK_BETA], fallbacks="default", **payload
        )
    except (TypeError, AttributeError):
        # Older SDK without the fallback parameter.
        return client.messages.create(**payload)
    except anthropic.BadRequestError as error:
        if "fallback" not in str(error).lower():
            raise
        return client.messages.create(**payload)


def extract_packet(
    prompt: str,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
) -> dict:
    """Run one extraction and return the observation packet.

    The prompt is the same text `lce prompt extract` prints, so the manual
    copy-paste path and this path produce identical packets.
    """
    anthropic, client = _client()
    if not (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    ):
        # An `ant auth login` profile also works; only warn, never block.
        pass

    try:
        response = _request(client, anthropic, model, effort, prompt)
    except anthropic.AuthenticationError as error:
        raise LLMUnavailable(
            "Anthropic credentials were rejected. Set ANTHROPIC_API_KEY or run `ant auth login`."
        ) from error
    except anthropic.RateLimitError as error:
        raise LLMUnavailable(f"Rate limited by the Anthropic API: {error}") from error
    except anthropic.APIConnectionError as error:
        raise LLMUnavailable(f"Could not reach the Anthropic API: {error}") from error
    except anthropic.APIStatusError as error:
        raise LLMUnavailable(f"Anthropic API error {error.status_code}: {error}") from error

    if response.stop_reason == "refusal":
        category = getattr(getattr(response, "stop_details", None), "category", None)
        raise LLMUnavailable(
            f"The model declined this source material (category: {category or 'unspecified'}). "
            "Extract it manually with `lce prompt extract`."
        )
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable(
            "The extraction was truncated at the output limit. Split the source into "
            "smaller files and ingest them separately."
        )

    text = _text_from(response).strip()
    if not text:
        raise LLMUnavailable("The model returned no content.")
    try:
        packet = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMUnavailable(f"The model returned invalid JSON: {error}") from error
    if not isinstance(packet, dict):
        raise LLMUnavailable("The model returned JSON that is not an observation packet.")
    return packet
