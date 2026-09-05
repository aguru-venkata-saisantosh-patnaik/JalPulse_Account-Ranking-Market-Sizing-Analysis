#!/usr/bin/env python3
"""
run_all.py -- run the full JalPulse pipeline end to end:

    fetch (download raw sources)
      -> extract (raw sources -> structured raw CSVs)
      -> score (raw CSVs -> processed/scored CSVs)
      -> report (processed CSVs -> Markdown reports)

Every stage's outputs are cached, so re-running this is cheap and
idempotent unless you pass --force / --force-refetch. This is the single
entry point referenced by the notebook at notebooks/JalPulse_Analysis.ipynb
-- the notebook just calls the same four functions cell by cell so you can
inspect intermediate results interactively.

Usage:
    python run_all.py                  # normal run, uses caches where present
    python run_all.py --force-refetch  # re-download every source from the network
    python run_all.py --force-extract  # re-run pdftotext/parsing even if cached
    python run_all.py --skip-fetch     # assume data/raw/sources/* already exists
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Configure logging once, centrally, before importing the pipeline stages --
# each stage module only does `log = logging.getLogger(__name__)` and relies
# on this format, so log lines are correctly tagged by stage (src.fetch,
# src.extract, src.score, src.report) instead of all inheriting whichever
# module happened to import first.
logging.basicConfig(level=logging.INFO, format="%(name)-12s %(message)s")

import config
from src import extract, fetch, report, score

log = logging.getLogger("run_all")


def main():
    parser = argparse.ArgumentParser(description="Run the full JalPulse analysis pipeline.")
    parser.add_argument("--force-refetch", action="store_true", help="re-download all sources from the network")
    parser.add_argument("--force-extract", action="store_true", help="re-run PDF/HTML extraction even if cached")
    parser.add_argument("--skip-fetch", action="store_true", help="skip the fetch stage entirely (use existing data/raw/sources/*)")
    args = parser.parse_args()

    log.info("=" * 70)
    log.info("STAGE 1/4: fetch")
    log.info("=" * 70)
    if args.skip_fetch:
        log.info("skipped (--skip-fetch)")
    else:
        results = fetch.fetch_all(force=args.force_refetch)
        if not all(results.values()):
            log.error("one or more sources unavailable -- aborting. See warnings above.")
            sys.exit(1)

    log.info("=" * 70)
    log.info("STAGE 2/4: extract")
    log.info("=" * 70)
    extract.extract_all(force=args.force_extract)

    log.info("=" * 70)
    log.info("STAGE 3/4: score")
    log.info("=" * 70)
    score.run()

    log.info("=" * 70)
    log.info("STAGE 4/4: report")
    log.info("=" * 70)
    report.generate_jalpulse_summary()
    report.generate_evidence_log()

    log.info("=" * 70)
    log.info("DONE. Outputs:")
    log.info(f"  raw CSVs:       {config.RAW_DIR}")
    log.info(f"  processed CSVs: {config.PROCESSED_DIR}")
    log.info(f"  reports:        {config.REPORTS_DIR}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
