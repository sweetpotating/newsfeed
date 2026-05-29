"""End-to-end smoke test: the full engine running offline on synthetic data
through the paper broker. Proves the wiring works without any network/account.
"""
import os
import pathlib

import pytest

from sgtrader.config import load_config
from sgtrader.engine import Engine


def _repo_root() -> pathlib.Path:
    """The sg-trading-bot dir (where config.yaml lives)."""
    here = pathlib.Path(__file__).resolve().parent.parent
    assert (here / "config.yaml").exists(), f"config.yaml not found at {here}"
    return here


@pytest.fixture
def offline_config(tmp_path, monkeypatch):
    # Force offline, deterministic data; run from the project root so config.yaml
    # and the state/ dir resolve correctly.
    monkeypatch.setenv("SGTRADER_MODE", "paper")
    monkeypatch.setenv("SGTRADER_DATA_PROVIDER", "synthetic")
    monkeypatch.chdir(_repo_root())
    return load_config(config_path="config.yaml", env_path=str(tmp_path / "missing.env"))


def test_full_rebalance_runs_and_produces_report(offline_config, tmp_path):
    engine = Engine(offline_config)
    engine._ensure_wiring()
    engine.broker._state_path = tmp_path / "paper.json"
    try:
        report = engine.run(dry_run=True)
    finally:
        engine.close()

    assert report["mode"] == "paper"
    assert report["dry_run"] is True
    assert report["equity"] > 0
    assert len(report["targets"]) > 0
    # On a fresh paper account it should want to deploy cash into the targets.
    assert len(report["orders"]) > 0
    for o in report["orders"]:
        assert o["ref_price"] > 0
        assert o["reason"]


def test_converges_to_no_churn(offline_config, tmp_path):
    """With prices held fixed, repeated runs should deploy capital (spread over
    several runs by the turnover cap) and then stop trading once on target."""
    engine = Engine(offline_config)
    engine._ensure_wiring()
    engine.broker._state_path = tmp_path / "paper.json"

    first = engine.run(dry_run=False)
    assert len(first["orders"]) > 0  # starts deploying cash

    last_n = len(first["orders"])
    converged = False
    for _ in range(12):  # plenty of runs to fully deploy under the turnover cap
        r = engine.run(dry_run=False)
        last_n = len(r["orders"])
        if last_n == 0:
            converged = True
            break
    engine.close()
    assert converged, "engine never reached a stable (no-trade) state"
