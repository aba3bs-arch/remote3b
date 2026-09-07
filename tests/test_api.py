import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

PASSWORD = "Tiendas@12345"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("USE_SSL", "false")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)

    import main

    main.reset_app_state(tmp_path / "am_connect.db")
    with TestClient(main.app) as test_client:
        yield test_client


def register_and_login(client, username="admin"):
    register = client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@3b.local", "password": PASSWORD},
    )
    assert register.status_code == 200, register.text
    login = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_dashboard_and_session_pages(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "AM-CONNECT" in home.text
    assert "Agregar equipo" in home.text
    session = client.get("/session")
    assert session.status_code == 200
    assert "Pantalla remota" in session.text


def test_login_json_and_query_params(client):
    headers, _ = register_and_login(client, "tienda")
    listed = client.get("/api/devices", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["devices"] == []

    query_login = client.post(
        "/api/auth/login",
        params={"username": "tienda", "password": PASSWORD},
    )
    assert query_login.status_code == 200


def test_device_register_persists_and_lists(client, tmp_path):
    headers, _ = register_and_login(client)
    created = client.post(
        "/api/devices/register",
        json={"device_name": "3B7 Del Valle", "os": "Windows"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["device_id"].startswith("dev_")
    assert payload["device_token"]

    listed = client.get("/api/devices", headers=headers)
    assert listed.json()["total"] == 1
    assert listed.json()["devices"][0]["device_name"] == "3B7 Del Valle"
    assert listed.json()["devices"][0]["is_online"] is False

    import main

    main.reset_app_state(tmp_path / "am_connect.db")
    listed_again = client.get("/api/devices", headers=headers)
    assert listed_again.status_code == 200
    assert listed_again.json()["total"] == 1
    assert listed_again.json()["devices"][0]["device_name"] == "3B7 Del Valle"


def test_device_belongs_to_owner_only(client):
    owner_headers, _ = register_and_login(client, "owner")
    other_headers, _ = register_and_login(client, "other")
    created = client.post(
        "/api/devices/register",
        json={"device_name": "3B Fusion", "os": "Windows"},
        headers=owner_headers,
    )
    device_id = created.json()["device_id"]

    forbidden = client.get(f"/api/devices/{device_id}/status", headers=other_headers)
    assert forbidden.status_code == 403

    screenshot = client.post(f"/api/devices/{device_id}/screenshot", headers=owner_headers)
    assert screenshot.status_code == 503


def test_offline_screenshot_and_delete(client):
    headers, _ = register_and_login(client)
    created = client.post(
        "/api/devices/register",
        json={"device_name": "EastTexas", "os": "Windows"},
        headers=headers,
    )
    device_id = created.json()["device_id"]
    deleted = client.delete(f"/api/devices/{device_id}", headers=headers)
    assert deleted.status_code == 200
    missing = client.get(f"/api/devices/{device_id}/status", headers=headers)
    assert missing.status_code == 404


def test_install_routes(client):
    script = client.get("/install/windows.ps1")
    assert script.status_code == 200
    assert b"AM-CONNECT" in script.content
    agent = client.get("/install/agent.py")
    assert agent.status_code == 200
    assert b"RemoteAgent" in agent.content
    requirements = client.get("/install/agent-requirements.txt")
    assert requirements.status_code == 200
    public = client.get("/api/public-config")
    assert public.status_code == 200
    assert public.json()["install_script"].endswith("/install/windows.ps1")


def test_operator_receives_screen_capture(client):
    headers, access_token = register_and_login(client)
    created = client.post(
        "/api/devices/register",
        json={"device_name": "3B10 ElMezquite", "os": "Windows"},
        headers=headers,
    )
    device_id = created.json()["device_id"]
    device_token = created.json()["device_token"]

    with client.websocket_connect(f"/ws/{device_id}?token={device_token}") as agent_ws:
        with client.websocket_connect(f"/ws/operator/{device_id}?token={access_token}") as operator_ws:
            ready = operator_ws.receive_json()
            assert ready["type"] == "session_ready"
            start = agent_ws.receive_json()
            assert start["type"] == "start_stream"
            agent_ws.send_json({
                "type": "screen_capture",
                "image": "abc123",
                "width": 800,
                "height": 600,
                "screen_width": 1920,
                "screen_height": 1080,
                "timestamp": "2026-09-07T00:00:00",
            })
            capture = operator_ws.receive_json()
            assert capture["type"] == "screen_capture"
            assert capture["image"] == "abc123"
            assert capture["screen_width"] == 1920

            operator_ws.send_json({
                "type": "input",
                "kind": "mouse",
                "action": "click",
                "x": 10,
                "y": 20,
            })
            inbound = agent_ws.receive_json()
            assert inbound["type"] == "input"
            assert inbound["x"] == 10
