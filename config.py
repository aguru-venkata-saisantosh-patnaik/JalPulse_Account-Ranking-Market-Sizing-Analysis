"""
Central configuration for the EPBL / BGCC JalPulse analysis pipeline.

Single source of truth for: source URLs, file paths, and every scoring
weight/threshold used by src/score.py. Nothing downstream should hardcode
a number that belongs here -- if you need to change an assumption, change
it here so every output (CSV, report, notebook) stays consistent.

Evidence tags used throughout this project (see reports/evidence_log.md):
  [P]  primary or regulatory source (govt registry, PCB circular, filing)
  [CD] company-disclosed (EPBL annual report / prospectus)
  [D]  derived by this pipeline from [P]/[CD] data
  [A]  assumption made by the case team (stated explicitly, not observed)
"""

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_SOURCES_DIR = RAW_DIR / "sources"      # original downloaded PDFs/HTML
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = ROOT_DIR / "reports"

for _d in (RAW_DIR, RAW_SOURCES_DIR, PROCESSED_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Source documents  [P] / [CD]
# --------------------------------------------------------------------------
SOURCES = {
    "goa_hotel_registry": {
        "url": "https://goatourism.gov.in/wp-content/uploads/2018/12/DoT-Registered-Hotels-23-Apr-2026.pdf",
        "local_pdf": RAW_SOURCES_DIR / "goa_hotel_registry.pdf",
        "local_txt": RAW_SOURCES_DIR / "goa_hotel_registry.txt",
        "tag": "P",
        "note": "Goa Dept. of Tourism, registered accommodation properties, last updated 23 Apr 2026.",
    },
    "epbl_annual_report": {
        "url": "https://epbiocomposites.com/wp-content/uploads/2025/09/Annual-Report-EPBL.pdf",
        "local_pdf": RAW_SOURCES_DIR / "epbl_annual_report.pdf",
        "local_txt": RAW_SOURCES_DIR / "epbl_annual_report.txt",
        "tag": "CD",
        "note": "EP Biocomposites Ltd, 6th Annual Report, FY 2024-25.",
    },
    "epbl_prospectus": {
        "url": "https://www.afsl.co.in/uploads/EP_Biocomposites_Limited_Prospectus.pdf",
        "local_pdf": RAW_SOURCES_DIR / "epbl_prospectus.pdf",
        "local_txt": RAW_SOURCES_DIR / "epbl_prospectus.txt",
        "tag": "CD",
        "note": "EP Biocomposites Ltd, abridged/IPO prospectus -- carries the DRDO licence certificate table.",
    },
    "gspcb_consent_to_operate": {
        "url": "https://goaspcb.gov.in/wp-content/uploads/2025/09/Consent-to-Operate.pdf",
        "local_pdf": RAW_SOURCES_DIR / "gspcb_cto.pdf",
        "local_txt": RAW_SOURCES_DIR / "gspcb_cto.txt",
        "tag": "P",
        "note": "Goa State Pollution Control Board -- Consent to Operate service standard (timelines + validity periods).",
    },
    "goa_rera_mis": {
        "url": "https://rera.goa.gov.in/reraApp/MIS",
        "local_html": RAW_SOURCES_DIR / "goa_rera_mis.html",
        "tag": "P",
        "note": "Goa RERA live MIS dashboard -- project and unit counts. Numbers are a live counter; re-fetch date matters.",
    },
}

# --------------------------------------------------------------------------
# Structured raw CSV outputs (unscored, directly extracted from sources)
# --------------------------------------------------------------------------
RAW_CSV = {
    "goa_hotels": RAW_DIR / "goa_hotels_raw.csv",
    "epbl_facts": RAW_DIR / "epbl_facts_raw.csv",
    "gspcb_rules": RAW_DIR / "gspcb_rules_raw.csv",
    "rera_mis": RAW_DIR / "rera_mis_raw.csv",
    "drdo_licence": RAW_DIR / "drdo_licence_raw.csv",
}

# --------------------------------------------------------------------------
# Processed (scored) CSV outputs
# --------------------------------------------------------------------------
PROCESSED_CSV = {
    "jalpulse_full": PROCESSED_DIR / "jalpulse_scored_full.csv",
    "jalpulse_phase1": PROCESSED_DIR / "jalpulse_phase1_shortlist.csv",
    "jalpulse_priority_and_winnable": PROCESSED_DIR / "jalpulse_priority_and_winnable.csv",
    "taluka_summary": PROCESSED_DIR / "taluka_tier_summary.csv",
}

# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
REPORTS = {
    "jalpulse_summary": REPORTS_DIR / "jalpulse_summary.md",
    "evidence_log": REPORTS_DIR / "evidence_log.md",
}

# --------------------------------------------------------------------------
# JalPulse scoring model
#
# Three signal layers, combined as a weighted sum into `value_score`, then
# discounted by `decision_fit` into `phase1_score`. Every weight/threshold
# below is a case-team modelling choice [A] unless noted otherwise -- change
# them here, re-run `run_all.py`, and every downstream file updates together.
# --------------------------------------------------------------------------

# Signal-layer weights (must sum to 1.0). [A]
WEIGHT_COMMERCIAL = 0.40   # wastewater load / order-size proxy (rooms, real per-property [P])
WEIGHT_REGULATORY = 0.35   # GSPCB Consent-to-Operate category threshold (real policy [P], applied categorically [D])
WEIGHT_SERVICE = 0.25      # taluka cluster density -> cost-to-serve proxy (real, derived from registry [P,D])

assert abs(WEIGHT_COMMERCIAL + WEIGHT_REGULATORY + WEIGHT_SERVICE - 1.0) < 1e-9, \
    "JalPulse layer weights must sum to 1.0"

# Regulatory urgency tiers, from GSPCB's own Consent-to-Operate classification [P]:
#   >50 rooms  = "Large Category" hotel  -> 90-day CTO processing, highest compliance visibility
#   20-50 rooms = "Micro/Small" hotel     -> 60-day CTO processing
#   <20 rooms   = below the size bands GSPCB's hotel table addresses at all
# All hotel CTOs are assumed "Orange" pollution category (10-year validity) per the same
# GSPCB document; this uniform assumption is [A] since per-property pollution category
# is not published in the tourism registry.
GSPCB_LARGE_CATEGORY_ROOMS = 50     # [P] GSPCB threshold, verbatim from source doc
GSPCB_MICRO_SMALL_MIN_ROOMS = 20    # [A] lower bound case team chose to still call "commercially material"
GSPCB_ORANGE_CTO_VALIDITY_YEARS = 10  # [P] GSPCB Consent-to-Operate validity for Orange category

REGULATORY_URGENCY_SCORE = {
    "large": 3,        # >50 rooms
    "micro_small": 2,  # 20-50 rooms
    "below_threshold": 1,  # <20 rooms
}

# Serviceability tiers, derived [D] from the registry's own concentration of
# >=20-room properties (independently verified: 858 total, 790 in these four
# talukas, 476 in Bardez alone).
SERVICE_TIER_1_TALUKAS = {"Bardez"}
SERVICE_TIER_2_TALUKAS = {"Salcete", "Pernem", "Tiswadi"}
SERVICE_TIER_SCORE = {1: 3, 2: 2, 3: 1}  # tier 1 = best serviceability -> highest score

# Commercial value: log2(rooms + 1), normalised 0-1 against the max in the
# dataset, so a 280-room property isn't literally weighted 280x a 1-room one.
COMMERCIAL_LOG_BASE = 2

# Tier cut points on the *value* score distribution (percentile-based). [A]
PRIORITY_PERCENTILE = 0.05   # top 5% by value_score = "Priority"
WATCH_PERCENTILE = 0.30      # next up to 30% = "Watch"; remainder = "Long-tail"

# Decision-maker fit: EPBL's Persona 1 (independent hotel/resort owner or GM,
# personally approves) does not describe corporate-procured branded/chain
# properties. Room-count band is used as an observable proxy for "likely
# independently owner-operated" -- this is a modelling proxy [A], not a
# verified ownership-structure fact. Cross-check big names manually before
# using this list to prioritise outreach.
FIT_SWEET_SPOT_MIN_ROOMS = 20
FIT_SWEET_SPOT_MAX_ROOMS = 120
FIT_SWEET_SPOT_SCORE = 1.00       # [A]
FIT_MID_MAX_ROOMS = 200
FIT_MID_SCORE = 0.50              # [A] plausible but likely needs a specifier/consultant sale, not owner-direct
FIT_LARGE_SCORE = 0.15            # [A] >200 rooms: near-certain corporate procurement / vendor panel
FIT_TOO_SMALL_SCORE = 0.30        # [A] <20 rooms: below today's packaged-STP commercial minimum

# Sanity bounds on room counts (drop obvious data-entry outliers)
MIN_PLAUSIBLE_ROOMS = 1
MAX_PLAUSIBLE_ROOMS = 500
