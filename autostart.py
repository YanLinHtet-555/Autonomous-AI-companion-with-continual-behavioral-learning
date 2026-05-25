"""
autostart.py -- install or remove the AI Companion from Windows startup.

Uses the Windows Startup folder (no admin required).
After running install, everything starts automatically on every login:
  1. Docker Compose starts the AI brain container  (silently, ~30s after login)
  2. monitoring_agent / tray_icon runs silently     (immediately, retries Docker)

Usage:
    python autostart.py install      Add to Windows startup
    python autostart.py uninstall    Remove from Windows startup
    python autostart.py status       Check if installed and what is running
"""

import os
import sys
import subprocess

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable
PYTHONW_EXE = os.path.join(os.path.dirname(PYTHON_EXE), "pythonw.exe")
if not os.path.exists(PYTHONW_EXE):
    PYTHONW_EXE = PYTHON_EXE

# Windows Startup folder -- everything here runs at login, no admin needed
STARTUP_DIR = os.path.expandvars(
    r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
)
VBS_MONITOR = os.path.join(STARTUP_DIR, "AICompanion-Monitor.vbs")
VBS_DOCKER  = os.path.join(STARTUP_DIR, "AICompanion-Docker.vbs")


# ── VBScript builders ─────────────────────────────────────────────────────────

def _build_vbs_monitor() -> str:
    """VBS that launches tray_icon.py (or monitoring_agent.py) with no window."""
    tray  = os.path.join(BASE_DIR, "tray_icon.py")
    agent = os.path.join(BASE_DIR, "monitoring_agent.py")
    script = tray if os.path.exists(tray) else agent
    # VBScript: use "" inside a string for a literal double-quote
    # sh.Run """exe"" ""script""", 0, False  =>  "exe" "script"
    q = '"'
    run_arg = (
        q + q + q + PYTHONW_EXE + q + q
        + " " +
        q + q + script + q + q + q
    )
    lines = [
        "' AI Companion -- tray icon + monitoring agent (no console window)",
        'Set sh = CreateObject("WScript.Shell")',
        "sh.Run " + run_arg + ", 0, False",
    ]
    return "\n".join(lines) + "\n"


def _build_vbs_docker() -> str:
    """VBS that runs docker compose up -d with no window."""
    docker = _find_docker_exe()
    # In VBScript, "" inside a string = literal double-quote.
    # We need: cmd /c cd /d "BASE_DIR" && "docker.exe" compose up -d
    # Which in VBScript string escaping becomes:
    #   "cmd /c cd /d ""BASE_DIR"" && ""docker.exe"" compose up -d"
    cmd = (
        'cmd /c cd /d ""' + BASE_DIR + '"" && ""' + docker + '"" compose up -d'
    )
    lines = [
        "' AI Companion -- start Docker container (no console window)",
        'Set sh = CreateObject("WScript.Shell")',
        'sh.Run "' + cmd + '", 0, False',
    ]
    return "\n".join(lines) + "\n"


DOCKER_BIN = r"C:\Program Files\Docker\Docker\resources\bin"

def _find_docker_exe() -> str:
    """Return full path to docker.exe, falling back to bare 'docker' if on PATH."""
    full = os.path.join(DOCKER_BIN, "docker.exe")
    if os.path.exists(full):
        return full
    return "docker"

def _find_docker_compose() -> str:
    """Return the docker compose command, using full path when available."""
    docker = _find_docker_exe()
    # Try 'docker compose' (v2 plugin, modern Docker Desktop)
    try:
        r = subprocess.run(
            [docker, "compose", "version"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return f'"{docker}" compose' if " " in docker else "docker compose"
    except Exception:
        pass
    return f'"{docker}" compose'


# ── Commands ──────────────────────────────────────────────────────────────────

def install():
    os.makedirs(STARTUP_DIR, exist_ok=True)

    with open(VBS_DOCKER,  "w") as f:
        f.write(_build_vbs_docker())
    with open(VBS_MONITOR, "w") as f:
        f.write(_build_vbs_monitor())

    print("[autostart] Installed to Startup folder:")
    print(f"  {VBS_DOCKER}")
    print(f"  {VBS_MONITOR}")
    print()
    print("[autostart] On every login (no admin, no extra tools needed):")
    print("  - Docker container starts automatically")
    print("  - Monitoring agent runs silently in the background")
    print()
    print("[autostart] To start RIGHT NOW without rebooting:")
    print('  docker-compose up -d')
    if os.path.exists(os.path.join(BASE_DIR, "tray_icon.py")):
        print(f'  pythonw "{os.path.join(BASE_DIR, "tray_icon.py")}"')
    else:
        print(f'  pythonw "{os.path.join(BASE_DIR, "monitoring_agent.py")}"')


def uninstall():
    removed = False
    for path in (VBS_DOCKER, VBS_MONITOR):
        if os.path.exists(path):
            os.remove(path)
            print(f"[autostart] Removed: {path}")
            removed = True
    if not removed:
        print("[autostart] Nothing to remove (not installed).")
    else:
        print("[autostart] AI Companion removed from startup.")


def status():
    print()
    print("[autostart] Startup folder entries:")
    for label, path in (("Docker launcher", VBS_DOCKER),
                        ("Monitor launcher", VBS_MONITOR)):
        state = "INSTALLED" if os.path.exists(path) else "not installed"
        print(f"  {label:<20} {state}")

    print()
    # Docker container
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=ai-companion", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=5,
        )
        container = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "NOT RUNNING"
    except Exception:
        container = "Docker not reachable (is Docker Desktop running?)"
    print(f"  Docker container:    {container}")

    # pythonw process check
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "@(Get-WmiObject Win32_Process | "
             "Where-Object { $_.CommandLine -like '*monitoring_agent*' "
             "-or $_.CommandLine -like '*tray_icon*' }).Count"],
            capture_output=True, text=True, timeout=10,
        )
        count = r.stdout.strip() if r.returncode == 0 else "?"
    except Exception:
        count = "?"
    print(f"  Agent processes:     {count or '0'} running")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "uninstall", "status"):
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "status":
        status()


if __name__ == "__main__":
    main()
