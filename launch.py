#!/usr/bin/env python3
"""
launch.py - Claudia × Local Models (Gradio web UI)

Default (Gradio web UI):
    python launch.py                  # opens browser at localhost:7860
    python launch.py --port 1234      # custom LM Studio port
    python launch.py --ui-port 7860   # custom Gradio port

Headless / scripted:
    python launch.py --cli            # interactive terminal menus
"""

import json
import platform
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

# ── paths ─────────────────────────────────────────────────────────────────────
FORK_DIR        = Path(__file__).parent
WORKSPACES_ROOT = Path.home() / "claudia-workspaces"
CONFIG_FILE     = Path.home() / ".claudia" / "launch-config.json"
CREATE_NEW      = "+ Create new workspace…"

CLAUDE_MODELS = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

PROVIDER_LOCAL     = "Local (LM Studio)"
PROVIDER_ANTHROPIC = "Claude (Anthropic)"

# ── LM Studio API (stdlib only) ───────────────────────────────────────────────

def _get(base_url: str, path: str, timeout: int = 5):
    try:
        with urlopen(f"{base_url}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def fetch_server_state(base_url: str) -> dict:
    state = {
        "connected": False,
        "models":    [],
        "gpu_name":  None,
        "vram_gb":   0,
        "ram_gb":    0,
        "has_gpu":   False,
    }
    data = _get(base_url, "/v1/models")
    if data is None:
        return state
    state["connected"] = True
    state["models"] = [m["id"] for m in data.get("data", [])]

    hw = _get(base_url, "/api/v0/hardware", timeout=3)
    if hw:
        gpus = hw.get("gpuSurveyResult", {}).get("gpuInfo", [])
        mem  = hw.get("memoryInfo", {})
        if gpus:
            g = gpus[0]
            state["gpu_name"] = g.get("name", "Unknown GPU")
            state["vram_gb"]  = g.get("dedicatedMemoryCapacityBytes", 0) // 1024 ** 3
            state["has_gpu"]  = True
        state["ram_gb"] = mem.get("ramCapacity", 0) // 1024 ** 3
    else:
        sys_info = _get(base_url, "/api/v0/system", timeout=3)
        if sys_info:
            gpu = sys_info.get("gpu", {})
            ram = sys_info.get("ram", {})
            if gpu:
                state["gpu_name"] = gpu.get("name", "Unknown GPU")
                state["vram_gb"]  = gpu.get("totalVramBytes", 0) // 1024 ** 3
                state["has_gpu"]  = True
            state["ram_gb"] = ram.get("totalBytes", 0) // 1024 ** 3
    return state


# ── config persistence ────────────────────────────────────────────────────────

def save_config(provider: str, base_url: str, model_id: str, workspace: Path):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "provider":  provider,
        "base_url":  base_url,
        "model_id":  model_id,
        "workspace": str(workspace),
    }
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


# ── workspace helpers ─────────────────────────────────────────────────────────

def list_workspaces() -> list:
    if not WORKSPACES_ROOT.exists():
        return []
    return [d.name for d in sorted(WORKSPACES_ROOT.iterdir()) if d.is_dir()]


def workspace_choices() -> list:
    return [CREATE_NEW] + list_workspaces()


def install_templates(workspace: Path):
    installer = FORK_DIR / "bin" / "index.js"
    if installer.exists():
        subprocess.run(["node", str(installer), str(workspace)], capture_output=True)


# ── terminal launcher ─────────────────────────────────────────────────────────

def launch_in_terminal(env: dict, model_id: str, workspace: str):
    """Open a new terminal window with env vars set and claude running."""
    ws = Path(workspace)

    # Build env-var setup strings for each shell flavor
    ps_pairs  = " ".join(f"$env:{k}='{v}';" for k, v in env.items())
    bash_pairs = " ".join(f"export {k}='{v}';" for k, v in env.items())

    ps_cmd   = f"{ps_pairs} Set-Location '{ws}'; claude --model '{model_id}'"
    bash_cmd = f"{bash_pairs} cd '{ws}' && claude --model '{model_id}'"

    system = platform.system()
    if system == "Windows":
        subprocess.Popen(
            ["powershell", "-NoExit", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    elif system == "Darwin":
        script = f'tell application "Terminal" to do script "{bash_cmd}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        for term, args in [
            ("gnome-terminal", ["--", "bash", "-c", bash_cmd + "; exec bash"]),
            ("konsole",        ["-e", "bash", "-c", bash_cmd + "; exec bash"]),
            ("xterm",          ["-e", f"bash -c '{bash_cmd}; exec bash'"]),
        ]:
            try:
                subprocess.Popen([term] + args)
                break
            except FileNotFoundError:
                continue


def env_for_local(base_url: str) -> dict:
    return {
        "ANTHROPIC_BASE_URL":   base_url,
        "ANTHROPIC_API_KEY":    "",
        "ANTHROPIC_AUTH_TOKEN": "lm-studio",
    }


def env_for_anthropic(api_key: str) -> dict:
    return {"ANTHROPIC_API_KEY": api_key}


# ── Gradio UI ─────────────────────────────────────────────────────────────────

def build_ui(lms_port: int):
    import gradio as gr

    lms_base_url = f"http://localhost:{lms_port}"

    # ── HTML helpers ──────────────────────────────────────────────────────────

    def badge_html(connected: bool) -> str:
        color = "#22c55e" if connected else "#ef4444"
        mark  = "✓" if connected else "✗"
        label = "Connected" if connected else "Unreachable"
        return (
            f'<div style="margin-bottom:10px">'
            f'<span style="display:inline-block;padding:5px 14px;border-radius:9999px;'
            f'background:{color};color:#fff;font-weight:600;font-size:0.9rem">'
            f'LM Studio &nbsp;{mark}&nbsp; {label}</span></div>'
        )

    def hardware_html(state: dict) -> str:
        if not state["connected"]:
            return "<p style='color:#888;margin:0'>Connect LM Studio to see hardware info.</p>"
        rows = []
        if state["has_gpu"]:
            rows.append(
                f'<tr><td style="padding:3px 10px 3px 0;color:#888">GPU</td>'
                f'<td><b>{state["gpu_name"]}</b> &nbsp;{state["vram_gb"]} GB VRAM</td></tr>'
            )
        if state["ram_gb"]:
            rows.append(
                f'<tr><td style="padding:3px 10px 3px 0;color:#888">RAM</td>'
                f'<td>{state["ram_gb"]} GB</td></tr>'
            )
        if not rows:
            return "<p style='color:#888;margin:0'>Hardware info unavailable.</p>"
        return f'<table style="border-collapse:collapse;font-size:0.9rem">{"".join(rows)}</table>'

    def gpu_tip_html(state: dict) -> str:
        if not state["connected"] or not state["has_gpu"]:
            return ""
        return (
            '<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;'
            'padding:10px 14px;margin-top:10px;font-size:0.85rem;line-height:1.5">'
            '⚠️ &nbsp;<b>GPU offload</b>: Set <b>GPU Layers → Max</b> in the LM Studio '
            'model card before loading to use your full VRAM.</div>'
        )

    def model_count_html(state: dict) -> str:
        if not state["connected"]:
            return ""
        n = len(state["models"])
        if n == 0:
            return (
                '<div style="background:#fee2e2;border:1px solid #f87171;border-radius:6px;'
                'padding:8px 14px;margin-top:10px;font-size:0.85rem">'
                '✗ &nbsp;No models loaded. Load a model in LM Studio first.</div>'
            )
        return (
            f'<div style="color:#22c55e;margin-top:8px;font-size:0.85rem">'
            f'✓ &nbsp;{n} model{"s" if n != 1 else ""} available</div>'
        )

    # ── event handlers ────────────────────────────────────────────────────────

    def refresh_lms():
        state = fetch_server_state(lms_base_url)
        models = state["models"]

        last = load_config()
        last_model   = last.get("model_id")
        default_model = last_model if last_model in models else (models[0] if models else None)

        ws_list   = workspace_choices()
        last_ws   = Path(last.get("workspace", "")).name
        default_ws = last_ws if last_ws in ws_list else ws_list[0]

        return (
            badge_html(state["connected"]),
            hardware_html(state),
            gpu_tip_html(state),
            model_count_html(state),
            gr.update(choices=models, value=default_model, interactive=bool(models)),
            gr.update(choices=ws_list, value=default_ws),
        )

    def on_provider_change(provider):
        is_local = (provider == PROVIDER_LOCAL)
        return (
            gr.update(visible=is_local),   # lms_status_col
            gr.update(visible=is_local),   # local_model_dd
            gr.update(visible=not is_local),  # anthropic_col
        )

    def on_workspace_change(choice):
        return gr.update(visible=(choice == CREATE_NEW))

    def do_launch(provider, local_model, claude_model, api_key, ws_choice, new_ws_name):
        # Resolve workspace
        if ws_choice == CREATE_NEW:
            name = (new_ws_name or "my-claudia").strip() or "my-claudia"
            ws_path = WORKSPACES_ROOT / name
            ws_path.mkdir(parents=True, exist_ok=True)
            install_templates(ws_path)
        else:
            ws_path = WORKSPACES_ROOT / ws_choice

        if provider == PROVIDER_LOCAL:
            if not local_model:
                return "⚠️ No model selected. Is LM Studio running with a model loaded?"
            env = env_for_local(lms_base_url)
            model_id = local_model
        else:
            if not api_key or not api_key.strip():
                return "⚠️ Anthropic API key is required."
            if not claude_model:
                return "⚠️ No Claude model selected."
            env = env_for_anthropic(api_key.strip())
            model_id = claude_model

        save_config(provider, lms_base_url if provider == PROVIDER_LOCAL else "https://api.anthropic.com",
                    model_id, ws_path)
        launch_in_terminal(env, model_id, str(ws_path))

        return (
            f"✓ Launching Claudia in a new terminal window.\n"
            f"\n"
            f"Provider  : {provider}\n"
            f"Model     : {model_id}\n"
            f"Workspace : {ws_path}"
        )

    # ── layout ────────────────────────────────────────────────────────────────

    last_cfg     = load_config()
    last_provider = last_cfg.get("provider", PROVIDER_LOCAL)
    last_ws_name  = Path(last_cfg.get("workspace", "")).name
    ws_list       = workspace_choices()
    default_ws    = last_ws_name if last_ws_name in ws_list else ws_list[0]

    with gr.Blocks(title="Claudia × Local Models", theme=gr.themes.Soft()) as app:
        gr.Markdown(
            "# Claudia &nbsp;×&nbsp; Local Models\n"
            "Switch between a local LM Studio model and Anthropic's Claude."
        )

        # Provider toggle spans full width
        provider_radio = gr.Radio(
            [PROVIDER_LOCAL, PROVIDER_ANTHROPIC],
            value=last_provider,
            label="Provider",
        )

        with gr.Row(equal_height=False):

            # ── left: LM Studio status (hidden for Anthropic) ─────────────────
            with gr.Column(scale=1, min_width=260, visible=(last_provider == PROVIDER_LOCAL)) as lms_status_col:
                gr.Markdown("### LM Studio Status")
                status_badge  = gr.HTML()
                hardware_card = gr.HTML()
                gpu_tip       = gr.HTML()
                model_count   = gr.HTML()
                refresh_btn   = gr.Button("↻ Refresh", size="sm", variant="secondary")

            # ── right: configure & launch ─────────────────────────────────────
            with gr.Column(scale=1, min_width=320):
                gr.Markdown("### Configure & Launch")

                # Local: model from LM Studio API
                local_model_dd = gr.Dropdown(
                    label="Model (from LM Studio)",
                    interactive=False,
                    visible=(last_provider == PROVIDER_LOCAL),
                )

                # Anthropic: API key + Claude model
                with gr.Column(visible=(last_provider == PROVIDER_ANTHROPIC)) as anthropic_col:
                    api_key_box = gr.Textbox(
                        label="Anthropic API Key",
                        type="password",
                        placeholder="sk-ant-…",
                        info="Not saved to disk.",
                    )
                    claude_model_dd = gr.Dropdown(
                        label="Claude Model",
                        choices=CLAUDE_MODELS,
                        value=CLAUDE_MODELS[1],  # sonnet as default
                    )

                # Workspace (always visible)
                ws_dd  = gr.Dropdown(label="Workspace", choices=ws_list, value=default_ws)
                new_ws = gr.Textbox(label="New workspace name", placeholder="my-claudia",
                                    visible=False)

                with gr.Accordion("How it works", open=False):
                    gr.Markdown(f"""
**Local (LM Studio)** — three env vars redirect Claude Code to your local server:

| Variable | Value |
|---|---|
| `ANTHROPIC_BASE_URL` | `{lms_base_url}` |
| `ANTHROPIC_API_KEY` | `""` (empty) |
| `ANTHROPIC_AUTH_TOKEN` | `lm-studio` |

**Claude (Anthropic)** — uses your API key normally; no URL override needed:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your key |

Both launch `claude --model <selected-model>` inside your chosen workspace.
""")

                launch_btn  = gr.Button("🚀  Launch Claudia", variant="primary", size="lg")
                result_text = gr.Textbox(label="Status", interactive=False,
                                         lines=4, show_copy_button=False)

        # ── wiring ────────────────────────────────────────────────────────────
        refresh_outputs = [status_badge, hardware_card, gpu_tip, model_count,
                           local_model_dd, ws_dd]

        app.load(refresh_lms, outputs=refresh_outputs)
        refresh_btn.click(refresh_lms, outputs=refresh_outputs)

        provider_radio.change(
            on_provider_change,
            inputs=[provider_radio],
            outputs=[lms_status_col, local_model_dd, anthropic_col],
        )
        ws_dd.change(on_workspace_change, inputs=[ws_dd], outputs=[new_ws])

        launch_btn.click(
            do_launch,
            inputs=[provider_radio, local_model_dd, claude_model_dd,
                    api_key_box, ws_dd, new_ws],
            outputs=[result_text],
        )

    return app


# ── CLI fallback ──────────────────────────────────────────────────────────────

class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    CYAN  = "\033[96m"; GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"

def _enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def _step(m): print(f"\n{C.CYAN}{C.BOLD}{m}{C.RESET}")
def _ok(m):   print(f"  {C.GREEN}✓{C.RESET} {m}")
def _warn(m): print(f"  {C.YELLOW}!{C.RESET} {m}")
def _err(m):  print(f"  {C.RED}✗{C.RESET} {m}")
def _info(m): print(f"  {C.DIM}{m}{C.RESET}")

def _pick(items, prompt="Choice"):
    for i, item in enumerate(items, 1):
        print(f"  [{C.BOLD}{i}{C.RESET}] {item}")
    while True:
        try:
            raw = input(f"\n  {prompt}: ").strip()
            idx = int(raw)
            if 1 <= idx <= len(items):
                return idx - 1
        except (ValueError, KeyboardInterrupt):
            pass
        _warn(f"Enter a number between 1 and {len(items)}")


def cli_main(lms_port: int):
    _enable_ansi()
    lms_base_url = f"http://localhost:{lms_port}"

    print(f"\n{C.BOLD}{C.CYAN}{'─'*54}{C.RESET}")
    print(f"  {C.BOLD}Claudia  ×  Local Models{C.RESET}")
    print(f"{C.CYAN}{'─'*54}{C.RESET}")

    last = load_config()
    if last:
        _info(f"Provider  : {last.get('provider', PROVIDER_LOCAL)}")
        _info(f"Model     : {last.get('model_id', '?')}")
        _info(f"Workspace : {last.get('workspace', '?')}")
        ans = input("\n  Quick relaunch? [Y/n] ").strip().lower()
        if ans in ("", "y"):
            provider = last.get("provider", PROVIDER_LOCAL)
            if provider == PROVIDER_LOCAL:
                env = env_for_local(last["base_url"])
            else:
                key = input("  Anthropic API key: ").strip()
                env = env_for_anthropic(key)
            launch_in_terminal(env, last["model_id"], last["workspace"])
            return
        print()

    _step("Select provider")
    providers = [PROVIDER_LOCAL, PROVIDER_ANTHROPIC]
    provider  = providers[_pick(providers, "Provider")]

    if provider == PROVIDER_LOCAL:
        _step(f"Connecting to LM Studio ({lms_base_url})")
        state = fetch_server_state(lms_base_url)
        if not state["connected"]:
            _err(f"Cannot reach LM Studio at {lms_base_url}")
            _warn("Open LM Studio → Developer tab → Start Server")
            sys.exit(1)
        _ok(f"Server running — {len(state['models'])} model(s) loaded")

        if state["has_gpu"]:
            _step("Hardware")
            _info(f"GPU: {state['gpu_name']}  ({state['vram_gb']} GB VRAM)")
            _warn("Set GPU Layers → Max in LM Studio for best performance.")

        if not state["models"]:
            _err("No models loaded — load a model in LM Studio first.")
            sys.exit(1)

        _step("Select model")
        model_id = state["models"][_pick(state["models"], "Model")]
        env = env_for_local(lms_base_url)
        base_url = lms_base_url

    else:
        api_key  = input("\n  Anthropic API key: ").strip()
        _step("Select Claude model")
        model_id = CLAUDE_MODELS[_pick(CLAUDE_MODELS, "Model")]
        env = env_for_anthropic(api_key)
        base_url = "https://api.anthropic.com"

    _ok(f"Model: {model_id}")

    _step("Workspace")
    choices = workspace_choices()
    idx = _pick(choices, "Choice")

    if choices[idx] == CREATE_NEW:
        name = input("  Workspace name: ").strip() or "my-claudia"
        ws_path = WORKSPACES_ROOT / name
        ws_path.mkdir(parents=True, exist_ok=True)
        install_templates(ws_path)
    else:
        ws_path = WORKSPACES_ROOT / choices[idx]
    _ok(f"Workspace: {ws_path}")

    save_config(provider, base_url, model_id, ws_path)
    _step("Launching Claudia")
    _ok(f"Provider  : {provider}")
    _ok(f"Model     : {model_id}")
    _ok(f"Workspace : {ws_path}")
    launch_in_terminal(env, model_id, str(ws_path))


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    args    = sys.argv[1:]
    use_cli = "--cli" in args
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
        print("Gradio is not installed. Run:  pip install gradio")
        print("Or use CLI mode:               python launch.py --cli")
        sys.exit(1)

    app = build_ui(lms_port)
    app.launch(server_port=ui_port, inbrowser=True, show_api=False)


if __name__ == "__main__":
    main()
