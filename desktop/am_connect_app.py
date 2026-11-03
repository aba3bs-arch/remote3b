#!/usr/bin/env python3
"""Double-click launcher for the AM-CONNECT web panel."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def configure_environment() -> tuple[str, int, str]:
    port = int(os.getenv("PORT", "8000"))
    probe = "127.0.0.1"
    if not _port_free(probe, port):
        port = _find_free_port(probe, port)
    panel_url = f"http://127.0.0.1:{port}"
    os.environ["USE_SSL"] = "false"
    os.environ["HOST"] = "0.0.0.0"
    os.environ["PORT"] = str(port)
    public = os.environ.get("PUBLIC_URL", "")
    if not public or _loopback(public):
        os.environ.pop("PUBLIC_URL", None)
    os.environ.setdefault(
        "ALLOWED_ORIGINS",
        f"{panel_url},http://localhost:{port}",
    )
    os.environ.setdefault("DEBUG", "false")
    return probe, port, panel_url


def _loopback(url: str) -> bool:
    lowered = url.lower()
    return "://127.0.0.1" in lowered or "://localhost" in lowered or "://0.0.0.0" in lowered


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) != 0


def _find_free_port(host: str, start: int) -> int:
    for port in range(start, start + 20):
        if _port_free(host, port):
            return port
    raise RuntimeError("No hay un puerto libre para AM-CONNECT")


def wait_for_server(host: str, port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_free(host, port):
            return True
        time.sleep(0.2)
    return False


def start_server(root: Path) -> None:
    sys.path.insert(0, str(root / "server"))
    os.chdir(root)
    import uvicorn
    import main as server_main

    uvicorn.run(
        server_main.app,
        host=os.environ["HOST"],
        port=int(os.environ["PORT"]),
        log_level="info",
    )


def show_window(public_url: str, store_url: str) -> None:
    import tkinter as tk

    window = tk.Tk()
    window.title("AM-CONNECT")
    window.geometry("520x250")
    window.resizable(False, False)
    tk.Label(window, text="AM-CONNECT esta abierto", font=("Segoe UI", 16, "bold")).pack(pady=(18, 8))
    tk.Label(
        window,
        text=(
            f"Panel: {public_url}\n"
            f"Las tiendas en esta red usan: {store_url}\n"
            "Deja esta ventana abierta. Si Windows pregunta, permite la app en redes privadas."
        ),
        justify="center",
        wraplength=480,
    ).pack(pady=6)
    tk.Button(
        window,
        text="Abrir panel",
        command=lambda: webbrowser.open(public_url),
        width=18,
        height=2,
    ).pack(pady=12)
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.mainloop()


def _store_url(root: Path, port: int) -> str:
    sys.path.insert(0, str(root / "server"))
    from paths import detect_lan_ip

    lan_ip = detect_lan_ip()
    if lan_ip:
        return f"http://{lan_ip}:{port}"
    return f"http://127.0.0.1:{port}"


def main() -> None:
    root = runtime_root()
    host, port, public_url = configure_environment()
    thread = threading.Thread(target=start_server, args=(root,), daemon=True)
    thread.start()
    if wait_for_server(host, port):
        webbrowser.open(public_url)
        show_window(public_url, _store_url(root, port))
        return

    import tkinter as tk
    from tkinter import messagebox

    fail = tk.Tk()
    fail.withdraw()
    messagebox.showerror(
        "AM-CONNECT",
        "No se pudo abrir el panel. El puerto esta ocupado o el servidor no arranco.",
    )


if __name__ == "__main__":
    main()
