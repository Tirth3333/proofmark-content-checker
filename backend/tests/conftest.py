import json
from pathlib import Path

import pytest

from app.config import settings

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def demo_text() -> str:
    return (FIX / "demo_article.md").read_text()


@pytest.fixture
def demo_brief() -> dict:
    b = json.loads((FIX / "demo_brief.json").read_text())
    b.pop("_note", None)
    return b


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    """Every test starts with AI and search disabled unless it opts in."""
    monkeypatch.setattr(settings, "llm_provider", "none")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "search_provider", "none")
    monkeypatch.setattr(settings, "search_api_key", "")
    yield


CLEAN_TEXT = """Our garden club meets on the first Saturday of each month.

Members bring seedlings to swap and share notes on what grew well. New members can come along to any meeting and ask questions.

We keep the meetings short and friendly, with tea afterwards."""
