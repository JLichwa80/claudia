# Changes from Original Claudia

This document describes all modifications made to [kbanc85/claudia](https://github.com/kbanc85/claudia) in this fork. The goal is local model support — running Claudia without Anthropic's API by redirecting Claude Code to a local inference server (LM Studio, Ollama, llama.cpp, or mlx-lm).

No template files, skills, rules, agents, or hooks were modified. All Claudia behavior and personality is unchanged.

---

## New Files

### `launch.py`

Gradio web UI launcher — the primary entry point for configuring and launching Claudia.
Opens a browser UI at `http://localhost:7860`.

**Requires:** `pip install gradio` (see `requirements.txt`)

**UI features:**
- **Provider toggle** — switch between Local (LM Studio) and Claude (Anthropic) without editing any files
- **LM Studio status panel** — live connection badge, GPU/RAM hardware info, GPU offload reminder
- **Model selection** — dropdown populated from the LM Studio API; or fixed Claude model list for Anthropic
- **Workspace management** — pick an existing workspace or create a new one (templates installed automatically)
- **How it works accordion** — shows the exact env vars used for each provider
- **Launch button** — opens a new terminal window with env vars set and `claude` running in the workspace
- **Config persistence** — saves last-used provider/model/workspace to `~/.claudia/launch-config.json`

**CLI flags:**
- `--port <n>` — override LM Studio port (default 1234)
- `--ui-port <n>` — override Gradio port (default 7860)
- `--cli` — fall back to interactive terminal menus (no Gradio required)

### `requirements.txt`

Python dependency file. Contains `gradio>=4.0` for the web UI launcher.

### `start-local.ps1`

Thin Windows PowerShell wrapper — delegates to `launch.py`.

### `start-local.sh`

Thin Mac/Linux bash wrapper — delegates to `launch.py`.

### `LOCAL_MODELS.md`

Setup guide covering:
- How the env var redirect works
- Platform-specific instructions (Windows/LM Studio, Mac/MLX, Linux/Ollama)
- Recommended models and GGUF quant guidance
- Startup script usage
- Memory daemon embedding provider switch
- Troubleshooting table

### `CHANGES.md`

This file.

---

## Modified Files

### `memory-daemon/claudia_memory/config.py`

**What changed:** Added three new fields to `MemoryConfig` and their corresponding loaders in `MemoryConfig.load()`.

**New fields:**
```python
embed_provider: str = "ollama"           # "ollama" | "lmstudio"
lmstudio_base_url: str = "http://localhost:1234"
lmstudio_embed_model: str = "text-embedding-nomic-embed-text-v1.5"
```

**Why:** The memory daemon previously required Ollama for embeddings. These fields allow users who have LM Studio (but not Ollama) to use LM Studio's OpenAI-compatible embedding endpoint instead.

**How to configure:** Add to `~/.claudia/config.json`:
```json
{
  "embed_provider": "lmstudio",
  "lmstudio_base_url": "http://localhost:1234",
  "lmstudio_embed_model": "text-embedding-nomic-embed-text-v1.5"
}
```

**Backward compatibility:** Default value is `"ollama"` — existing installations are unaffected.

---

### `memory-daemon/claudia_memory/embeddings.py`

**What changed:** Added `LMStudioEmbeddingService` class and updated `get_embedding_service()` factory function.

**New class — `LMStudioEmbeddingService`:**
- Uses `httpx` (already a project dependency) to call LM Studio's OpenAI-compatible `/v1/embeddings` endpoint
- Implements the same interface as the existing `EmbeddingService`: `embed()`, `embed_sync()`, `embed_batch()`, `embed_batch_sync()`, `is_available()`, `is_available_sync()`, `close()`
- Checks server availability via GET `/v1/models` before embedding
- Reuses the existing `EmbeddingCache` class for LRU caching
- Logs a clear warning if LM Studio is unreachable

**Updated factory — `get_embedding_service()`:**
- Was: always returns `EmbeddingService` (Ollama)
- Now: checks `config.embed_provider` and returns `LMStudioEmbeddingService` when set to `"lmstudio"`, otherwise returns `EmbeddingService` (unchanged default behavior)

**Backward compatibility:** Default provider is `"ollama"` — the factory returns `EmbeddingService` by default, identical to the original behavior.

---

## What Was Not Changed

| Component | Status |
|-----------|--------|
| `template-v2/CLAUDE.md` | Unchanged |
| `template-v2/.claude/skills/` (41 skills) | Unchanged |
| `template-v2/.claude/rules/` | Unchanged |
| `template-v2/.claude/agents/` | Unchanged |
| `template-v2/.claude/hooks/` | Unchanged |
| `bin/index.js` (installer) | Unchanged |
| `visualizer/` (3D memory graph) | Unchanged |
| `memory-daemon/` (all other files) | Unchanged |
| `package.json` | Unchanged |

---

## Potential Upstream Contribution

The changes in this fork are minimal and additive. They could be proposed back to the original repo as:

- A PR adding `start-local.ps1`, `start-local.sh`, and `LOCAL_MODELS.md`
- A separate PR adding LM Studio embedding support to the memory daemon

The embedding changes follow the existing code patterns exactly (same dataclass field style in `config.py`, same service interface in `embeddings.py`) and add zero new dependencies.
