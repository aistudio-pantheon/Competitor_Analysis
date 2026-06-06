"""Flatten Apify Instagram-scraper JSON output into a flat CSV that build_dashboard.py understands.

Usage:
    python flatten_to_csv.py <input.json> <output.csv>
"""
import csv
import json
import sys


def flatten(obj, prefix="", out=None):
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{prefix}/{k}" if prefix else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}/{i}", out)
    else:
        out[prefix] = obj
    return out


def main():
    if len(sys.argv) < 3:
        print("usage: flatten_to_csv.py <input.json> <output.csv>")
        sys.exit(1)
    inp, outp = sys.argv[1], sys.argv[2]
    with open(inp, "r", encoding="utf-8") as fh:
        items = json.load(fh)
    if not isinstance(items, list):
        items = [items]
    rows = [flatten(it) for it in items]
    fields = sorted({k for r in rows for k in r.keys()})
    with open(outp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {len(rows)} rows -> {outp}")


if __name__ == "__main__":
    main()
