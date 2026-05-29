"""Configuration loading and the live-trading safety gate.

Two sources are merged:
  * config.yaml  — strategy/universe/risk parameters (no secrets, committed)
  * .env / env   — mode, credentials, provider selection (secrets, NOT committed)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Instrument, Mode

# The exact phrase a user must put in SGTRADER_LIVE_CONFIRM to arm live trading.
LIVE_CONFIRM_PHRASE = "I UNDERSTAND THIS TRADES REAL MONEY"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids a hard dependency on python-dotenv)."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path)
        return
    except Exception:
        pass
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


@dataclass
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 11
    account: str = ""


@dataclass
class Config:
    mode: Mode
    base_currency: str
    sleeves: dict[str, dict[str, Any]]
    universes: dict[str, list[Instrument]]
    strategy_params: dict[str, dict[str, Any]]
    risk: dict[str, Any]
    schedule: dict[str, Any]
    data_provider: str
    ibkr: IBKRConfig
    live_confirmed: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def enabled_sleeves(self) -> dict[str, float]:
        """Return {sleeve_name: normalised_weight} for enabled sleeves only."""
        active = {
            name: float(cfg.get("weight", 0.0))
            for name, cfg in self.sleeves.items()
            if cfg.get("enabled", False) and float(cfg.get("weight", 0.0)) > 0
        }
        total = sum(active.values())
        if total <= 0:
            return {}
        return {name: w / total for name, w in active.items()}


def load_config(
    config_path: str | Path = "config.yaml",
    env_path: str | Path = ".env",
) -> Config:
    """Load and validate configuration, enforcing the live-trading gate."""
    _load_dotenv(Path(env_path))

    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path.resolve()}")
    raw = yaml.safe_load(cfg_path.read_text()) or {}

    mode = Mode(os.getenv("SGTRADER_MODE", "paper").lower())

    # ── The live-trading gate ────────────────────────────────────────────────
    # Live orders require BOTH mode=live AND the exact confirmation phrase.
    live_confirmed = (
        mode is Mode.LIVE
        and os.getenv("SGTRADER_LIVE_CONFIRM", "").strip() == LIVE_CONFIRM_PHRASE
    )
    if mode is Mode.LIVE and not live_confirmed:
        raise RuntimeError(
            "LIVE mode requested but not confirmed. To trade real money you must set\n"
            f'  SGTRADER_LIVE_CONFIRM="{LIVE_CONFIRM_PHRASE}"\n'
            "in your .env. This guard exists so live trading is never enabled by accident."
        )

    universes = {
        name: [Instrument.from_dict(d) for d in items]
        for name, items in (raw.get("universes") or {}).items()
    }

    ibkr = IBKRConfig(
        host=os.getenv("IBKR_HOST", "127.0.0.1"),
        port=int(os.getenv("IBKR_PORT", "7497")),
        client_id=int(os.getenv("IBKR_CLIENT_ID", "11")),
        account=os.getenv("IBKR_ACCOUNT", ""),
    )

    return Config(
        mode=mode,
        base_currency=raw.get("base_currency", "USD"),
        sleeves=raw.get("sleeves", {}),
        universes=universes,
        strategy_params=raw.get("strategy_params", {}),
        risk=raw.get("risk", {}),
        schedule=raw.get("schedule", {}),
        data_provider=os.getenv("SGTRADER_DATA_PROVIDER", "synthetic").lower(),
        ibkr=ibkr,
        live_confirmed=live_confirmed,
        raw=raw,
    )
