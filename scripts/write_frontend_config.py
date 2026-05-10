#!/usr/bin/env python3
"""
Generate frontend runtime configuration for static hosting.

Netlify serves the frontend as plain static files, so environment variables are
written into a small config file at build time. For local FastAPI hosting, the
committed default keeps apiBaseUrl empty and uses same-origin /api routes.
"""

import json
import os
from pathlib import Path


def main() -> None:
    api_base_url = os.getenv("AM_CONNECT_API_BASE_URL", "").rstrip("/")
    output_path = Path("frontend/assets/config.js")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.AM_CONNECT_CONFIG = "
        + json.dumps({"apiBaseUrl": api_base_url}, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} with apiBaseUrl={api_base_url!r}")


if __name__ == "__main__":
    main()
