"""
fetch.py -- download raw source documents.

Every source is defined once in config.SOURCES. This module just pulls
bytes off the network and writes them to data/raw/sources/ verbatim.
No parsing happens here (see extract.py) -- keeping fetch and extract
separate means a source that changes its HTML/PDF layout only breaks
extract.py, and you can always re-run extraction against a previously
cached raw file without hitting the network again.

Usage:
    python -m src.fetch                # fetch everything, skip what's cached
    python -m src.fetch --force        # re-download everything
    python -m src.fetch --only goa_hotel_registry epbl_annual_report
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
TIMEOUT_SECONDS = 30


def _download(url: str, dest: Path, force: bool = False) -> bool:
    """Download `url` to `dest`. Returns True on success (including cache hit)."""
    if dest.exists() and not force:
        log.info(f"cached, skipping: {dest.name}")
        return True
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        log.info(f"downloaded {len(resp.content):,} bytes -> {dest.name}")
        return True
    except requests.RequestException as exc:
        log.warning(f"FAILED to fetch {url}: {exc}")
        if dest.exists():
            log.warning(f"falling back to stale cached copy: {dest.name}")
            return True
        return False


def fetch_source(key: str, force: bool = False) -> bool:
    """Fetch one named source from config.SOURCES. Returns success bool."""
    src = config.SOURCES[key]
    dest_attr = "local_pdf" if "local_pdf" in src else "local_html"
    dest = src[dest_attr]
    log.info(f"fetching '{key}' [{src['tag']}] -- {src['note']}")
    return _download(src["url"], dest, force=force)


def fetch_all(force: bool = False, only: list[str] | None = None) -> dict[str, bool]:
    """Fetch every configured source (or a subset via `only`). Returns {key: success}."""
    keys = only if only else list(config.SOURCES.keys())
    results = {}
    for key in keys:
        results[key] = fetch_source(key, force=force)
    ok = sum(results.values())
    log.info(f"fetch complete: {ok}/{len(results)} sources available")
    return results


def main():
    parser = argparse.ArgumentParser(description="Download raw source documents for JalPulse analysis.")
    parser.add_argument("--force", action="store_true", help="re-download even if a cached copy exists")
    parser.add_argument("--only", nargs="*", default=None, help="fetch only these source keys")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    results = fetch_all(force=args.force, only=args.only)
    if not all(results.values()):
        failed = [k for k, v in results.items() if not v]
        log.error(f"one or more sources failed and had no cache to fall back on: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
