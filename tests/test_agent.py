import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client"))

from agent import RemoteAgent  # noqa: E402


def test_mock_screen_contains_store_name():
    agent = RemoteAgent("ws://localhost/ws", "dev_1", "3B7 Del Valle", "tok")
    agent.mock_screen = True
    image, width, height = agent._grab_screen()
    assert (width, height) == (1280, 720)
    assert image.size == (1280, 720)
