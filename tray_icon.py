"""
tray_icon.py — system tray icon for the AI Companion.

Shows a small icon in the Windows system tray with a right-click menu:
  • Status      — show current level, experience count, study time
  • Open Chat   — open a terminal with main.py
  • Stop        — gracefully stop monitoring agent + Docker container
  • Exit        — exit the tray icon (companion keeps running)

Requires:  pip install pystray pillow
Run with:  pythonw tray_icon.py   (no console window)

The autostart installer can register this instead of (or alongside) the
monitoring_agent directly.
"""

import os
import sys
import subprocess
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


def _create_icon_image(color="#4CAF50"):
    """Draw a simple circular icon in the given colour."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Small white dot in centre to distinguish levels
    dot = size // 4
    cx = size // 2
    draw.ellipse([cx - dot//2, cx - dot//2, cx + dot//2, cx + dot//2],
                 fill="white")
    return img


def _level_color(level: str) -> str:
    return {
        "baby":         "#9E9E9E",   # grey
        "kid":          "#4CAF50",   # green
        "adult":        "#2196F3",   # blue
        "scholar":      "#9C27B0",   # purple
        "professional": "#FF9800",   # gold
    }.get(level, "#4CAF50")


def _get_status() -> dict:
    """Pull live status from the Docker API or fall back to defaults."""
    try:
        import urllib.request, json
        with urllib.request.urlopen("http://localhost:8000/stats", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _get_level() -> str:
    data = _get_status()
    return data.get("level", "baby")


def _open_chat(_icon, _item):
    subprocess.Popen(
        ["cmd", "/k", f'python "{os.path.join(BASE_DIR, "main.py")}"'],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _show_status(_icon, _item):
    data = _get_status()
    if not data:
        msg = "AI Companion\n\nCannot reach backend (is Docker running?)"
    else:
        level = data.get("level", "?").upper()
        exp = data.get("memory", {}).get("total", "?")
        study = data.get("total_study_minutes", 0)
        progress = data.get("level_progress", {})
        next_lvl = progress.get("next_level", "max")
        msg = (
            f"AI Companion\n\n"
            f"Level     : {level}\n"
            f"Experience: {exp}\n"
            f"Study time: {study:.0f} min\n"
            f"Next level: {next_lvl}"
        )

    import ctypes
    ctypes.windll.user32.MessageBoxW(0, msg, "AI Companion Status", 0x40)


def _stop_companion(_icon, _item):
    import ctypes
    answer = ctypes.windll.user32.MessageBoxW(
        0,
        "Stop the AI Companion?\n\nThis will stop the monitoring agent and Docker container.",
        "AI Companion",
        0x04 | 0x30,   # Yes/No + warning icon
    )
    if answer == 6:   # IDYES
        # Kill monitoring_agent (pythonw processes matching our script)
        subprocess.run(
            ["powershell", "-Command",
             "Get-WmiObject Win32_Process | "
             "Where-Object { $_.CommandLine -like '*monitoring_agent*' } | "
             "ForEach-Object { $_.Terminate() }"],
            capture_output=True,
        )
        # Stop Docker container
        subprocess.run(
            ["docker", "compose", "stop"],
            cwd=BASE_DIR, capture_output=True,
        )
        _icon.stop()


def _exit_tray(_icon, _item):
    _icon.stop()


def _update_icon_loop(icon):
    """Poll the backend every 60s and update the tray icon colour by level."""
    while True:
        try:
            level = _get_level()
            color = _level_color(level)
            icon.icon = _create_icon_image(color)
            icon.title = f"AI Companion [{level.upper()}]"
        except Exception:
            pass
        time.sleep(60)


def run_tray():
    if not TRAY_AVAILABLE:
        print(
            "[TrayIcon] pystray or Pillow not installed.\n"
            "  pip install pystray pillow\n"
            "  Falling back to headless mode (monitoring_agent runs without tray)."
        )
        # Fall back: just run the monitoring agent directly
        agent = os.path.join(BASE_DIR, "monitoring_agent.py")
        os.execv(sys.executable, [sys.executable, agent])
        return

    level = _get_level()
    color = _level_color(level)
    icon_img = _create_icon_image(color)

    menu = pystray.Menu(
        pystray.MenuItem("Status",    _show_status),
        pystray.MenuItem("Open Chat", _open_chat),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Stop Companion", _stop_companion),
        pystray.MenuItem("Exit Tray",      _exit_tray),
    )

    icon = pystray.Icon(
        "ai_companion",
        icon=icon_img,
        title=f"AI Companion [{level.upper()}]",
        menu=menu,
    )

    # Start monitoring agent in a background thread
    agent_thread = threading.Thread(
        target=_run_monitoring_agent, daemon=True
    )
    agent_thread.start()

    # Keep icon colour in sync with level
    update_thread = threading.Thread(
        target=_update_icon_loop, args=(icon,), daemon=True
    )
    update_thread.start()

    icon.run()


def _run_monitoring_agent():
    """Run the monitoring agent in-process (blocking)."""
    agent = os.path.join(BASE_DIR, "monitoring_agent.py")
    try:
        import runpy
        runpy.run_path(agent, run_name="__main__")
    except SystemExit:
        pass
    except Exception as e:
        print(f"[TrayIcon] monitoring_agent error: {e}")


if __name__ == "__main__":
    run_tray()
