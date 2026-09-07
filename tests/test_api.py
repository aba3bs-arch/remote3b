import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-am-connect")
os.environ.setdefault("USE_SSL", "false")
os.environ["AM_CONNECT_DATA_DIR"] = str(ROOT / "data" / "test-store")

sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient
import main


client = TestClient(main.app)


def _auth_headers():
    username = "tiendaadmin"
    password = "Secure@12345"
    client.post(
        "/api/auth/register",
        params={"username": username, "email": "admin@3b.test", "password": password},
    )
    login = client.post(
        "/api/auth/login",
        params={"username": username, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_dashboard_and_session_pages():
    home = client.get("/")
    assert home.status_code == 200
    assert "AM-CONNECT" in home.text
    assert "Always-ON" in home.text
    assert "Connect" in home.text
    assert "Computadoras" in home.text

    downloads = client.get("/api/downloads")
    assert downloads.status_code == 200
    assert "agent_exe" in downloads.json()

    session = client.get("/session")
    assert session.status_code == 200
    assert "Sesion remota" in session.text


def test_register_store_computer_and_installer():
    headers = _auth_headers()
    created = client.post(
        "/api/devices/register",
        params={"device_name": "3B7 Del Valle", "os": "Windows"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    device_id = created.json()["device_id"]
    assert created.json()["install_code"]

    listing = client.get("/api/devices", headers=headers)
    assert listing.status_code == 200
    names = [item["device_name"] for item in listing.json()["devices"]]
    assert "3B7 Del Valle" in names

    installer = client.get(f"/api/devices/{device_id}/installer", headers=headers)
    assert installer.status_code == 200, installer.text
    payload = installer.json()
    assert "Invoke-WebRequest" in payload["command"]
    assert payload["script_url"].endswith(payload["install_code"]) or "code=" in payload["script_url"]

    script = client.get(f"/install/windows.ps1?code={payload['install_code']}")
    assert script.status_code == 200
    assert "AM-CONNECT Always-ON" in script.text
    assert device_id in script.text
    assert "AM-CONNECT-Agent.exe" in script.text

    agent = client.get("/install/agent.py")
    assert agent.status_code == 200
    assert b"RemoteAgent" in agent.content


def test_offline_screenshot_returns_503():
    headers = _auth_headers()
    created = client.post(
        "/api/devices/register",
        params={"device_name": "3B6 Soli", "os": "Windows"},
        headers=headers,
    )
    device_id = created.json()["device_id"]
    response = client.post(f"/api/devices/{device_id}/screenshot", headers=headers)
    assert response.status_code == 503
