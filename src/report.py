"""
report.py -- generate human-readable Markdown reports from the processed CSVs.

Two reports:
  reports/jalpulse_summary.md -- the analysis findings (tiers, taluka
      breakdown, top properties, the "value != winnable" caveat), written
      to be dropped near-verbatim into slide notes.
  reports/evidence_log.md -- every disclosed/extracted fact from EPBL's
      filings and the regulatory sources, each tagged [P]/[CD]/[D]/[A],
      for footnoting the final deck.

Usage:
    python -m src.report
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

log = logging.getLogger(__name__)


def _load_or_none(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        log.warning(f"missing: {path} -- run the earlier pipeline stages first")
        return None
    return pd.read_csv(path)


def generate_jalpulse_summary() -> Path:
    scored = _load_or_none(config.PROCESSED_CSV["jalpulse_full"])
    phase1 = _load_or_none(config.PROCESSED_CSV["jalpulse_phase1"])
    priority_and_winnable = _load_or_none(config.PROCESSED_CSV["jalpulse_priority_and_winnable"])
    taluka = _load_or_none(config.PROCESSED_CSV["taluka_summary"])
    out_path = config.REPORTS["jalpulse_summary"]

    if scored is None:
        out_path.write_text("# JalPulse summary\n\nNo scored data available -- run `python -m src.score` first.\n")
        return out_path

    n = len(scored)
    tier_counts = scored["tier"].value_counts()
    priority_n = int(tier_counts.get("Priority", 0))
    watch_n = int(tier_counts.get("Watch", 0))
    longtail_n = int(tier_counts.get("Long-tail", 0))

    priority_df = scored[scored["tier"] == "Priority"]
    priority_taluka = priority_df["taluka"].value_counts()
    bardez_share_of_priority = (
        priority_taluka.get("Bardez", 0) / priority_n if priority_n else 0
    )

    top100 = scored.nlargest(100, "value_score")
    big_in_top100 = int((top100["rooms"] > config.FIT_SWEET_SPOT_MAX_ROOMS).sum())

    top15_value = scored.nlargest(15, "value_score")[
        ["name", "name_confidence", "taluka", "rooms", "value_score", "decision_fit", "phase1_score", "tier"]
    ]

    lines = []
    lines.append("# JalPulse analysis summary")
    lines.append(f"\n_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z by `src/report.py`._\n")

    lines.append("## Coverage")
    lines.append(f"- {n:,} Goa accommodation properties scored (source: Goa Dept. of Tourism registry) `[P]`")
    lines.append(f"- Registry-wide parse coverage vs. max serial number: see `data/raw/goa_hotels_raw.csv` log output\n")

    lines.append("## Tier distribution (by value_score)")
    lines.append(f"- **Priority**: {priority_n:,} properties ({priority_n/n:.1%})")
    lines.append(f"- **Watch**: {watch_n:,} properties ({watch_n/n:.1%})")
    lines.append(f"- **Long-tail**: {longtail_n:,} properties ({longtail_n/n:.1%})\n")

    lines.append("## Priority-tier geographic concentration")
    lines.append(f"- Bardez alone accounts for {bardez_share_of_priority:.1%} of the {priority_n} Priority-tier properties `[D]`")
    lines.append("- Top talukas in the Priority tier:\n")
    lines.append("| Taluka | Priority-tier properties |")
    lines.append("|---|---|")
    for tal, cnt in priority_taluka.head(8).items():
        lines.append(f"| {tal} | {cnt} |")

    lines.append("\n## The value-vs-winnability caveat")
    lines.append(
        f"- Without a decision-fit adjustment, **{big_in_top100} of the top 100 properties by raw value_score** "
        f"are above {config.FIT_SWEET_SPOT_MAX_ROOMS} rooms -- i.e. likely branded/chain-managed, "
        "corporate-procured accounts that do not match EPBL's Persona 1 (independent owner/GM personally approves). "
        "`[D]` derived from this pipeline; do not present raw value_score as a sales-readiness ranking."
    )

    if priority_and_winnable is not None:
        pw_taluka = priority_and_winnable["taluka"].value_counts()
        pw_bardez_share = pw_taluka.get("Bardez", 0) / len(priority_and_winnable) if len(priority_and_winnable) else 0
        lines.append(
            f"\n## The headline account list: worth winning AND winnable\n"
            f"- **{len(priority_and_winnable):,} properties** are both Priority-tier by value_score "
            f"*and* inside the {config.FIT_SWEET_SPOT_MIN_ROOMS}-{config.FIT_SWEET_SPOT_MAX_ROOMS}-room "
            f"decision-fit band. `[D]` derived by intersecting the two cuts above.\n"
            f"- Bardez alone accounts for {pw_bardez_share:.1%} of this list "
            f"({pw_taluka.get('Bardez', 0)} of {len(priority_and_winnable)}).\n"
            f"- This is the pipeline's answer to \"which accounts should Year 1 actually call\" -- "
            f"see `data/processed/jalpulse_priority_and_winnable.csv` for the full list."
        )

    if phase1 is not None:
        lines.append(f"\n## Phase-1 shortlist (owner/GM decision-fit band: "
                      f"{config.FIT_SWEET_SPOT_MIN_ROOMS}-{config.FIT_SWEET_SPOT_MAX_ROOMS} rooms)")
        lines.append(f"- {len(phase1):,} properties fall inside the fit band `[A]` (see config.py for the room-band assumption)")
        p1_taluka = phase1["taluka"].value_counts().head(8)
        lines.append("\n| Taluka | Phase-1 fit-band properties |")
        lines.append("|---|---|")
        for tal, cnt in p1_taluka.items():
            lines.append(f"| {tal} | {cnt} |")

        lines.append("\n### Top 15 Phase-1 shortlist properties (by value_score within the fit band)")
        lines.append("_Names with `name_confidence=low` are parsing artifacts -- verify against the source PDF before using in outreach or on a slide._\n")
        lines.append("| Name | Confidence | Taluka | Rooms | Value score | Fit | Phase-1 score |")
        lines.append("|---|---|---|---|---|---|---|")
        top15_p1 = phase1.nlargest(15, "value_score")
        for _, r in top15_p1.iterrows():
            lines.append(
                f"| {r['name']} | {r['name_confidence']} | {r['taluka']} | {r['rooms']} | "
                f"{r['value_score']:.3f} | {r['decision_fit']:.2f} | {r['phase1_score']:.3f} |"
            )

    lines.append("\n## Top 15 properties by raw value_score (unfiltered -- includes low-fit large chains)")
    lines.append("| Name | Confidence | Taluka | Rooms | Value score | Tier |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in top15_value.iterrows():
        lines.append(
            f"| {r['name']} | {r['name_confidence']} | {r['taluka']} | {r['rooms']} | "
            f"{r['value_score']:.3f} | {r['tier']} |"
        )

    lines.append("\n## Methodology, in one paragraph")
    lines.append(
        "JalPulse combines three signals per property: commercial value (log-scaled room count, `[P]` real "
        "per-property data), regulatory urgency (GSPCB Consent-to-Operate size-band classification, `[P]` real "
        "policy applied categorically), and serviceability (taluka cluster density, `[P,D]` derived from the "
        "registry's own concentration). These are weighted into `value_score`. A separate `decision_fit` factor "
        "(room-count band as a proxy for independent ownership, `[A]` a stated modelling assumption) discounts "
        "`value_score` into `phase1_score`, so the Phase-1 shortlist reflects who EPBL can actually sell to "
        "in Year 1, not just who has the most wastewater. Full formula and every constant: `config.py`."
    )

    out_path.write_text("\n".join(lines) + "\n")
    log.info(f"wrote {out_path}")
    return out_path


def generate_evidence_log() -> Path:
    out_path = config.REPORTS["evidence_log"]
    lines = ["# Evidence log", f"\n_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z._\n"]
    lines.append(
        "Every figure below is tagged: **[P]** primary/regulatory source, **[CD]** company-disclosed, "
        "**[D]** derived by this pipeline, **[A]** case-team assumption. Use these tags on the deck itself.\n"
    )

    epbl_facts = _load_or_none(config.RAW_CSV["epbl_facts"])
    if epbl_facts is not None:
        lines.append("## EPBL annual report (FY 2024-25) `[CD]`")
        lines.append("| Fact | Value | Source line |")
        lines.append("|---|---|---|")
        for _, r in epbl_facts.iterrows():
            val = r["value"] if r["found"] else "_not found -- verify manually_"
            src_line = r.get("source_line", "")
            lines.append(f"| {r['fact_key']} | {val} | {src_line if pd.notna(src_line) else ''} |")
        lines.append("")

    drdo = _load_or_none(config.RAW_CSV["drdo_licence"])
    if drdo is not None:
        lines.append("## DRDO licence (EPBL prospectus) `[CD]`")
        lines.append("| Fact | Value |")
        lines.append("|---|---|")
        for _, r in drdo.iterrows():
            lines.append(f"| {r['fact_key']} | {r['value']} |")
        lines.append("")

    gspcb = _load_or_none(config.RAW_CSV["gspcb_rules"])
    if gspcb is not None and not gspcb.empty:
        lines.append("## GSPCB Consent-to-Operate rules `[P]`")
        lines.append("| Rule type | Detail | Value |")
        lines.append("|---|---|---|")
        for _, r in gspcb.iterrows():
            pc = r.get("pollution_category")
            rb = r.get("room_band")
            detail = pc if pd.notna(pc) else (rb if pd.notna(rb) else "")
            lines.append(f"| {r['rule_type']} | {detail} | {r['value']} |")
        lines.append("")

    rera = _load_or_none(config.RAW_CSV["rera_mis"])
    if rera is not None and not rera.empty:
        lines.append("## Goa RERA MIS dashboard `[P]` -- live counter, re-fetch date matters")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for _, r in rera.iterrows():
            lines.append(f"| {r['metric']} | {r['value']} |")
        lines.append("")

    goa_hotels = _load_or_none(config.RAW_CSV["goa_hotels"])
    if goa_hotels is not None:
        lines.append("## Goa hotel registry `[P]`")
        lines.append(f"- Total properties parsed: {len(goa_hotels):,} (registry max serial: {goa_hotels['sr'].max():,})")
        lines.append(f"- Properties with >=20 rooms: {(goa_hotels['rooms']>=20).sum():,}")
        lines.append(f"- Properties with 10-19 rooms: {((goa_hotels['rooms']>=10)&(goa_hotels['rooms']<=19)).sum():,}")
        lines.append(f"- Total rooms: {goa_hotels['rooms'].sum():,}")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n")
    log.info(f"wrote {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate Markdown reports from processed CSVs.")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    generate_jalpulse_summary()
    generate_evidence_log()


if __name__ == "__main__":
    main()
