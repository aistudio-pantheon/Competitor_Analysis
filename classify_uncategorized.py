"""Classify Uncategorized Instagram posts via Claude API.

Reads the current dashboard.html, finds all posts where theme=='Uncategorized',
batches them to Claude, writes results to theme_cache.json keyed by shortCode.

build_dashboard.py will read theme_cache.json on next run and override the
theme field for any cached shortCode.

Usage:
    set ANTHROPIC_API_KEY=sk-ant-...
    python classify_uncategorized.py

Cost: ~$0.10-1.00 one-time depending on uncategorized count + model choice.
Defaults to Claude Sonnet 4.5 for accuracy.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

# Force UTF-8 stdout on Windows so the progress bars and any emoji output don't crash
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE, "theme_cache.json")
DASHBOARD_PATH = os.path.join(BASE, "dashboard.html")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
BATCH_SIZE = int(os.environ.get("CLASSIFY_BATCH", "12"))

ALLOWED_THEMES = [
    "Project Launch",
    "Investment",
    "Event / Occasion",
    "Real Estate Market",
    "Business / Leadership",
    "Press / Media Coverage",
    "Behind the Scenes / Team",
    "Motivational / Inspirational",
    "Partnership / Collaboration",
    "Cultural / Community",
    "Personal Storytelling",
    "Lifestyle / Personal",
    "Uncategorized",
]

THEME_DESCRIPTIONS = """\
Available themes (you must pick exactly ONE per post, output EXACTLY as written):

1. Project Launch — announcing/promoting a specific named property, development, building, or new real-estate project (LUXOR, VOXA, La Perla, FashionTV Acacia, Samana Hills, etc.)
2. Investment — ROI, returns, payment plans, freehold, financial/investment angle, golden visa, capital appreciation
3. Event / Occasion — corporate awards, conferences, expos, gala ceremonies, anniversaries, corporate milestones (Gulf Business Awards, Cityscape, etc.)
4. Real Estate Market — Dubai/UAE real estate industry trends, market commentary, off-plan market reports
5. Business / Leadership — founder/CEO/chairman content, vision statements, leadership philosophy, strategy, discipline, entrepreneurship
6. Press / Media Coverage — featured in publications, interviews, press recognition (Forbes, Gulf Business, Entrepreneur ME)
7. Behind the Scenes / Team — office life, team culture, BTS content, sales gallery, showroom, internal team building
8. Motivational / Inspirational — generic motivational quotes/messages WITHOUT personal narrative (vague aspirational copy, "every step matters", "vision becomes reality")
9. Partnership / Collaboration — collabs with celebrities, brand partnerships, ambassadors (e.g., Hrithik Roshan x Imtiaz, Portuguese Football Federation)
10. Cultural / Community — concerts, festivals (Holi, Diwali), religious/spiritual moments, community events (Sitar for Mental Health, Holiverse Cricket, Arijit Singh concert, Bageshwar Dham blessing)
11. Personal Storytelling — autobiographical narrative, life lessons, personal struggles or reflections ("When my father passed...", "My journey from...", Bigg Boss memoir)
12. Lifestyle / Personal — family, fitness, travel, food, personal moments without narrative storytelling structure
13. Uncategorized — ONLY if the post is genuinely uninterpretable (corrupted text, non-text content)
"""

SYSTEM_PROMPT = (
    "You are an expert Instagram content classifier for a real-estate competitive intelligence dashboard. "
    "You will be given a batch of Instagram posts. For each post, output the single most appropriate theme from the provided list. "
    "Posts may be in English, Arabic, Persian/Farsi, or Hindi — translate mentally and classify by meaning. "
    "Output format: one theme per line, in the same numeric order as the input. No extra commentary, no explanations, no numbering."
)


def load_uncategorized():
    """Read dashboard.html to extract the DATA JS array and return posts with theme=='Uncategorized'."""
    if not os.path.exists(DASHBOARD_PATH):
        print(f"[ERROR] {DASHBOARD_PATH} not found. Run `python build_dashboard.py` first.")
        sys.exit(1)
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as fh:
        html = fh.read()
    m = re.search(r"const DATA = (\[.*?\]);", html, re.DOTALL)
    if not m:
        print("[ERROR] Could not find DATA array in dashboard.html")
        sys.exit(1)
    data = json.loads(m.group(1))
    return [p for p in data if p.get("isOwn") and p.get("theme") == "Uncategorized"]


def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)


def call_claude(batch, api_key):
    """Send a batch of posts; return list of theme strings (same length as batch)."""
    # Build the user message
    lines = []
    for i, p in enumerate(batch, 1):
        caption = (p.get("caption") or "").replace("\n", " ").strip()[:600]
        hashtags = " ".join(f"#{h}" for h in (p.get("hashtags") or [])[:12])
        owner_full = p.get("ownerFullName", "")
        kind = p.get("type", "")
        lines.append(f"[{i}] type={kind} caption={caption}  tags={hashtags}")
    user_msg = (
        f"{THEME_DESCRIPTIONS}\n\n"
        f"Classify the following {len(batch)} Instagram posts. "
        f"Output ONE theme per line, in input order, no numbering or explanations:\n\n"
        + "\n".join(lines)
    )

    payload = {
        "model": MODEL,
        "max_tokens": 800,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] API HTTPError {e.code}: {err_body[:400]}")
        raise
    text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    lines_out = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    # Normalize: strip leading numbering / quotes
    cleaned = []
    for ln in lines_out:
        ln = re.sub(r"^[\[\(]?\d+[\]\)]?[\.\:\)]?\s*", "", ln).strip().strip('"').strip("'")
        # Fuzzy-match to allowed themes
        match = next((t for t in ALLOWED_THEMES if t.lower() == ln.lower()), None)
        if not match:
            # Try partial match
            match = next((t for t in ALLOWED_THEMES if ln.lower() in t.lower() or t.lower() in ln.lower()), None)
        cleaned.append(match or "Uncategorized")
    # Pad or truncate to expected length
    while len(cleaned) < len(batch):
        cleaned.append("Uncategorized")
    return cleaned[: len(batch)]


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY environment variable is not set.")
        print("   Set it before running:")
        print('     PowerShell:  $env:ANTHROPIC_API_KEY = "sk-ant-..."')
        print('     CMD:         set ANTHROPIC_API_KEY=sk-ant-...')
        sys.exit(1)

    uncategorized = load_uncategorized()
    cache = load_cache()
    todo = [p for p in uncategorized if p.get("shortCode") and p["shortCode"] not in cache]

    print(f"Found {len(uncategorized)} uncategorized posts ({len(cache)} already cached, {len(todo)} new).")
    if not todo:
        print("[OK] Nothing to classify. theme_cache.json is up-to-date.")
        return

    print(f"Classifying {len(todo)} posts via {MODEL} in batches of {BATCH_SIZE}...")
    print()

    processed = 0
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i : i + BATCH_SIZE]
        try:
            themes = call_claude(batch, api_key)
        except Exception as e:
            print(f"[WARN]  Batch {i // BATCH_SIZE + 1} failed: {e}. Retrying once in 5s...")
            time.sleep(5)
            try:
                themes = call_claude(batch, api_key)
            except Exception as e2:
                print(f"[ERROR] Batch retry failed: {e2}. Skipping batch.")
                continue

        for p, t in zip(batch, themes):
            cache[p["shortCode"]] = t
            processed += 1
        save_cache(cache)  # save after every batch in case of interruption

        bar_done = "█" * int(20 * (i + len(batch)) / len(todo))
        bar_rest = "░" * (20 - len(bar_done))
        print(f"  [{bar_done}{bar_rest}] {min(i + len(batch), len(todo))}/{len(todo)}")
        time.sleep(0.6)  # gentle pacing

    print()
    print(f"[OK] Classified {processed} posts. Cache written to {CACHE_PATH}")
    print()
    print("Now run:  python build_dashboard.py")
    print("(The build script will read theme_cache.json and override theme for cached posts.)")


if __name__ == "__main__":
    main()
