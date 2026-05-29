"""Combine per-sleeve target weights into one portfolio-level target.

Each sleeve returns weights that sum to <= 1.0 *within the sleeve*. We scale
those by the sleeve's normalised share of total capital and sum across sleeves,
so the same instrument appearing in two sleeves accumulates its target.
"""
from __future__ import annotations

from dataclasses import dataclass

from .logging_config import get_logger
from .models import Instrument

log = get_logger("portfolio")


@dataclass
class CombinedTarget:
    instrument: Instrument
    weight: float            # fraction of total equity
    reasons: list[str]


def combine_targets(
    sleeve_weights: dict[str, float],
    sleeve_outputs: dict[str, list],  # {sleeve: [TargetWeight,...]}
) -> dict[str, CombinedTarget]:
    combined: dict[str, CombinedTarget] = {}
    for sleeve, weight in sleeve_weights.items():
        for tw in sleeve_outputs.get(sleeve, []):
            contribution = weight * tw.weight
            if contribution <= 0:
                continue
            key = tw.instrument.key
            if key in combined:
                combined[key].weight += contribution
                combined[key].reasons.append(f"{sleeve}: {tw.reason}")
            else:
                combined[key] = CombinedTarget(
                    instrument=tw.instrument,
                    weight=contribution,
                    reasons=[f"{sleeve}: {tw.reason}"],
                )

    total = sum(t.weight for t in combined.values())
    log.info("Combined target invests %.1f%% of equity across %d instruments",
             total * 100, len(combined))
    return combined
