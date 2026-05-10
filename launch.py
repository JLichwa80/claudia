#!/usr/bin/env python3
"""
launch.py - Claudia Local Model Configuration Dashboard

Reads and writes existing Claude Code and Claudia configurations.
Does NOT launch Claudia — you do that yourself with:
    claude              (Anthropic mode)
    ./start-local.ps1   (Local/LM Studio mode, Windows)
    ./start-local.sh    (Local/LM Studio mode, Mac/Linux)

Usage:
    python launch.py                  # Gradio web UI on :7860
    python launch.py --port 1234      # custom LM Studio port
    python launch.py --ui-port 7860   # custom Gradio port
    python launch.py --cli            # terminal menus (no Gradio needed)
"""

import json
import platform
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen, Request

# ── paths ─────────────────────────────────────────────────────────────────────
FORK_DIR      = Path(__file__).parent
LAUNCH_CONFIG = Path.home() / ".claudia" / "launch-config.json"
DAEMON_CONFIG = Path.home() / ".claudia" / "config.json"
OLLAMA_HOST   = "http://localhost:11434"
DAEMON_PORT   = 3848

CLAUDE_MODELS = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]
PROVIDER_LOCAL     = "Local (LM Studio)"
PROVIDER_ANTHROPIC = "Claude (Anthropic)"

# ── HTTP helpers (stdlib only) ────────────────────────────────────────────────

def _get(url: str, timeout: int = 5):
    try:
        with urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def _post(url: str, body: dict, timeout: int = 15):
    try:
        data = json.dumps(body).encode()
        req  = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

# ── System checks ─────────────────────────────────────────────────────────────

def check_lms(base_url: str) -> dict:
    """Query LM Studio: server state, all models (loaded + available), hardware."""
    result = {
        "connected": False, "models": [],
        "has_gpu": False, "gpu_name": None, "vram_gb": 0, "ram_gb": 0,
    }
    # v0/models returns all models with state; v1/models returns only loaded ones
    data = _get(f"{base_url}/api/v0/models")
    if data is not None:
        result["connected"] = True
        for m in data.get("data", []):
            result["models"].append({
                "id":     m.get("id", ""),
                "loaded": m.get("state", "") == "loaded",
                "arch":   m.get("arch", ""),
                "quant":  m.get("quantization", ""),
            })
    else:
        # fall back to v1 (only loaded models)
        data2 = _get(f"{base_url}/v1/models")
        if data2 is not None:
            result["connected"] = True
            for m in data2.get("data", []):
                result["models"].append({"id": m["id"], "loaded": True, "arch": "", "quant": ""})

    if not result["connected"]:
        return result

    hw = _get(f"{base_url}/api/v0/hardware", timeout=3)
    if hw:
        gpus = hw.get("gpuSurveyResult", {}).get("gpuInfo", [])
        mem  = hw.get("memoryInfo", {})
        if gpus:
            g = gpus[0]
            result["gpu_name"] = g.get("name", "Unknown GPU")
            result["vram_gb"]  = g.get("dedicatedMemoryCapacityBytes", 0) // 1024 ** 3
            result["has_gpu"]  = True
        result["ram_gb"] = mem.get("ramCapacity", 0) // 1024 ** 3
    else:
        sys_info = _get(f"{base_url}/api/v0/system", timeout=3)
        if sys_info:
            gpu = sys_info.get("gpu", {})
            if gpu:
                result["gpu_name"] = gpu.get("name", "Unknown GPU")
                result["vram_gb"]  = gpu.get("totalVramBytes", 0) // 1024 ** 3
                result["has_gpu"]  = True
            result["ram_gb"] = sys_info.get("ram", {}).get("totalBytes", 0) // 1024 ** 3
    return result


def check_ollama(host: str = OLLAMA_HOST) -> bool:
    return _get(f"{host}/api/tags", timeout=3) is not None


def check_memory_daemon() -> dict:
    data = _get(f"http://localhost:{DAEMON_PORT}/health", timeout=3)
    return {"running": bool(data), "status": (data or {}).get("status", "")}


def check_node() -> str | None:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

# ── LM Studio model management ────────────────────────────────────────────────

def lms_load_model(base_url: str, model_id: str) -> str:
    r = _post(f"{base_url}/api/v1/models/load",
              {"model": model_id, "gpu_offload": "max"}, timeout=30)
    return f"✓ Loading {model_id}…" if r is not None else f"✗ Load failed for {model_id}"


def lms_unload_model(base_url: str, model_id: str) -> str:
    r = _post(f"{base_url}/api/v1/models/unload", {"instance_id": model_id}, timeout=10)
    return "✓ Unloaded" if r is not None else "✗ Unload failed (model may already be unloaded)"

# ── Config read / write ───────────────────────────────────────────────────────

def read_daemon_config() -> dict:
    if not DAEMON_CONFIG.exists():
        return {}
    try:
        return json.loads(DAEMON_CONFIG.read_text())
    except Exception:
        return {}


def write_daemon_config(updates: dict):
    current = read_daemon_config()
    current.update(updates)
    DAEMON_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_CONFIG.write_text(json.dumps(current, indent=2))


def read_workspace_settings(ws: Path) -> dict:
    f = ws / ".claude" / "settings.local.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def write_workspace_settings(ws: Path, updates: dict):
    f = ws / ".claude" / "settings.local.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    current = read_workspace_settings(ws)
    current.update(updates)
    f.write_text(json.dumps(current, indent=2))


def write_start_scripts(ws: Path, model_id: str, lms_url: str):
    """Generate start-local.ps1 and start-local.sh with current settings."""
    ps1 = ws / "start-local.ps1"
    sh  = ws / "start-local.sh"

    ps1.write_text(
        f"# Generated by Claudia Local Config — run to use LM Studio instead of Anthropic\n"
        f"$env:ANTHROPIC_BASE_URL   = '{lms_url}'\n"
        f"$env:ANTHROPIC_API_KEY    = ''\n"
        f"$env:ANTHROPIC_AUTH_TOKEN = 'lm-studio'\n"
        f"claude --model '{model_id}'\n"
    )
    sh.write_text(
        f"#!/usr/bin/env bash\n"
        f"# Generated by Claudia Local Config — run to use LM Studio instead of Anthropic\n"
        f"export ANTHROPIC_BASE_URL='{lms_url}'\n"
        f"export ANTHROPIC_API_KEY=''\n"
        f"export ANTHROPIC_AUTH_TOKEN='lm-studio'\n"
        f"claude --model '{model_id}'\n"
    )
    try:
        sh.chmod(0o755)
    except Exception:
        pass


def apply_config(ws: Path, provider: str, model_id: str, lms_url: str) -> list[str]:
    """Write settings.local.json and (for local) the start scripts. Returns log lines."""
    log = []
    write_workspace_settings(ws, {"model": model_id})
    log.append(f"✓ {ws / '.claude' / 'settings.local.json'}  →  model: {model_id}")

    if provider == PROVIDER_LOCAL:
        write_start_scripts(ws, model_id, lms_url)
        log.append(f"✓ {ws / 'start-local.ps1'}  (Windows launcher)")
        log.append(f"✓ {ws / 'start-local.sh'}   (Mac/Linux launcher)")
        log.append("")
        log.append("To launch Claudia with LM Studio:")
        log.append("  Windows : .\\start-local.ps1")
        log.append("  Mac/Linux: ./start-local.sh")
    else:
        log.append("")
        log.append("To launch Claudia with Anthropic Claude:")
        log.append("  claude")
    return log


def save_launch_config(provider: str, ws: Path, model_id: str, lms_url: str):
    LAUNCH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_CONFIG.write_text(json.dumps({
        "provider":  provider,
        "workspace": str(ws),
        "model_id":  model_id,
        "lms_url":   lms_url,
    }, indent=2))


def load_launch_config() -> dict:
    if not LAUNCH_CONFIG.exists():
        return {}
    try:
        return json.loads(LAUNCH_CONFIG.read_text())
    except Exception:
        return {}

# ── Workspace helpers ─────────────────────────────────────────────────────────

def workspace_status(ws: Path) -> str:
    if (ws / "context" / "me.md").exists():
        return "ready"
    if (ws / "CLAUDE.md").exists():
        return "installed"
    return "not a Claudia workspace"


def find_claudia_workspaces() -> list[Path]:
    """Suggest likely Claudia workspace locations."""
    candidates = []
    for root in [
        Path.home() / "claudia-workspaces",
        Path.home() / "claudia",
        Path.home() / ".claudia" / "workspace",
        Path.cwd(),
    ]:
        if root.exists() and (root / "CLAUDE.md").exists():
            candidates.append(root)
        elif root.exists() and root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "CLAUDE.md").exists():
                    candidates.append(d)
    return list(dict.fromkeys(candidates))  # deduplicate, preserve order

# ── Gradio UI ─────────────────────────────────────────────────────────────────

def build_ui(lms_port: int):
    import gradio as gr

    lms_base_url = f"http://localhost:{lms_port}"

    # ── HTML helpers ──────────────────────────────────────────────────────────

    def _row(label: str, state: str, detail: str = "") -> str:
        color = {"ok": "#22c55e", "warn": "#f59e0b", "error": "#ef4444"}.get(state, "#94a3b8")
        mark  = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(state, "·")
        det   = f' <span style="color:#94a3b8;font-size:0.78rem">{detail}</span>' if detail else ""
        return (
            f'<div style="display:flex;align-items:center;gap:8px;padding:3px 0">'
            f'<span style="color:{color};font-weight:700;width:14px;text-align:center">{mark}</span>'
            f'<span style="font-size:0.875rem">{label}</span>{det}</div>'
        )

    def build_status_html(lms: dict, daemon: dict, ollama: bool,
                          node: str | None, embed_prov: str) -> str:
        rows = []
        # LM Studio
        if lms["connected"]:
            n = sum(1 for m in lms["models"] if m["loaded"])
            rows.append(_row("LM Studio", "ok", f"{n} model(s) loaded"))
        else:
            rows.append(_row("LM Studio", "error", "server not running"))
        # Memory daemon
        rows.append(_row("Memory Daemon",
                          "ok" if daemon["running"] else "warn",
                          daemon.get("status", "") if daemon["running"] else "not running"))
        # Embeddings
        if embed_prov == "lmstudio":
            rows.append(_row("Embeddings", "ok" if lms["connected"] else "warn",
                              "LM Studio" + ("" if lms["connected"] else " — server down")))
        else:
            rows.append(_row("Embeddings", "ok" if ollama else "warn",
                              "Ollama" + ("" if ollama else " — not running")))
        # Ollama
        rows.append(_row("Ollama", "ok" if ollama else "warn",
                          "" if ollama else "not running"))
        # Node.js
        rows.append(_row("Node.js", "ok" if node else "error", node or "not found"))
        # Python
        rows.append(_row("Python", "ok", f"v{sys.version.split()[0]}"))
        # GPU
        if lms["has_gpu"]:
            rows.append(_row("GPU", "ok", f"{lms['gpu_name']} · {lms['vram_gb']} GB VRAM"))
            rows.append(_row("RAM", "ok", f"{lms['ram_gb']} GB"))

        return '<div style="font-family:system-ui,sans-serif">' + "".join(rows) + "</div>"

    def build_models_html(models: list) -> str:
        if not models:
            return "<p style='color:#888;font-size:0.85rem;margin:0'>No models found. Is LM Studio server running?</p>"
        rows = []
        for m in models:
            dot   = "🟢" if m["loaded"] else "⚪"
            state = "loaded" if m["loaded"] else "available"
            extra = f' <span style="color:#94a3b8">{m["quant"]}</span>' if m["quant"] else ""
            rows.append(
                f'<tr style="border-bottom:1px solid #f1f5f9">'
                f'<td style="padding:5px 6px">{dot}</td>'
                f'<td style="padding:5px 6px;font-size:0.8rem;font-family:monospace">{m["id"]}{extra}</td>'
                f'<td style="padding:5px 6px;color:#64748b;font-size:0.78rem">{state}</td>'
                f'</tr>'
            )
        return (
            '<table style="width:100%;border-collapse:collapse">'
            '<tr style="background:#f8fafc"><th style="padding:3px 6px;text-align:left;'
            'font-size:0.75rem;color:#64748b;font-weight:500"></th>'
            '<th style="padding:3px 6px;text-align:left;font-size:0.75rem;color:#64748b;font-weight:500">Model</th>'
            '<th style="padding:3px 6px;text-align:left;font-size:0.75rem;color:#64748b;font-weight:500">State</th>'
            '</tr>'
            + "".join(rows) + "</table>"
        )

    def build_ws_badge_html(ws_path_str: str) -> str:
        if not ws_path_str or not ws_path_str.strip():
            return ""
        ws = Path(ws_path_str.strip()).expanduser().resolve()
        if not ws.exists():
            return '<div style="color:#ef4444;font-size:0.85rem">Path does not exist.</div>'
        status = workspace_status(ws)
        colors = {"ready": "#22c55e", "installed": "#f59e0b"}
        color  = colors.get(status, "#94a3b8")
        model  = read_workspace_settings(ws).get("model", "")
        model_line = (f'<br><span style="font-size:0.75rem;color:#64748b">'
                      f'settings.local.json → <code>{model}</code></span>') if model else ""
        return (
            f'<div style="padding:8px 12px;border-radius:6px;border:1px solid #e5e7eb;margin-top:6px">'
            f'<span style="color:{color};font-weight:600">{status}</span>{model_line}</div>'
        )

    # ── Event handlers ────────────────────────────────────────────────────────

    def refresh():
        daemon_cfg  = read_daemon_config()
        embed_prov  = daemon_cfg.get("embed_provider", "ollama")
        lms         = check_lms(lms_base_url)
        daemon      = check_memory_daemon()
        ollama      = check_ollama()
        node        = check_node()

        all_ids    = [m["id"] for m in lms["models"]]
        loaded_ids = [m["id"] for m in lms["models"] if m["loaded"]]

        last      = load_launch_config()
        last_model = last.get("model_id")
        def_model  = last_model if last_model in loaded_ids else (loaded_ids[0] if loaded_ids else None)

        # Daemon config defaults
        embed_model = (daemon_cfg.get("embedding_model", "all-minilm:l6-v2")
                       if embed_prov == "ollama"
                       else daemon_cfg.get("lmstudio_embed_model",
                                           "text-embedding-nomic-embed-text-v1.5"))
        cog_model = daemon_cfg.get("language_model", "qwen3:4b")
        ollama_host_val = daemon_cfg.get("ollama_host", OLLAMA_HOST)

        return (
            build_status_html(lms, daemon, ollama, node, embed_prov),
            build_models_html(lms["models"]),
            gr.update(choices=all_ids,    value=all_ids[0] if all_ids else None,
                      interactive=bool(all_ids)),         # model_action_dd
            gr.update(choices=loaded_ids, value=def_model,
                      interactive=bool(loaded_ids)),     # launch_model_dd
            gr.update(value=embed_prov),                  # embed_radio
            gr.update(value=embed_model),                 # embed_model_box
            gr.update(value=ollama_host_val),             # ollama_host_box
            gr.update(value=cog_model),                   # cognitive_box
        )

    REFRESH_N = 8

    def on_provider_change(provider):
        is_local = provider == PROVIDER_LOCAL
        return (
            gr.update(visible=is_local),       # lms_section
            gr.update(visible=not is_local),   # anthropic_section
            gr.update(visible=is_local),       # launch_model_dd
            gr.update(visible=not is_local),   # claude_model_dd
        )

    def on_ws_input(ws_str):
        return build_ws_badge_html(ws_str)

    def on_load(model_id):
        if not model_id:
            return "Select a model first."
        return lms_load_model(lms_base_url, model_id)

    def on_unload(model_id):
        if not model_id:
            return "Select a model first."
        return lms_unload_model(lms_base_url, model_id)

    def on_save_daemon(embed_prov, embed_model, ollama_host_val, cog_model):
        updates = {"embed_provider": embed_prov, "language_model": cog_model}
        if embed_prov == "ollama":
            updates["embedding_model"] = embed_model
            updates["ollama_host"]     = ollama_host_val
        else:
            updates["lmstudio_embed_model"] = embed_model
            updates["lmstudio_base_url"]    = lms_base_url
        write_daemon_config(updates)
        return "✓ Saved ~/.claudia/config.json — restart memory daemon to apply."

    def on_apply(provider, local_model, claude_model, ws_str):
        if not ws_str or not ws_str.strip():
            return "⚠️ Enter a workspace path."
        ws = Path(ws_str.strip()).expanduser().resolve()
        if not ws.exists():
            return f"⚠️ Path does not exist: {ws}"
        if workspace_status(ws) == "not a Claudia workspace":
            return f"⚠️ No CLAUDE.md found at {ws} — is this a Claudia workspace?"

        if provider == PROVIDER_LOCAL:
            if not local_model:
                return "⚠️ No model selected. Load a model in LM Studio first."
            model_id = local_model
        else:
            model_id = claude_model

        log = apply_config(ws, provider, model_id, lms_base_url)
        save_launch_config(provider, ws, model_id, lms_base_url)
        return "\n".join(log)

    # ── Layout ────────────────────────────────────────────────────────────────

    last_cfg  = load_launch_config()
    last_prov = last_cfg.get("provider", PROVIDER_LOCAL)
    last_ws   = last_cfg.get("workspace", "")
    dmon_cfg  = read_daemon_config()

    suggested = find_claudia_workspaces()
    ws_placeholder = str(suggested[0]) if suggested else "~/claudia-workspaces/my-workspace"

    with gr.Blocks(title="Claudia · Local Config", theme=gr.themes.Soft()) as app:
        gr.Markdown(
            "# Claudia &nbsp;·&nbsp; Local Model Configuration\n"
            "Configures your existing Claudia workspace to use LM Studio or Anthropic Claude.\n"
            "**No launcher** — you run `claude` (or `./start-local.ps1`) yourself."
        )

        with gr.Row(equal_height=False):

            # ── Left: System Status ────────────────────────────────────────────
            with gr.Column(scale=1, min_width=200):
                gr.Markdown("### System Status")
                status_html = gr.HTML("<p style='color:#888'>Loading…</p>")
                refresh_btn = gr.Button("↻ Refresh", size="sm", variant="secondary")

            # ── Middle: LLM Configuration ──────────────────────────────────────
            with gr.Column(scale=2, min_width=360):
                gr.Markdown("### LLM Provider")
                provider_radio = gr.Radio(
                    [PROVIDER_LOCAL, PROVIDER_ANTHROPIC],
                    value=last_prov, label="Provider",
                )

                # Local section
                with gr.Column(visible=(last_prov == PROVIDER_LOCAL)) as lms_section:
                    gr.Markdown("**LM Studio Models**")
                    models_html    = gr.HTML()
                    model_action_dd = gr.Dropdown(label="Select model to load / unload",
                                                   interactive=True, allow_custom_value=True)
                    with gr.Row():
                        load_btn   = gr.Button("▶ Load",   size="sm", variant="secondary")
                        unload_btn = gr.Button("■ Unload", size="sm", variant="secondary")
                    lms_result = gr.Textbox(label="", interactive=False, lines=1,
                                             show_label=False)

                # Anthropic section
                with gr.Column(visible=(last_prov == PROVIDER_ANTHROPIC)) as anthropic_section:
                    gr.Markdown(
                        "Select the Claude model to write to `settings.local.json`. "
                        "Your existing Claude Code auth is used — no key needed here."
                    )
                    claude_model_dd = gr.Dropdown(
                        label="Claude Model", choices=CLAUDE_MODELS, value=CLAUDE_MODELS[1],
                        visible=(last_prov == PROVIDER_ANTHROPIC),
                    )

                gr.Markdown("---")
                gr.Markdown(
                    "### Memory Daemon\n"
                    "Configures `~/.claudia/config.json`. Restart the daemon after saving."
                )
                embed_radio   = gr.Radio(["ollama", "lmstudio"], label="Embed provider",
                                          value=dmon_cfg.get("embed_provider", "ollama"))
                embed_model_box = gr.Textbox(
                    label="Embedding model",
                    value=dmon_cfg.get("embedding_model", "all-minilm:l6-v2"),
                    info="Ollama: all-minilm:l6-v2 · LM Studio: text-embedding-nomic-embed-text-v1.5",
                )
                ollama_host_box = gr.Textbox(
                    label="Ollama host", value=dmon_cfg.get("ollama_host", OLLAMA_HOST),
                )
                cognitive_box = gr.Textbox(
                    label="Cognitive model",
                    value=dmon_cfg.get("language_model", "qwen3:4b"),
                    info="Used internally for memory consolidation — not for chat.",
                )
                save_daemon_btn = gr.Button("Save Memory Config", size="sm", variant="secondary")
                daemon_result   = gr.Textbox(label="", interactive=False, lines=1,
                                              show_label=False)

            # ── Right: Workspace ───────────────────────────────────────────────
            with gr.Column(scale=1, min_width=240):
                gr.Markdown("### Workspace")
                gr.Markdown(
                    "Point to an existing Claudia workspace "
                    "(created with `npx get-claudia`).",
                    elem_classes=["dim"]
                )
                ws_box = gr.Textbox(
                    label="Workspace path", value=last_ws,
                    placeholder=ws_placeholder,
                    info="Absolute or ~ path to your Claudia workspace directory.",
                )
                ws_badge = gr.HTML(build_ws_badge_html(last_ws))

                if suggested:
                    gr.Markdown("**Detected workspaces:**")
                    for s in suggested[:4]:
                        gr.Markdown(f"- `{s}`")

                gr.Markdown("---")
                gr.Markdown("### Apply")
                launch_model_dd = gr.Dropdown(
                    label="Local model (for launch scripts)",
                    interactive=False,
                    visible=(last_prov == PROVIDER_LOCAL),
                )
                apply_btn    = gr.Button("Apply Configuration", variant="primary")
                apply_result = gr.Textbox(label="Result", interactive=False, lines=8)

                with gr.Accordion("What gets written", open=False):
                    gr.Markdown("""
**`<workspace>/.claude/settings.local.json`**
```json
{ "model": "<selected-model>" }
```
Claude Code reads this automatically. Gitignored.

**`<workspace>/start-local.ps1`** (Local mode only)
Pre-filled with `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY=""`,
`ANTHROPIC_AUTH_TOKEN`, and `claude --model <id>`.

**`<workspace>/start-local.sh`** (Local mode only)
Same as above for Mac/Linux.
""")

        # ── Wiring ────────────────────────────────────────────────────────────
        refresh_outputs = [
            status_html, models_html,
            model_action_dd, launch_model_dd,
            embed_radio, embed_model_box, ollama_host_box, cognitive_box,
        ]

        app.load(refresh, outputs=refresh_outputs)
        refresh_btn.click(refresh, outputs=refresh_outputs)

        provider_radio.change(
            on_provider_change, [provider_radio],
            [lms_section, anthropic_section, launch_model_dd, claude_model_dd],
        )
        ws_box.change(on_ws_input, [ws_box], [ws_badge])
        ws_box.blur(on_ws_input, [ws_box], [ws_badge])

        load_btn.click(on_load, [model_action_dd], [lms_result])
        unload_btn.click(on_unload, [model_action_dd], [lms_result])

        save_daemon_btn.click(
            on_save_daemon,
            [embed_radio, embed_model_box, ollama_host_box, cognitive_box],
            [daemon_result],
        )
        apply_btn.click(
            on_apply,
            [provider_radio, launch_model_dd, claude_model_dd, ws_box],
            [apply_result],
        )

    return app


# ── CLI fallback ──────────────────────────────────────────────────────────────

class C:
    R = "\033[0m"; B = "\033[1m"; D = "\033[2m"
    C = "\033[96m"; G = "\033[92m"; Y = "\033[93m"; E = "\033[91m"

def _ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def _h(m): print(f"\n{C.C}{C.B}{m}{C.R}")
def _ok(m): print(f"  {C.G}✓{C.R} {m}")
def _w(m):  print(f"  {C.Y}⚠{C.R} {m}")
def _e(m):  print(f"  {C.E}✗{C.R} {m}")
def _i(m):  print(f"  {C.D}{m}{C.R}")

def _pick(items, prompt="Choice"):
    for i, it in enumerate(items, 1):
        print(f"  [{C.B}{i}{C.R}] {it}")
    while True:
        try:
            idx = int(input(f"\n  {prompt}: ").strip())
            if 1 <= idx <= len(items):
                return idx - 1
        except (ValueError, KeyboardInterrupt):
            pass


def cli_main(lms_port: int):
    _ansi()
    lms_base_url = f"http://localhost:{lms_port}"
    print(f"\n{C.B}{C.C}── Claudia · Local Config ──{C.R}")
    print("Configures your Claudia workspace. No launching — run claude yourself.\n")

    # Workspace
    _h("Workspace")
    suggestions = find_claudia_workspaces()
    if suggestions:
        print("  Detected:")
        for s in suggestions[:4]:
            _i(str(s))
    ws_str = input("\n  Workspace path (Enter to use first detected): ").strip()
    ws = Path(ws_str).expanduser().resolve() if ws_str else (suggestions[0] if suggestions else None)
    if not ws or not ws.exists():
        _e("No valid workspace path.")
        sys.exit(1)
    status = workspace_status(ws)
    _ok(f"Workspace: {ws}  [{status}]")

    # Provider
    _h("Provider")
    providers = [PROVIDER_LOCAL, PROVIDER_ANTHROPIC]
    provider  = providers[_pick(providers, "Provider")]

    if provider == PROVIDER_LOCAL:
        _h(f"LM Studio ({lms_base_url})")
        lms = check_lms(lms_base_url)
        if not lms["connected"]:
            _e("LM Studio not reachable. Start the server (Developer tab → Start Server).")
            sys.exit(1)
        loaded = [m["id"] for m in lms["models"] if m["loaded"]]
        if not loaded:
            _e("No models loaded. Load a model in LM Studio first.")
            sys.exit(1)
        model_id = loaded[_pick(loaded, "Model")]
    else:
        _h("Claude (Anthropic)")
        model_id = CLAUDE_MODELS[_pick(CLAUDE_MODELS, "Model")]

    _ok(f"Model: {model_id}")

    # Apply
    _h("Applying configuration…")
    log = apply_config(ws, provider, model_id, lms_base_url)
    save_launch_config(provider, ws, model_id, lms_base_url)
    for line in log:
        print(f"  {line}" if line else "")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args     = sys.argv[1:]
    use_cli  = "--cli" in args
    lms_port = 1234
    ui_port  = 7860

    for flag, target in [("--port", "lms"), ("--ui-port", "ui")]:
        if flag in args:
            try:
                val = int(args[args.index(flag) + 1])
                if target == "lms":
                    lms_port = val
                else:
                    ui_port = val
            except (IndexError, ValueError):
                pass

    if use_cli:
        cli_main(lms_port)
        return

    try:
        import gradio  # noqa: F401
    except ImportError:
        print("Gradio not installed. Run:  pip install gradio")
        print("Or use CLI mode:            python launch.py --cli")
        sys.exit(1)

    build_ui(lms_port).launch(server_port=ui_port, inbrowser=True, show_api=False)


if __name__ == "__main__":
    main()
