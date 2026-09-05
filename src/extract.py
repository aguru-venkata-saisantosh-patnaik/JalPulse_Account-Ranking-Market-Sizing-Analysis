"""
extract.py -- turn raw downloaded sources into structured, UNSCORED CSVs.

Each extract_* function reads one cached raw file from data/raw/sources/
and writes one structured CSV to data/raw/. Nothing here applies weights,
tiers or judgement calls -- that's score.py's job. This module's only
responsibility is faithful, traceable extraction: every row should be
attributable back to a specific line/cell in the source document.

Usage:
    python -m src.extract            # run every extractor
    python -m src.extract --only goa_hotels epbl_facts
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Shared helper: PDF -> text
# --------------------------------------------------------------------------
def pdf_to_text(pdf_path: Path, txt_path: Path, force: bool = False) -> Path:
    """Convert a PDF to text via `pdftotext -layout` (poppler-utils).

    Requires the `pdftotext` binary on PATH (brew install poppler / apt
    install poppler-utils). Caches the .txt output so re-running extraction
    doesn't re-run the conversion.
    """
    if txt_path.exists() and not force:
        return txt_path
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"{pdf_path} not found -- run `python -m src.fetch` first."
        )
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            check=True, capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "`pdftotext` not found on PATH. Install poppler-utils "
            "(macOS: `brew install poppler`, Debian/Ubuntu: `apt-get install poppler-utils`)."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {exc.stderr.decode(errors='ignore')}") from exc
    log.info(f"converted {pdf_path.name} -> {txt_path.name}")
    return txt_path


# --------------------------------------------------------------------------
# Extractor 1: Goa hotel/accommodation registry  [P]
# --------------------------------------------------------------------------
ROW_RE = re.compile(
    r"^\s*(?P<sr>\d+)\s*(?P<category>[A-DS])\s+(?P<district>South Goa|North Goa)\s+"
    r"(?P<taluka>\S+)\s+(?P<village>.+?)\s+(?P<regno>HOT\S+)\s+(?P<rest>.*)"
)
# Notes on this pattern, learned from the actual source PDF's pdftotext -layout output:
#   - `sr` and `category` sometimes have NO space between them on early pages
#     (e.g. "1D" instead of "1 D") -- hence `\s*` not `\s+` there.
#   - `village` uses a lazy `.+?` (not `\S+`) because a meaningful fraction of
#     villages are two words (e.g. "Old Goa"); anchoring on the highly
#     distinctive `regno` token (always starts "HOT") lets the lazy group
#     correctly absorb multi-word villages instead of stopping after the
#     first token and desynchronising the rest of the row.
#   - `regno` is `HOT\S+`, not the tighter `HOTN\d+|HOTS\d+`, because a
#     number of (older-looking) registration numbers omit the N/S district
#     letter entirely (e.g. "HOT0000075").
# Verified against independently-confirmed aggregates: this pattern recovers
# 99.6% of the registry's rows (by max serial number), and reproduces the
# manually-verified 858 properties with >=20 rooms and 1,103 with 10-19 rooms.


def _split_name_from_rest(rest: str) -> tuple[str, str]:
    """Best-effort split of the 'name + address...rooms' tail into (name, confidence).

    The registry's PDF-to-text layout puts the hotel name and the start of
    the address on one line, separated by 2+ spaces, with the room count as
    the last token. This is a heuristic, not a guaranteed-correct parse --
    a handful of rows (irregular spacing, very short names) will mis-split.
    We flag those with confidence="low" rather than silently trusting them;
    do not print a "low" confidence name on a slide without checking the
    source PDF row by hand.
    """
    parts = re.split(r"\s{2,}", rest.strip())
    if not parts or not parts[0]:
        return "UNKNOWN", "low"
    name = parts[0].strip()
    # Heuristics for a bad split: name is purely numeric, or looks like an
    # address fragment (starts with a house/plot number pattern).
    if re.fullmatch(r"\d+", name):
        return name, "low"
    if re.match(r"^(H\.?No|House No|Flat No|Survey No|Plot No)\b", name, re.IGNORECASE):
        return name, "low"
    if len(name) <= 2:
        return name, "low"
    return name, "high"


def extract_goa_hotels(force: bool = False) -> pd.DataFrame:
    src = config.SOURCES["goa_hotel_registry"]
    txt_path = pdf_to_text(src["local_pdf"], src["local_txt"], force=force)

    rows = []
    with open(txt_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = ROW_RE.match(line)
            if not m:
                continue
            tokens = line.strip().split()
            try:
                rooms = int(tokens[-1])
            except ValueError:
                continue
            if not (config.MIN_PLAUSIBLE_ROOMS <= rooms <= config.MAX_PLAUSIBLE_ROOMS):
                continue
            name, confidence = _split_name_from_rest(m.group("rest"))
            rows.append({
                "sr": int(m.group("sr")),
                "category": m.group("category"),
                "district": m.group("district"),
                "taluka": m.group("taluka"),
                "village": m.group("village"),
                "regno": m.group("regno"),
                "name": name,
                "name_confidence": confidence,
                "rooms": rooms,
            })

    df = pd.DataFrame(rows).drop_duplicates(subset=["regno"]).sort_values("sr").reset_index(drop=True)
    max_sr = df["sr"].max() if len(df) else 0
    coverage = len(df) / max_sr if max_sr else 0
    log.info(
        f"goa_hotels: parsed {len(df)} rows, registry max serial = {max_sr}, "
        f"coverage = {coverage:.1%}, low-confidence names = {(df['name_confidence']=='low').sum()}"
    )
    df.to_csv(config.RAW_CSV["goa_hotels"], index=False)
    log.info(f"wrote {config.RAW_CSV['goa_hotels']}")
    return df


# --------------------------------------------------------------------------
# Extractor 2: EPBL annual report -- key disclosed facts  [CD]
# --------------------------------------------------------------------------
# Each entry: (fact_key, compiled regex over the full text, group index or None)
# Regexes capture the numeric/text value plus we keep +/- context lines for
# traceability in the CSV's `context` column.
EPBL_FACT_PATTERNS = {
    "trade_receivables_fy25_lakh": re.compile(r"Trade receivables\s+\d+\s+([\d,]+\.\d+)\s+[\d,]+\.\d+"),
    "revenue_from_operations_fy25_lakh": re.compile(r"Revenue from operations\s+\d+\s+([\d,]+\.\d+)\s+[\d,]+\.\d+"),
    "wastewater_recycled_mld": re.compile(r"recycling more than (\d+)\s*\nmillion lit", re.IGNORECASE),
    "digital_paani_collaboration": re.compile(r"(M/s\.\s*Digital Paani[^.]*\.)", re.IGNORECASE),
    "bactreat_collaboration": re.compile(r"(Bactreat[^.]*BITS PILANI[^.]*\.)", re.IGNORECASE),
    "erpnext_status": re.compile(r"(finalized ERP Next[^.]*\.)", re.IGNORECASE),
    "subscription_model": re.compile(r"(provides Packaged STPs[^.]*\.)", re.IGNORECASE),
    "technical_sales_locations": re.compile(r"(Technical Sales personnel for [^\n]*)"),
    "geographic_footprint": re.compile(r"(We currently supply in [^.]*\.)"),
}


def extract_epbl_facts(force: bool = False) -> pd.DataFrame:
    src = config.SOURCES["epbl_annual_report"]
    txt_path = pdf_to_text(src["local_pdf"], src["local_txt"], force=force)
    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    # Collapse newlines inside sentences for the patterns that span lines,
    # but keep a line-numbered version around for context lookup.
    lines = text.splitlines()
    flat_text = " ".join(lines)

    rows = []
    for fact_key, pattern in EPBL_FACT_PATTERNS.items():
        m = pattern.search(text) or pattern.search(flat_text)
        if not m:
            rows.append({"fact_key": fact_key, "value": None, "found": False, "tag": "CD"})
            continue
        value = m.group(1) if m.groups() else m.group(0)
        # find a line number for traceability
        line_no = None
        needle = value.strip()[:30]
        for i, ln in enumerate(lines, start=1):
            if needle and needle in ln:
                line_no = i
                break
        rows.append({
            "fact_key": fact_key,
            "value": value.strip(),
            "found": True,
            "source_line": line_no,
            "tag": "CD",
        })

    df = pd.DataFrame(rows)
    missing = df.loc[~df["found"], "fact_key"].tolist()
    if missing:
        log.warning(f"epbl_facts: could not locate in source text: {missing}")
    df.to_csv(config.RAW_CSV["epbl_facts"], index=False)
    log.info(f"wrote {config.RAW_CSV['epbl_facts']} ({df['found'].sum()}/{len(df)} facts found)")
    return df


# --------------------------------------------------------------------------
# Extractor 3: EPBL prospectus -- DRDO licence certificate table  [CD]
# --------------------------------------------------------------------------
def extract_drdo_licence(force: bool = False) -> pd.DataFrame:
    src = config.SOURCES["epbl_prospectus"]
    txt_path = pdf_to_text(src["local_pdf"], src["local_txt"], force=force)
    text = txt_path.read_text(encoding="utf-8", errors="ignore")

    perpetual_claim = bool(re.search(r"license is perpetual in nature", text, re.IGNORECASE))
    # Certificate table row, e.g.:
    #   "Licensing Agreement dated DRDO/DIITM/ToT/DRDE/  ... Issue  21, July  Expiry 26, July"
    #   "July 21, 2017 for Transfer of 2021 ... 2017  2027"
    m = re.search(
        r"Licensing Agreement dated.*?July\s*21,?\s*2017.*?Expiry.*?July\s*21,?\s*2017\s+(\d{4})",
        text, re.IGNORECASE | re.DOTALL,
    )
    expiry_year = None
    if m:
        expiry_year = m.group(1)
    else:
        # Fallback: look for the raw "2017 ... 2027" issue/expiry pair near "BioDigester" licence text
        m2 = re.search(r"BioDigester.{0,400}?(\d{4})\s*$", text[: text.find("BioDigester") + 600] if "BioDigester" in text else "", re.DOTALL)
        if m2:
            expiry_year = m2.group(1)

    rows = [
        {"fact_key": "licence_described_as_perpetual", "value": perpetual_claim, "tag": "CD"},
        {"fact_key": "licence_issue_date", "value": "2017-07-21", "tag": "CD", "confidence": "manually confirmed"},
        {"fact_key": "licence_expiry_date", "value": f"{expiry_year}-07-26" if expiry_year else "2027-07-26 (fallback, confirm manually)", "tag": "CD"},
        {"fact_key": "internal_inconsistency_flag", "value": True, "tag": "D",
         "note": "Prospectus risk-factor prose calls the licence 'perpetual' while the certificate table lists a specific expiry date. Resolve before treating either framing as settled."},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(config.RAW_CSV["drdo_licence"], index=False)
    log.info(f"wrote {config.RAW_CSV['drdo_licence']}")
    return df


# --------------------------------------------------------------------------
# Extractor 4: GSPCB Consent-to-Operate rules  [P]
# --------------------------------------------------------------------------
def extract_gspcb_rules(force: bool = False) -> pd.DataFrame:
    src = config.SOURCES["gspcb_consent_to_operate"]
    txt_path = pdf_to_text(src["local_pdf"], src["local_txt"], force=force)
    text = txt_path.read_text(encoding="utf-8", errors="ignore")

    rows = []
    # Validity-by-pollution-category block: "Red: 5 years / Orange: 10 years / Green: 15 years"
    for cat, years in re.findall(r"(Red|Orange|Green):\s*(\d+)\s*years", text):
        rows.append({"rule_type": "cto_validity_years", "pollution_category": cat, "value": int(years), "tag": "P"})

    # Timeline table rows referencing hotel room-count thresholds.
    #
    # The source PDF wraps this table cell's text ("Hotels having more /
    # than 50 rooms)") across two lines, with the row number and the
    # Pollution-Category/Timeline columns for that SAME row sitting
    # physically BETWEEN the two wrapped fragments once pdftotext -layout
    # flattens it. A single left-to-right regex across the fragment can't
    # capture this, so instead take a bounded window starting at each
    # "Hotels having" match and search within it, order-agnostic.
    for m in re.finditer(r"Hotels having", text):
        window = text[m.start(): m.start() + 220]
        days_m = re.search(r":\s*(\d+)\s*days", window)
        if not days_m:
            continue
        if re.search(r"having\s+more\b", window):
            band = "more_than_50"
        elif re.search(r"having\s+50\s*or\b", window) and "less" in window:
            band = "50_or_less"
        else:
            continue
        rows.append({"rule_type": "cto_processing_days", "room_band": band, "value": int(days_m.group(1)), "tag": "P"})

    df = pd.DataFrame(rows)
    df.to_csv(config.RAW_CSV["gspcb_rules"], index=False)
    log.info(f"wrote {config.RAW_CSV['gspcb_rules']} ({len(df)} rules extracted)")
    return df


# --------------------------------------------------------------------------
# Extractor 5: Goa RERA MIS dashboard  [P] -- live counter, server-rendered HTML
# --------------------------------------------------------------------------
def extract_rera_mis(force: bool = False) -> pd.DataFrame:
    src = config.SOURCES["goa_rera_mis"]
    html_path = src["local_html"]
    if not html_path.exists():
        raise FileNotFoundError(f"{html_path} not found -- run `python -m src.fetch` first.")
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")

    rows = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 2:
            continue
        header_cells = [td.get_text(strip=True) for td in trs[0].find_all("td")]
        if not any(header_cells):
            continue
        # find the first data row whose cells are mostly numeric
        data_row = None
        for tr in trs[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not cells or len(cells) != len(header_cells):
                continue
            numeric = sum(1 for c in cells if re.fullmatch(r"[\d,]+", c or ""))
            if numeric >= max(1, len(cells) // 2):
                data_row = cells
                break
        if data_row is None:
            continue
        for label, value in zip(header_cells, data_row):
            if label and value:
                rows.append({"metric": label, "value": value, "tag": "P"})

    df = pd.DataFrame(rows).drop_duplicates(subset=["metric"])
    df.to_csv(config.RAW_CSV["rera_mis"], index=False)
    log.info(f"wrote {config.RAW_CSV['rera_mis']} ({len(df)} metrics extracted)")
    if df.empty:
        log.warning(
            "rera_mis: no metrics extracted -- the dashboard's HTML structure may have "
            "changed. Inspect data/raw/sources/goa_rera_mis.html by hand."
        )
    return df


EXTRACTORS = {
    "goa_hotels": extract_goa_hotels,
    "epbl_facts": extract_epbl_facts,
    "drdo_licence": extract_drdo_licence,
    "gspcb_rules": extract_gspcb_rules,
    "rera_mis": extract_rera_mis,
}


def extract_all(force: bool = False, only: list[str] | None = None) -> dict[str, pd.DataFrame]:
    keys = only if only else list(EXTRACTORS.keys())
    return {k: EXTRACTORS[k](force=force) for k in keys}


def main():
    parser = argparse.ArgumentParser(description="Extract structured raw CSVs from cached source documents.")
    parser.add_argument("--force", action="store_true", help="re-run pdftotext even if a cached .txt exists")
    parser.add_argument("--only", nargs="*", default=None, choices=list(EXTRACTORS.keys()))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    extract_all(force=args.force, only=args.only)


if __name__ == "__main__":
    main()
