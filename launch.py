#!/usr/bin/env python3
"""
launch.py - Interactive Claudia launcher for local models

Usage:
    python launch.py          # interactive setup
    python launch.py --port 1234  # custom LM Studio port
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

# ── Paths ──────────────────────────────────────────────────────────────────
FORK_DIR        = Path(__file__).parent
WORKSPACES_ROOT = Path.home() / "claudia-workspaces"
CONFIG_FILE     = Path.home() / ".claudia" / "launch-config.json"

# ── Terminal colours ────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"

def _enable_ansi_windows():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def step(msg):  print(f"\n{C.CYAN}{C.BOLD}{msg}{C.RESET}")
def ok(msg):    print(f"  {C.GREEN}✓{C.RESET} {msg}")
def warn(msg):  print(f"  {C.YELLOW}!{C.RESET} {msg}")
def err(msg):   print(f"  {C.RED}✗{C.RESET} {msg}")
def info(msg):  print(f"  {C.DIM}{msg}{C.RESET}")
def header(msg):print(f"\n{C.BOLD}{C.CYAN}{'─'*54}{C.RESET}\n  {C.BOLD}{msg}{C.RESET}\n{C.CYAN}{'─'*54}{C.RESET}")

# ── LM Studio API ───────────────────────────────────────────────────────────

def _get(base_url: str, path: str, timeout: int = 5) -> dict | None:
    try:
        with urlopen(f"{base_url}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def check_server(port: int) -> tuple[str, list[dict]]:
    base_url = f"http://localhost:{port}"
    step(f"Connecting to LM Studio  ({base_url})")

    data = _get(base_url, "/v1/models")
    if data is None:
        err(f"Cannot reach LM Studio at {base_url}")
        warn("Open LM Studio → Developer tab → Start Server")
        sys.exit(1)

    models = data.get("data", [])
    ok(f"Server running — {len(models)} model(s) loaded")
    return base_url, models


def show_hardware(base_url: str):
    """Show GPU / memory info reported by LM Studio."""
    # LM Studio v0 stats endpoint (may not exist on all versions)
    stats = _get(base_url, "/api/v0/system", timeout=3)
    if stats:
        gpu = stats.get("gpu", {})
        ram = stats.get("ram", {})
        if gpu or ram:
            step("Hardware")
            if gpu:
                info(f"GPU  : {gpu.get('name', 'unknown')}  "
                     f"VRAM {gpu.get('totalVramBytes', 0) // 1024**3} GB")
            if ram:
                info(f"RAM  : {ram.get('totalBytes', 0) // 1024**3} GB total  "
                     f"{ram.get('availableBytes', 0) // 1024**3} GB free")
            return

    # Fallback: pull from /v1/models extended info if available
    hw = _get(base_url, "/api/v0/hardware", timeout=3)
    if hw:
        mem = hw.get("memoryInfo", {})
        gpus = hw.get("gpuSurveyResult", {}).get("gpuInfo", [])
        if gpus:
            step("Hardware")
            for g in gpus:
                vram_gb = g.get("dedicatedMemoryCapacityBytes", 0) // 1024**3
                info(f"GPU  : {g.get('name', '?')}  VRAM {vram_gb} GB  "
                     f"({g.get('detectionPlatform', '?')})")
            ram_gb = mem.get("ramCapacity", 0) // 1024**3
            info(f"RAM  : {ram_gb} GB")

# ── Menus ───────────────────────────────────────────────────────────────────

def pick(items: list[str], prompt: str = "Choice") -> int:
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
        warn(f"Enter a number between 1 and {len(items)}")


def select_model(models: list[dict]) -> str:
    if not models:
        err("No models loaded in LM Studio — load a model first.")
        sys.exit(1)

    step("Select model")
    idx = pick([m["id"] for m in models], "Model")
    model_id = models[idx]["id"]
    ok(f"Model: {model_id}")
    return model_id

# ── Workspace management ────────────────────────────────────────────────────

def _status(path: Path) -> str:
    if (path / "context" / "me.md").exists():
        return f"{C.GREEN}ready{C.RESET}"
    if (path / "CLAUDE.md").exists():
        return f"{C.YELLOW}installed, not onboarded{C.RESET}"
    return f"{C.DIM}empty{C.RESET}"


def _list_workspaces() -> list[Path]:
    if not WORKSPACES_ROOT.exists():
        return []
    return sorted(d for d in WORKSPACES_ROOT.iterdir() if d.is_dir())


def _install_templates(workspace: Path):
    installer = FORK_DIR / "bin" / "index.js"
    if not installer.exists():
        warn("Claudia installer (bin/index.js) not found.")
        warn(f"Run this script from inside the claudia fork directory.")
        return
    info("Installing Claudia templates...")
    result = subprocess.run(["node", str(installer), str(workspace)])
    if result.returncode == 0:
        ok("Templates installed")
    else:
        warn("Installer exited with errors — check output above.")


def select_workspace() -> Path:
    step("Workspace")

    existing = _list_workspaces()
    labels   = [f"{C.BOLD}+ Create new workspace{C.RESET}"]
    labels  += [f"{w.name}   ({_status(w)})" for w in existing]
    labels  += [f"{C.DIM}Enter custom path…{C.RESET}"]

    idx = pick(labels, "Choice")

    if idx == 0:                          # new
        name = input("  Workspace name: ").strip()
        if not name:
            name = "my-claudia"
        path = WORKSPACES_ROOT / name
        path.mkdir(parents=True, exist_ok=True)
        ok(f"Created: {path}")
        _install_templates(path)
        return path

    if idx == len(labels) - 1:           # custom path
        raw  = input("  Path: ").strip()
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            if input(f"  {path} does not exist. Create it? [Y/n] ").lower() in ("", "y"):
                path.mkdir(parents=True)
                _install_templates(path)
        return path

    path   = existing[idx - 1]           # existing workspace
    status = workspace_status_raw(path)
    ok(f"Workspace: {path}")
    if status == "empty":
        _install_templates(path)
    return path


def workspace_status_raw(path: Path) -> str:
    if (path / "context" / "me.md").exists():
        return "ready"
    if (path / "CLAUDE.md").exists():
        return "installed"
    return "empty"

# ── Config persistence ──────────────────────────────────────────────────────

def save_config(base_url: str, model_id: str, workspace: Path):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({
        "base_url":  base_url,
        "model_id":  model_id,
        "workspace": str(workspace),
    }, indent=2))


def load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return None

# ── Launch ──────────────────────────────────────────────────────────────────

def launch(base_url: str, model_id: str, workspace: Path):
    step("Launching Claudia")
    ok(f"Model     : {model_id}")
    ok(f"Workspace : {workspace}")
    ok(f"Server    : {base_url}")

    save_config(base_url, model_id, workspace)

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"]   = base_url
    env["ANTHROPIC_API_KEY"]    = ""
    env["ANTHROPIC_AUTH_TOKEN"] = "lm-studio"

    print()
    subprocess.run(["claude", "--model", model_id], cwd=str(workspace), env=env)

# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    _enable_ansi_windows()

    port = 1234
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass

    header("Claudia  ×  Local Models")

    # Quick relaunch from last session
    last = load_config()
    if last:
        info(f"Last session: {last['model_id']}")
        info(f"Workspace   : {last['workspace']}")
        ans = input("\n  Quick relaunch? [Y/n] ").strip().lower()
        if ans in ("", "y"):
            launch(last["base_url"], last["model_id"], Path(last["workspace"]))
            return
        print()

    base_url, models = check_server(port)
    show_hardware(base_url)
    model_id  = select_model(models)
    workspace = select_workspace()
    launch(base_url, model_id, workspace)


if __name__ == "__main__":
    main()
