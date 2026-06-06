"""Print a copy-pasteable starter for theme_overrides.json.

Reads the current dashboard.html, finds all posts where theme=='Uncategorized'
(or whatever filter you set), and emits a JSON object you can hand-edit.

Usage:
    python seed_theme_overrides.py           # all uncategorized
    python seed_theme_overrides.py @kalpesh.kinariwala  # one account
    python seed_theme_overrides.py --misclassified Theme1 Theme2  # specific themes to review

Then save the output to theme_overrides.json and edit the empty "" values.
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(BASE, "dashboard.html")

ALLOWED_THEMES = [
    "Project Launch", "Investment", "Event / Occasion",
    "Real Estate Market", "Business / Leadership", "Press / Media Coverage",
    "Behind the Scenes / Team", "Motivational / Inspirational",
    "Partnership / Collaboration", "Cultural / Community",
    "Personal Storytelling", "Lifestyle / Personal",
]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    if not os.path.exists(DASHBOARD):
        print("[ERROR] dashboard.html not found. Run `python build_dashboard.py` first.")
        sys.exit(1)
    with open(DASHBOARD, "r", encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r"const DATA = (\[.*?\]);", html, re.DOTALL)
    if not m:
        print("[ERROR] DATA array not found in dashboard.html")
        sys.exit(1)
    data = json.loads(m.group(1))

    args = sys.argv[1:]
    handle_filter = None
    target_themes = ["Uncategorized"]
    if args and args[0].startswith("@"):
        handle_filter = args[0].lstrip("@")
        args = args[1:]
    if args and args[0] == "--misclassified":
        target_themes = args[1:] if len(args) > 1 else ["Uncategorized"]

    posts = [
        p for p in data
        if p.get("isOwn")
        and p.get("theme") in target_themes
        and (handle_filter is None or p["account"] == handle_filter)
    ]
    posts.sort(key=lambda x: -(x.get("engagement") or 0))

    print(f"// {len(posts)} posts matching: theme in {target_themes}" + (f", account=@{handle_filter}" if handle_filter else ""))
    print("// Copy this into theme_overrides.json, then replace each \"\" with one of:")
    print("//   " + " | ".join(ALLOWED_THEMES))
    print("// Save and re-run `python build_dashboard.py`.")
    print()
    print("{")
    print('  "_README": "Hand-curated theme overrides. Higher priority than theme_cache.json and rules. Key = post shortCode, value = theme. Lines with keys starting _ are ignored.",')
    print('  "_VALID_THEMES": ' + json.dumps(ALLOWED_THEMES) + ",")
    print()
    for i, p in enumerate(posts):
        cap = (p.get("caption") or "").replace("\n", " ").strip()[:90]
        cap_escaped = cap.replace('"', "'")
        eng = p.get("engagement") or 0
        url = p.get("url") or ""
        comma = "," if i < len(posts) - 1 else ""
        print(f'  "_note_{p["shortCode"]}": "@{p["account"]} | {p["type"]} | {eng} eng | {cap_escaped} | {url}",')
        print(f'  "{p["shortCode"]}": ""{comma}')
        if i < len(posts) - 1:
            print()
    print("}")


if __name__ == "__main__":
    main()
