# Running Claudia with Local Models

Claudia can run entirely on a local model instead of Anthropic's API. Claude Code natively supports any server that speaks the Anthropic API format — three environment variables are all that's needed.

---

## Quick Start

### One-time prerequisites

1. **LM Studio** — installed, model downloaded (Qwen2.5-Coder-32B Q4_K_M recommended), GPU Layers set to **Max** in the model card, server started (Developer tab → Start Server)
2. **Gradio** — `pip install -r requirements.txt` (or `pip install gradio`)
3. **This repo** — cloned; no workspace needed yet, the launcher creates one

### Every session

```bash
python launch.py    # from the claudia directory
```

Browser opens at `http://localhost:7860`.

- Left panel queries LM Studio immediately — green badge if connected, GPU/RAM info shown
- **Model dropdown** is populated from whatever is loaded in LM Studio right now
- Pick your model → pick or create a workspace → click **Launch Claudia**
- A new terminal opens with the three redirect env vars set and `claude --model <id>` running inside the workspace

### Switching to Anthropic Claude

Same UI, no restart needed:

1. Click **Claude (Anthropic)** in the provider radio at the top
2. Status panel hides; API key input appears
3. Enter your `sk-ant-…` key — **not saved to disk**
4. Pick a Claude model (Sonnet 4.6 is the default)
5. Click **Launch Claudia** — new terminal with `ANTHROPIC_API_KEY` set, no URL override

### Config persistence

`~/.claudia/launch-config.json` saves the last provider, model, and workspace. Next time you run `python launch.py` all three are pre-selected — typically one click to relaunch.

---

## How It Works

Set these three environment variables before launching `claude`:

| Variable | Value |
|----------|-------|
| `ANTHROPIC_BASE_URL` | Your local server's base URL |
| `ANTHROPIC_API_KEY` | `""` (empty — disables Anthropic auth) |
| `ANTHROPIC_AUTH_TOKEN` | Any non-empty string (e.g. `local`) |

Then run: `claude --model <your-model-id>`

---

## Platform Guide

### Windows — LM Studio

LM Studio is the recommended option on Windows. It provides a GUI for model management, Vulkan GPU acceleration (including AMD integrated graphics), and an Anthropic-compatible API server.

**Setup:**
1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Download a model (see Recommended Models below)
3. Load the model, set GPU layers to maximum in model settings
4. Go to Developer tab and click **Start Server**
5. Confirm the server is running: `curl http://localhost:1234/v1/models`

**Launch Claudia:**
```powershell
.\start-local.ps1 -Model "your-model-id"
```

---

### Mac (Apple Silicon — M1/M2/M3/M4)

Apple Silicon Macs have unified memory (CPU and GPU share the same pool), which means large models run efficiently without a discrete GPU. You have two good options:

**Option A: LM Studio (recommended, easiest)**

LM Studio on Apple Silicon automatically uses **MLX** — Apple's native machine learning framework — for fast Metal GPU inference. You get the same GUI as Windows but with significantly better performance.

1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Download an MLX model (LM Studio auto-selects MLX format on Apple Silicon) or a GGUF model
3. Load the model and start the server (Developer tab)

```bash
./start-local.sh your-model-id
```

**Option B: Ollama + litellm proxy (more control)**

Ollama is popular on Mac but speaks OpenAI format, not Anthropic format. You need a lightweight proxy to translate:

```bash
pip install litellm
litellm --model ollama/qwen2.5-coder:32b --port 1234
```

Then set `ANTHROPIC_BASE_URL=http://localhost:1234` and run normally.

**Option C: mlx-lm (fastest on Apple Silicon, CLI only)**

For maximum performance on Apple Silicon without a GUI:

```bash
pip install mlx-lm
mlx_lm.server --model mlx-community/Qwen2.5-Coder-32B-Instruct-4bit --port 8080
```

mlx-lm uses OpenAI format — same litellm proxy as Ollama to bridge to Anthropic format.

**Performance note:** A 32B 4-bit model on M2/M3 Max with 64-96 GB unified memory runs at 20-40 tok/s — significantly faster than any Windows setup without a discrete GPU.

---

### Mac (Intel)

Intel Macs have no GPU acceleration for AI inference. Stick to smaller models:

- LM Studio with GGUF models (CPU only)
- 7B-14B models recommended; 32B will be very slow

---

### Linux

**Option A: LM Studio**

LM Studio is available on Linux (AppImage). Works with NVIDIA (CUDA), AMD (ROCm/Vulkan), and CPU.

```bash
chmod +x start-local.sh
./start-local.sh your-model-id
```

**Option B: Ollama**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:32b
# Then use litellm proxy to bridge to Anthropic format (same as Mac Option B)
```

**Option C: llama.cpp server**

```bash
./llama-server -m path/to/model.gguf --port 8080 -ngl 99  # -ngl offloads layers to GPU
```

llama.cpp speaks OpenAI format — use litellm proxy to bridge.

---

## Launcher

`launch.py` is the primary way to start Claudia. It opens a browser UI at `http://localhost:7860`.

**Install the dependency once:**
```bash
pip install gradio
```

**Start the launcher:**
```bash
python launch.py              # opens browser UI
python launch.py --port 8080  # if LM Studio is on a non-default port
python launch.py --cli        # terminal menus (no Gradio needed)
```

**Windows / Mac one-liner wrappers** (both delegate to `launch.py`):
```powershell
.\start-local.ps1          # Windows
./start-local.sh           # Mac/Linux
```

### What the UI lets you do

- **Switch providers** — toggle between Local (LM Studio) and Claude (Anthropic) with a radio button; no env var editing needed
- **See hardware** — GPU name, VRAM, RAM reported by LM Studio
- **Pick a model** — dropdown populated live from the LM Studio API, or fixed Claude model list
- **Manage workspaces** — select existing or create new (templates installed automatically)
- **Launch** — opens a new terminal with the right env vars and `claude` running

---

## Recommended Models

Tool calling (file reads, Bash execution, MCP memory tools) is essential for Claudia. These models handle it reliably:

| Model | Size | Best for |
|-------|------|----------|
| Qwen2.5-Coder-32B-Instruct | 32B | Best overall quality, use Q4_K_M on Windows/Linux |
| Qwen2.5-Coder-32B-Instruct (MLX 4-bit) | 32B | Apple Silicon — use `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` |
| Qwen2.5-Coder-14B-Instruct | 14B | Good balance, lower RAM requirement |
| Qwen2.5-14B-Instruct | 14B | Good if you prefer a general model over coder variant |

**GGUF quant guide (Windows/Linux):** Always prefer `Q4_K_M` over `Q4_K_S`. The ~1 GB difference buys meaningfully better instruction-following. Only use `Q4_K_S` if you are right at the edge of available memory.

**Minimum:** 14B parameters. Models below 7B tend to fail Claudia's multi-step tool use.

---

## Switching Back to Claude

The startup scripts only affect the current terminal session. To use Anthropic's Claude again, open a new terminal and run `claude` normally.

Or unset the variables explicitly:

```powershell
# Windows
Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_API_KEY, Env:ANTHROPIC_AUTH_TOKEN
```

```bash
# Mac/Linux
unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
```

---

## Memory Daemon Embeddings (Optional)

The memory daemon uses Ollama for embeddings by default. To replace Ollama with LM Studio (so nothing external is required), add to `~/.claudia/config.json`:

```json
{
  "embed_provider": "lmstudio",
  "lmstudio_base_url": "http://localhost:1234",
  "lmstudio_embed_model": "text-embedding-nomic-embed-text-v1.5"
}
```

Restart the memory daemon after saving. Make sure the embedding model is downloaded and loaded in LM Studio alongside your main model.

For Mac with mlx-lm or Ollama, keep `embed_provider` as `"ollama"` and point `ollama_host` at your embedding server.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `claude` shows authentication error | Make sure `ANTHROPIC_API_KEY` is empty (`""`) not unset |
| Model ID not found | Run `curl http://localhost:1234/v1/models` and use the `id` field exactly |
| Tool calls failing / Claudia confused | Model may be too small; try 32B or a stronger quant |
| Very slow responses | GPU offload not enabled; set GPU layers to max in LM Studio |
| Memory daemon won't start | Check that `embed_provider` is set correctly in `~/.claudia/config.json` |
