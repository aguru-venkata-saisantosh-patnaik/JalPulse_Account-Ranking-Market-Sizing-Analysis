"""JalPulse analysis pipeline -- modular source package.

Modules:
    fetch    -- download raw source documents to data/raw/sources/
    extract  -- parse raw sources into structured, unscored CSVs in data/raw/
    score    -- run the JalPulse scoring model, write data/processed/*.csv
    report   -- generate human-readable Markdown reports in reports/
"""
