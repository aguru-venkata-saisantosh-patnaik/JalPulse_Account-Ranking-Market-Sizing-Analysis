"""
score.py -- the JalPulse scoring engine.

Reads the structured raw hotel registry (data/raw/goa_hotels_raw.csv,
produced by extract.py) and computes, per property:

  commercial_value   -- log-scaled room count, normalised 0-1        [P]
  regulatory_urgency -- GSPCB Consent-to-Operate size-band category  [P, D]
  service_tier_score -- taluka cluster density (cost-to-serve proxy) [P, D]
  value_score        -- weighted sum of the three signals above      [D]
  tier                -- Priority / Watch / Long-tail, by percentile  [A]
  decision_fit        -- proxy for "matches EPBL's owner/GM persona"  [A]
  phase1_score        -- value_score x decision_fit                  [D]

All weights and thresholds live in config.py -- nothing here should be a
magic number. See config.py's module docstring for the [P]/[CD]/[D]/[A]
evidence-tag convention.

Usage:
    python -m src.score
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

log = logging.getLogger(__name__)


def _regulatory_urgency(rooms: int) -> int:
    if rooms > config.GSPCB_LARGE_CATEGORY_ROOMS:
        return config.REGULATORY_URGENCY_SCORE["large"]
    if rooms >= config.GSPCB_MICRO_SMALL_MIN_ROOMS:
        return config.REGULATORY_URGENCY_SCORE["micro_small"]
    return config.REGULATORY_URGENCY_SCORE["below_threshold"]


def _service_tier(taluka: str) -> int:
    if taluka in config.SERVICE_TIER_1_TALUKAS:
        return 1
    if taluka in config.SERVICE_TIER_2_TALUKAS:
        return 2
    return 3


def _decision_fit(rooms: int) -> float:
    """Proxy for 'does this property match EPBL's owner/GM-approved persona'.

    Room-count band as a proxy for likely-independent ownership -- see
    config.py's comment on FIT_* constants for why this is a modelling
    assumption [A], not a verified ownership-structure fact.
    """
    if rooms < config.FIT_SWEET_SPOT_MIN_ROOMS:
        return config.FIT_TOO_SMALL_SCORE
    if rooms <= config.FIT_SWEET_SPOT_MAX_ROOMS:
        return config.FIT_SWEET_SPOT_SCORE
    if rooms <= config.FIT_MID_MAX_ROOMS:
        return config.FIT_MID_SCORE
    return config.FIT_LARGE_SCORE


def compute_jalpulse(df: pd.DataFrame) -> pd.DataFrame:
    """Take the raw hotel dataframe and return it with all JalPulse columns added."""
    df = df.copy()

    df["commercial_value_raw"] = df["rooms"].apply(lambda r: math.log(r + 1, config.COMMERCIAL_LOG_BASE))
    max_cv = df["commercial_value_raw"].max()
    df["commercial_value"] = df["commercial_value_raw"] / max_cv

    df["regulatory_urgency_raw"] = df["rooms"].apply(_regulatory_urgency)
    df["regulatory_urgency"] = df["regulatory_urgency_raw"] / 3.0

    df["service_tier"] = df["taluka"].apply(_service_tier)
    df["service_tier_score_raw"] = df["service_tier"].map(config.SERVICE_TIER_SCORE)
    df["service_tier_score"] = df["service_tier_score_raw"] / 3.0

    df["value_score"] = (
        config.WEIGHT_COMMERCIAL * df["commercial_value"]
        + config.WEIGHT_REGULATORY * df["regulatory_urgency"]
        + config.WEIGHT_SERVICE * df["service_tier_score"]
    ).round(4)

    df["decision_fit"] = df["rooms"].apply(_decision_fit)
    df["phase1_score"] = (df["value_score"] * df["decision_fit"]).round(4)

    # Tiering on value_score (percentile cut points from config)
    sorted_scores = df["value_score"].sort_values(ascending=False).reset_index(drop=True)
    n = len(sorted_scores)
    priority_cut = sorted_scores.iloc[max(0, int(n * config.PRIORITY_PERCENTILE) - 1)]
    watch_cut = sorted_scores.iloc[max(0, int(n * config.WATCH_PERCENTILE) - 1)]

    def _tier(score):
        if score >= priority_cut:
            return "Priority"
        if score >= watch_cut:
            return "Watch"
        return "Long-tail"

    df["tier"] = df["value_score"].apply(_tier)
    df.attrs["priority_cut"] = float(priority_cut)
    df.attrs["watch_cut"] = float(watch_cut)

    return df.sort_values("value_score", ascending=False).reset_index(drop=True)


def build_phase1_shortlist(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Properties inside the owner/GM decision-fit sweet spot, ranked by value."""
    pool = scored_df[
        (scored_df["rooms"] >= config.FIT_SWEET_SPOT_MIN_ROOMS)
        & (scored_df["rooms"] <= config.FIT_SWEET_SPOT_MAX_ROOMS)
    ].copy()
    return pool.sort_values("value_score", ascending=False).reset_index(drop=True)


def build_priority_and_winnable(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Properties that are BOTH top-tier by value AND inside the decision-fit
    sweet spot -- i.e. both worth winning and actually winnable.

    This is the headline account list ("428 accounts") used throughout the
    deck. It is deliberately the intersection, not either cut alone: a
    property can score Priority on value_score purely because it is a large
    branded/chain property (which decision_fit already flags as low-fit,
    since those are corporate-procured, not owner-signed) -- see
    src/score.py's compute_jalpulse for why decision_fit exists at all.
    """
    both = scored_df[
        (scored_df["tier"] == "Priority")
        & (scored_df["rooms"] >= config.FIT_SWEET_SPOT_MIN_ROOMS)
        & (scored_df["rooms"] <= config.FIT_SWEET_SPOT_MAX_ROOMS)
    ].copy()
    return both.sort_values("value_score", ascending=False).reset_index(drop=True)


def build_taluka_summary(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Tier counts by taluka -- feeds the GTM roadmap's phase/geography table."""
    summary = (
        scored_df.groupby(["district", "taluka", "tier"])
        .size()
        .unstack(fill_value=0)
    )
    for col in ("Priority", "Watch", "Long-tail"):
        if col not in summary.columns:
            summary[col] = 0
    summary["total"] = summary[["Priority", "Watch", "Long-tail"]].sum(axis=1)
    summary = summary.sort_values("Priority", ascending=False).reset_index()
    return summary


def run(force_reextract: bool = False) -> dict[str, pd.DataFrame]:
    if not config.RAW_CSV["goa_hotels"].exists():
        raise FileNotFoundError(
            f"{config.RAW_CSV['goa_hotels']} not found -- run `python -m src.extract` first."
        )
    raw = pd.read_csv(config.RAW_CSV["goa_hotels"])
    log.info(f"loaded {len(raw)} raw properties")

    scored = compute_jalpulse(raw)
    log.info(
        f"scored {len(scored)} properties | priority_cut={scored.attrs['priority_cut']:.3f} "
        f"watch_cut={scored.attrs['watch_cut']:.3f}"
    )
    tier_counts = scored["tier"].value_counts().to_dict()
    log.info(f"tier distribution: {tier_counts}")

    phase1 = build_phase1_shortlist(scored)
    log.info(f"phase-1 fit pool ({config.FIT_SWEET_SPOT_MIN_ROOMS}-{config.FIT_SWEET_SPOT_MAX_ROOMS} rooms): {len(phase1)} properties")

    priority_and_winnable = build_priority_and_winnable(scored)
    log.info(f"priority AND winnable (the deck's headline account list): {len(priority_and_winnable)} properties")

    taluka_summary = build_taluka_summary(scored)

    scored.to_csv(config.PROCESSED_CSV["jalpulse_full"], index=False)
    phase1.to_csv(config.PROCESSED_CSV["jalpulse_phase1"], index=False)
    priority_and_winnable.to_csv(config.PROCESSED_CSV["jalpulse_priority_and_winnable"], index=False)
    taluka_summary.to_csv(config.PROCESSED_CSV["taluka_summary"], index=False)
    log.info(f"wrote {config.PROCESSED_CSV['jalpulse_full']}")
    log.info(f"wrote {config.PROCESSED_CSV['jalpulse_phase1']}")
    log.info(f"wrote {config.PROCESSED_CSV['jalpulse_priority_and_winnable']}")
    log.info(f"wrote {config.PROCESSED_CSV['taluka_summary']}")

    return {
        "scored": scored,
        "phase1": phase1,
        "priority_and_winnable": priority_and_winnable,
        "taluka_summary": taluka_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Run the JalPulse scoring engine.")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    run()


if __name__ == "__main__":
    main()
