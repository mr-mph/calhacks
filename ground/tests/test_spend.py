import json

from agents.llm import Claude, SpendLedger, cost_usd, estimate_input_tokens


def test_cost_uses_model_prices():
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == 0.60
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 0) == 2.00
    assert cost_usd("some-future-model", 1_000_000, 0) == 10.00


def test_image_blocks_count_toward_the_estimate():
    text = [{"type": "text", "text": "x" * 350}]
    image = [{"type": "image", "_size": (1024, 576)}]
    assert estimate_input_tokens(text, "") == 101
    assert estimate_input_tokens(image, "") > 700


def test_ledger_accumulates_per_session_and_enforces_cap(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", "s1", cap_usd=0.05)
    ledger.record("pricing", "claude-haiku-5-5", 0.03)
    ledger.record("alerts", "claude-sonnet-5-5", 0.01)
    assert round(ledger.spent(), 6) == 0.04
    assert ledger.allows(0.01) and not ledger.allows(0.02)
    other = SpendLedger(tmp_path / "spend.json", "s2", cap_usd=0.05)
    assert other.spent() == 0.0
    data = json.loads((tmp_path / "spend.json").read_text())
    assert data["sessions"]["s1"]["calls"] == 2
    assert data["sessions"]["s1"]["by_purpose"] == {"pricing": 0.03, "alerts": 0.01}


def test_capped_ledger_refuses_before_calling(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", "s", cap_usd=0.0)
    claude = Claude(ledger, api_key="not-used")
    reply = claude.ask(purpose="pricing", model="claude-haiku-5-5", system="x",
                       content=[{"type": "text", "text": "hello"}])
    assert reply.skipped.startswith("spend cap")
    assert json.loads((tmp_path / "spend.json").read_text())["sessions"]["s"]["refused"] == 1


def test_no_key_means_engine_only(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BALLOON_ENV_FILE", str(tmp_path / "missing"))
    claude = Claude(SpendLedger(tmp_path / "spend.json", "s", 10.0))
    assert not claude.available and claude.mode.startswith("engine only")
