# better-litellm

A maintained fork of [LiteLLM](https://github.com/BerriAI/litellm) that patches critical gaps in local LLM proxy behavior when running llama.cpp-based models through llama-swap.

## Purpose

LiteLLM works well with cloud providers but struggles with edge cases from local OpenAI-compatible proxies. This fork addresses those gaps so that llama-swap + litellm can serve as a reliable local inference stack for AI agents.

### Problems this fork solves

1. **Tool call parsing failures** — Models served via llama-swap wrap JSON tool calls in `...` tags. LiteLLM's `_check_and_fix_if_content_is_tool_call()` passes the raw content (including tags) to `json.loads()`, which fails. The agent sees no tool call and treats it as a text response.
2. **Local-only config** — The puma-lan config has dozens of models across multiple machines. A lighter, focused config is needed for local development against a single llama-swap instance.

This fork provides focused patches and a streamlined local dev setup.

---

## Features

The fork adds patches to address local LLM proxy edge cases:

- **Tool Call Wrapper Tag Extraction** — Strips `...` wrapper tags from content before `json.loads()` in `_check_and_fix_if_content_is_tool_call()`, so tool calls from llama.cpp models are parsed correctly.

See **[FEATURES.md](./FEATURES.md)** for detailed descriptions and implementation specs.

---

## Installation

### Prerequisites

- **Python 3.10+** — [Install](https://www.python.org/downloads/)
- **uv** (recommended) — [Install](https://docs.astral.sh/uv/getting-started/installation/)
- **Git** — for fetching and building

### Quick Start (Local Dev)

```bash
# Clone the fork (if not already cloned)
cd ~/www/misc
git clone git@github.com:oleksii-honchar/better-litellm.git

# Install dependencies
cd better-litellm
uv sync

# Start the proxy with the mammoth config
./scripts/start-dev.sh
```

This starts the LiteLLM proxy on port 4000 with the mammoth llama-swap models. The proxy forwards `/v1/chat/completions` requests to `http://mammoth.lan:8014/v1`.

---

## Usage

### Using the Proxy Directly

Once the proxy is running:

```bash
# Test with curl
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwopus3.6-27b",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

### Configuring opencode to Use the Proxy

Point opencode at the better-litellm proxy instead of directly at the llama-swap endpoint:

```json
{
  "model": "qwopus3.6-27b",
  "baseURL": "http://127.0.0.1:4000/v1",
  "apiKey": "we-don't-need-an-api-key-for-llama-cpp"
}
```

The proxy translates the model name to the correct llama-swap model ID and handles the OpenAI-compatible routing.

---

## Runbook: Making Changes and Syncing with Source

For detailed governance procedures — fork structure, syncing with upstream, making changes, building, and pushing — see **[GOVERNANCE.md](./GOVERNANCE.md)**.

The governance document covers:
- Fork structure and branch conventions
- Upstream sync procedures (with conflict resolution)
- Feature branch workflow for adding patches
- Build and verification commands
- Push procedures and recovery scenarios

---

## Compatibility

This fork is **drop-in compatible** with the official LiteLLM proxy. All patches use non-breaking modifications — when the `...` tag stripping finds no tags, it returns the original content unchanged.

The `config.yaml` in the repo root is a subset of the puma-lan config and can be used independently.

---

## Deferred Features

- **Streaming tool call fixes** — The `_check_and_fix_if_content_is_tool_call()` patch covers non-streaming responses. Streaming tool calls may need similar treatment in the chunk assembler.
- **Custom llama-swap model routing** — Support for dynamic model switching based on request headers.
- **Health check for upstream llama-swap** — Pre-flight check against `mammoth.lan:8014` before starting the proxy.

---

## License

Apache 2.0 — Same as upstream LiteLLM.
