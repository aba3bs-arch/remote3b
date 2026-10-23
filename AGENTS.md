# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Remote3B is a Python FastAPI-based Remote Access Tool with a server + client agent architecture. The frontend (React) referenced in README is not present in the repository.

### Running the Server

```bash
source venv/bin/activate
python server/main.py
```

Server runs on `https://localhost:8000` with TLS by default. The `server/main.py` must be run from the `/workspace` directory because it imports sibling modules (`connection_manager`, `security`) using relative names, and the working directory must be `server/` or the `PYTHONPATH` must include `server/`. The recommended approach is:

```bash
cd /workspace/server && python main.py
```

Or from workspace root:
```bash
cd /workspace && python server/main.py
```

Both work because uvicorn is configured with `"main:app"` which resolves relative to cwd.

### Key Gotchas

1. **requirements.txt has broken packages**: `sqlite3-python==1.0.0`, `screenshot==2.3`, and `asyncio-contextmanager==1.0.0` do not exist on PyPI. The actual working dependencies are installed without these packages. Use `opencv-python-headless` instead of `opencv-python` to avoid GUI library requirements in headless environments.

2. **PyJWT version**: The pinned `PyJWT==2.8.1` is no longer available. Use `PyJWT>=2.8.0` instead.

3. **TLS certificates**: Must be generated before starting the server: `python generate_certs.py`. Certs are saved to `certs/cert.pem` and `certs/key.pem`. If not present, server falls back to non-SSL mode.

4. **In-memory state**: The server uses in-memory user/device stores (no persistent database despite SQLAlchemy being in deps). All data is lost on restart.

5. **API testing**: Use `-k` flag with curl to skip TLS verification for self-signed certs: `curl -sk https://localhost:8000/health`

### Linting and Testing

- **Lint**: `flake8 server/ client/ generate_certs.py --max-line-length=120`
- **Format check**: `black --check server/ client/ generate_certs.py`
- **Tests**: `pytest` (no test files exist yet; pytest is configured and ready)

### API Endpoints (Quick Reference)

See README.md for full API documentation. Key endpoints:
- `GET /health` — health check
- `POST /api/auth/register?username=X&email=Y&password=Z` — register user
- `POST /api/auth/login?username=X&password=Y` — login (returns JWT tokens)
- `GET /api/devices` — list devices (requires Authorization header)
- `WS /ws/{device_id}` — WebSocket for device communication
