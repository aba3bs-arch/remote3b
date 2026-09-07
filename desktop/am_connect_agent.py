#!/usr/bin/env python3
"""Windows agent entrypoint for the packaged AM-CONNECT-Agent.exe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def load_settings() -> None:
    load_dotenv(exe_dir() / ".env")
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AM-CONNECT" / "agent" / ".env"
    load_dotenv(local)
    load_dotenv()

    args = sys.argv[1:]
    for index, item in enumerate(args):
        if item in {"--server", "-s"} and index + 1 < len(args):
            os.environ["SERVER_URL"] = args[index + 1]
        elif item in {"--device", "-d"} and index + 1 < len(args):
            os.environ["DEVICE_ID"] = args[index + 1]
        elif item in {"--token", "-t"} and index + 1 < len(args):
            os.environ["DEVICE_TOKEN"] = args[index + 1]
        elif item in {"--name", "-n"} and index + 1 < len(args):
            os.environ["DEVICE_NAME"] = args[index + 1]


def main() -> None:
    root = runtime_root()
    sys.path.insert(0, str(root / "client"))
    os.chdir(exe_dir())
    load_settings()

    if not os.getenv("DEVICE_TOKEN"):
        print("Falta DEVICE_TOKEN. Usa el instalador de AM-CONNECT o un archivo .env junto al ejecutable.")
        sys.exit(1)

    import asyncio
    import agent as agent_module

    asyncio.run(agent_module.main())


if __name__ == "__main__":
    main()
