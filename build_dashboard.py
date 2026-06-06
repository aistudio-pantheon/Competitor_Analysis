"""Build a segment-aware competitor-intelligence dashboard.

Folder convention:
    Founder/<handle>/*.csv      -> founder personal accounts
    Enterprise/<handle>/*.csv   -> brand / enterprise accounts

Each CSV is an Apify Instagram-scraper dump. Records are deduplicated by shortCode.
Run: `python build_dashboard.py`  ->  writes dashboard.html in this folder.
"""
import csv
import json
import os
from collections import defaultdict
from datetime import datetime

csv.field_size_limit(10**8)
BASE = os.path.dirname(os.path.abspath(__file__))

SEGMENT_DIRS = [
    ("Founder",    "Founder"),
    ("Enterprise", "Enterprise"),
]

# Palette assigned in order to each unique account
PALETTE = [
    "#5b9cff", "#ff7ab6", "#46d3a0", "#ffb454", "#b97aff",
    "#ff6b8a", "#52d4e5", "#ffd166", "#7cffaa", "#ff8c5a",
    "#4facfe", "#f093fb", "#6ee2f5", "#f5576c", "#96e6a1",
    "#a18cd1", "#ffc3a0", "#43e97b", "#fa709a", "#c2e9fb"
]

import hashlib
def get_deterministic_color(handle):
    idx = int(hashlib.md5(handle.encode('utf-8')).hexdigest(), 16) % len(PALETTE)
    return PALETTE[idx]

def to_int(v):
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except Exception:
        return 0

def to_bool(v):
    return str(v).strip().lower() in ("true", "1", "yes")

def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def discover_files():
    """Yield (segment_label, handle_folder, file_path)."""
    for seg_label, seg_dir in SEGMENT_DIRS:
        seg_path = os.path.join(BASE, seg_dir)
        if not os.path.isdir(seg_path):
            continue
        for handle in sorted(os.listdir(seg_path)):
            handle_path = os.path.join(seg_path, handle)
            if not os.path.isdir(handle_path):
                continue
            for fn in sorted(os.listdir(handle_path)):
                if fn.lower().endswith(".csv"):
                    yield seg_label, handle, os.path.join(handle_path, fn)

records = []
seen = set()
known_accounts = defaultdict(set)  # segment -> set of handles

# Theme assignment priority (highest first):
#   1. theme_overrides.json  — hand-curated, never overwritten by code
#   2. theme_cache.json      — LLM-generated (from classify_uncategorized.py)
#   3. Rule-based classifier — keyword matching defined in THEMES below
#   4. "Uncategorized"       — fallback
THEME_CACHE = {}
THEME_OVERRIDES = {}
_cache_path = os.path.join(BASE, "theme_cache.json")
_overrides_path = os.path.join(BASE, "theme_overrides.json")
if os.path.exists(_cache_path):
    try:
        with open(_cache_path, "r", encoding="utf-8") as _fh:
            THEME_CACHE = json.load(_fh)
        print(f"Loaded {len(THEME_CACHE)} LLM-classified themes from theme_cache.json")
    except Exception as _e:
        print(f"[WARN] Could not load theme_cache.json: {_e}")
if os.path.exists(_overrides_path):
    try:
        with open(_overrides_path, "r", encoding="utf-8") as _fh:
            _raw = json.load(_fh)
        # strip comment/meta keys (anything starting with _) so users can leave notes in the file
        THEME_OVERRIDES = {k: v for k, v in _raw.items() if not k.startswith("_") and isinstance(v, str)}
        print(f"Loaded {len(THEME_OVERRIDES)} manual theme overrides from theme_overrides.json")
    except Exception as _e:
        print(f"[WARN] Could not load theme_overrides.json: {_e}")

# ====================== Theme / content-pillar classifier ======================
# Each theme has a list of keyword patterns. Matching is case-insensitive over
# caption + hashtags + mentions. A post is assigned to the highest-scoring theme.
# Order in dict matters for tie-break (earlier = preferred).
THEMES = {
    "Project Launch": [
        # explicit launch verbs + new-project signals
        "launch", "launching", "launched", "introducing", "presenting", "unveil",
        "now selling", "now open", "now booking", "coming soon", "off plan", "off-plan",
        "new project", "newproject", "new development", "ground breaking", "groundbreaking",
        "handover", "handovers", "deliver", "ready to move", "ready to handover",
        # specific project names from tracked accounts (BNW, Pantheon, Samana, Imtiaz)
        "la perla", "orvessa", "voxa", "elysee heights", "maison elysee", "rak central",
        "radisson blu", "ramada", "tonino lamborghini", "pearl development",
        "samana 50", "samana50", "lights camera 50", "samana greens", "burj samana",
        "samana hills", "samana barari", "barari lagoons", "autograph collection",
        "enre", "symphony", "sea cliff", "raw district", "rawdistrict",
        "imtiaz dubai island", "imtiaz dubai south", "danube", "skywaters",
        # BNW + Imtiaz additional projects
        "fashiontv acacia", "fashiontvacacia", "bnwxftv", "acacia",
        "luxor by imtiaz", "luxorbyimtiaz", "luxor",
        "sunset bay", "sunsetbay", "sunset bay collection",
        # BNW residual projects
        "taj wellington mews", "taj wellington", "tajwellington", "wellington mews",
        # Imtiaz residual projects
        "pearl house", "pearlhouse", "cove by imtiaz", "covebyimtiaz", "cove imtiaz",
        "beach walk grand", "beachwalkgrand", "beachwalk grand",
        "meydan horizon", "meydanhorizon", "wynwood horizon", "wynwoodhorizon",
        "westwood grande", "westwoodgrande",
        # Samana residual projects
        "samana imperial garden", "samanaimperialgarden", "imperial garden", "imperialgarden",
        "samana miami", "samanamiami", "samana santorini", "samanasantorini",
        "samana mykonos", "samanamykonos", "samana ivy", "samanaivy",
        "samana waves", "samanawaves", "samana avenue", "samanaavenue",
        # Pantheon residual projects
        "pantheon 2.0", "pantheon2.0", "pantheon2", "pantheon two",
        # Imtiaz additional residual
        "le blanc by imtiaz", "leblancbyimtiaz", "le blanc", "leblanc",
        "beach walk 4", "beachwalk4", "beach walk", "beachwalk",
        # Generic "by <brand>" project signaling
        "by imtiaz", "by samana", "by bnw", "by pantheon", "by danube",
        # Generic spatial / development descriptors when paired with project context
        "flexible home", "flexible home concept", "smart home concept",
        "residential development", "residential project", "residentialdevelopment",
        "coastal setting", "sea-facing", "sea facing", "seaview", "sea view",
        # Project update tag patterns
        "project update", "projectupdate", "construction update", "constructionupdate",
        # Samana brand fallback (Arabic/Persian captions often only carry these tags)
        "#samana", "samanasboshasgonecrazy", "samanas boss has gone crazy",
        "samanadevelopers",
        # generic project / development reveals
        "off-plan", "off plan", "off-plan properties", "new project",
        "presents", "we present", "introduces", "introduces:",
    ],
    "Investment": [
        "roi", "returns", "yield", "payment plan", "easy payment",
        "investment opportunity", "investor", "investment", "appreciation",
        "capital", "rental income", "passive income", "freehold",
        "golden visa", "residency", "smart investment", "investmentopportunity",
        "dubaiinvestments", "dubai investments",
        # Crypto / alternative payment as investment angle
        "cryptocurrency", "crypto payment", "accept cryptocurrency",
        "bitcoin payment", "accept crypto", "pay in crypto", "crypto real estate",
    ],
    "Event / Occasion": [
        "awards", "award", "ceremony", "gala", "summit", "conference", "expo",
        "cityscape", "gires", "gulf real estate", "exhibition", "panel",
        "anniversary", "milestone", "celebration", "celebrating",
        "open house", "openhouse", "groundbreaking ceremony", "ribbon cutting",
        "gulf business", "gbawards", "guinness world record", "guinness",
        "world record",
        # date-specific holidays
        "ramadan", "eid", "national day", "uae national",
        "christmas", "new year", "diwali",
        # Tournaments / corporate sport / community competitions
        "imtiaz champions league", "imtiazchampionsleague", "champions league",
        "championsleague", "bnw legends cup", "legends cup", "legendscup",
        "ipf dubai", "ipfdubai", "ipf trophy",
        # Corporate events / launches as occasions
        "hop events", "hopevents", "hop event", "soic2026", "soic 2026", "soic",
        # Philanthropy / honors
        "mohammed bin rashid al maktoum medal", "philanthropy medal",
        "medal for philanthropy", "humanitarian medal",
    ],
    "Real Estate Market": [
        "dubai real estate", "dubai property", "real estate market", "property market",
        "dubai market", "uae real estate", "property trends", "market report",
        "market update", "dubai growth", "dubai economy", "real estate insights",
        "off-plan market", "freehold zone", "dubai property news",
    ],
    "Business / Leadership": [
        "founder", "chairman", "ceo ", "ceo,", "ceo.", "leadership", "leaders",
        "vision", "mission", "founding", "entrepreneur", "entrepreneurship",
        "discipline", "strategy", "execution", "operations", "business",
        "interview", "interviewed", "podcast", "keynote",
        "consistency is", "every decision",
    ],
    "Press / Media Coverage": [
        "forbes", "entrepreneur middle east", "gulf news", "khaleej times",
        "the national", "mena entrepreneur", "arabian business",
        "featured in", "featured on", "as featured", "press release",
        "interview with", "coverage by", "magazine", "publication",
        "filmfare", "entrepreneurtvme", "yuvis",
        # Additional press handles / outlets
        "khaleejtimes", "khaleej_times", "mashable.me", "mashableme",
        "rannvijaysingha", "rannvijay", "thenational", "arabianbusiness",
        "businessbreakfast", "dubaieye",
    ],
    "Behind the Scenes / Team": [
        "behind the scenes", "bts", "behindthescenes", "our team", "the team",
        "office", "team building", "team day", "culture", "people of",
        "sales team", "sales gallery", "showroom", "meet our",
        "cso", "coo", "cmo", "cfo", "vp ", "vice president",
        # Team outings / bonding
        "team hit the lanes", "team bowling", "team night", "team outing",
        "team dinner", "company outing", "strikes spares", "bowling night",
        "regular day at", "just a regular day", "office life",
    ],
    "Motivational / Inspirational": [
        "mindset", "dream big", "never give up", "keep going", "believe",
        "rise and grind", "hustle", "grind", "perseverance",
        "inspired", "inspiration", "inspire", "motivation", "motivational",
        "passion", "purpose", "growth", "ambition", "drive ",
        "every step", "moving forward", "next chapter",
    ],
    "Partnership / Collaboration": [
        "x ", " × ", " x @", "in collaboration with", "collaborating",
        "partnered with", "partnership with", "proud to partner",
        "joining hands", "alongside @", "together with",
        "hrithikroshan", "celebrity", "ambassador", "endorser",
        "portuguese football federation", "portuguesefootball",
    ],
    "Cultural / Community": [
        # Music & live performance
        "concert", "live music", "performance", "musical", "performance by",
        "arijit singh", "arijitsinghlive", "sitar", "sitarformentalhealth",
        "rishab sharma", "musicunites", "concertvibes",
        # Festivals & cultural events
        "holi", "holiverse", "diwali", "festival", "navratri", "garba",
        "iftar", "ramadan iftar", "community event", "fan meet",
        # Religious / spiritual moments (distinct from corporate awards in Event/Occasion)
        "bageshwar", "bageshwar dham", "iambageshvardham", "blessing", "blessings",
        "divine presence", "spiritual", "religious", "satsang", "kirtan",
        "tradition", "traditional", "sacred",
        # Sports / community sport
        "cricket in dubai", "cricketindubai", "ipl",
        # Community organizing
        "community", "neighbourhood event", "fan", "fans",
        # A.R. Rahman / Pantheon Icon Series concerts (Kalpesh / Pantheon)
        "a. r. rahman", "a.r. rahman", "ar rahman", "arrahman", "arrahmanlive",
        "rahman live", "rahmanlive", "pantheon icon series", "pantheoniconseries",
        "pantheon iconic series", "pantheoniconicseries", "icon series",
        # Live shows / dance / cultural production
        "tandav", "kathak", "bharatanatyam", "classical dance",
        # Mindfulness / wellness through art (cultural overlap)
        "breathwork", "breath work", "mindfulness through music",
        "mindfulnessthroughmusic", "wellness through art", "wellnessthroughart",
        "music heals", "musicheals", "soulful evening", "soulfulevening",
        # Women / inclusion initiatives
        "she pioneers", "shepioneers", "women's day", "womens day", "womensday",
        "international women", "internationalwomensday", "iwd",
        "women in real estate", "women in business", "women leaders",
        # Children / philanthropy / community visits
        "al jalila", "aljalila", "children's hospital", "childrenshospital",
        "orphanage", "charity visit", "charityvisit",
        # National / civic ceremonies
        "republic day", "republicday", "77th republic", "independence day",
        "independenceday", "flag raising", "flagraising",
        # Devotional / spiritual gathering signals
        "devotees", "divine gathering", "divinegathering", "grateful hearts",
        "gratefulhearts", "prayerful", "company of the divine", "jaisi sangat",
        "sangat", "blessings of", "blessed evening", "sacred moment",
        "music moved", "hearts aligned", "atmosphere shifted",
    ],
    "Personal Storytelling": [
        # Memoir / life narrative cues
        "my journey", "my story", "looking back", "when i was",
        "when my father", "when my mother", "growing up", "childhood",
        "started with nothing", "humble beginnings", "from humble",
        "life taught me", "what i learned", "lessons learned", "lesson learned",
        "life lesson", "life lessons", "things i wish",
        # Reflection / personal opinion
        "in my opinion", "from my experience", "my take on", "my perspective",
        "personal note", "real talk", "honest truth", "i used to",
        # Bigg Boss / TV journey markers
        "bigg boss", "biggboss",
        # Storytelling viral signals
        "true story", "real story", "story time", "storytime",
        # Strong narrative opener patterns
        "passed away", "reality check", "you won't believe", "no one told me",
        "life lesson", "lifelessons", "viral",
        # Family / relational storytelling (Rizwan-style narrative posts)
        "my wife", "my mother", "my husband", "my father", "my son", "my daughter",
        "she said", "he said", "she told me", "he told me",
        "i once asked", "i asked my", "i told my",
        "they say she", "she does nothing", "people often ask",
        # Self-worth / introspection
        "self worth", "selfworth", "self-worth", "self respect", "selfrespect",
        "inner peace", "innerpeace", "find yourself", "knowing yourself",
        # Rizwan-style reflective aphorisms
        "life works", "life teaches", "life shows", "life gives",
        "not everything you see online", "online is reality", "what we see online",
        "overthink", "overanalyze", "unnecessary fear",
        "love is not about", "love is about", "what is needed",
        "the bond is", "the bond between", "without being told",
        "small lock", "small key", "small things matter",
        "responsible and avoid", "spreading unverified",
    ],
    "Lifestyle / Personal": [
        "family", "weekend", "vacation", "holiday", "gym", "fitness",
        "workout", "endurance", "marathon", "race", "training",
        "food", "dinner", "lunch", "travel", "trip", "explore",
        "personal", "weekend vibes", "blessed",
        # Travel-specific (was uncategorized: "San Francisco walk")
        "san francisco", "newyork", "london", "tokyo", "paris", "milan",
        "city walk", "city stroll", "exploring", "discovering",
        # Year-wrap / recap
        "2024 wrapup", "2025wrapup", "2026wrapup", "year wrap", "year wrapped",
        "year in review", "yearreview", "cheers to", "memories",
        # Ankur-style city walks / personal exploration
        "annamalai", "rannvijay", "city walks", "morning walk", "evening walk",
        "sunset walk", "downtown walk",
    ],
}
# Compile keyword lists once (lowercase)
THEME_PATTERNS = {t: [w.lower() for w in ws] for t, ws in THEMES.items()}

def classify_theme(caption, hashtags, mentions):
    """Returns (primary_theme, all_matched_themes_list, score_dict)."""
    text = (caption or "").lower() + " " + " ".join(hashtags or []).lower() + " " + " ".join(("@" + m for m in (mentions or []))).lower()
    scores = {}
    for theme, kws in THEME_PATTERNS.items():
        s = 0
        for kw in kws:
            if kw in text:
                s += 1
        if s > 0:
            scores[theme] = s
    if not scores:
        return ("Uncategorized", [], {})
    # Sort by (score DESC, theme order from THEMES — earlier = preferred on tie)
    theme_order = list(THEMES.keys())
    sorted_themes = sorted(scores.items(), key=lambda x: (-x[1], theme_order.index(x[0])))
    primary = sorted_themes[0][0]
    matched = [t for t, _ in sorted_themes]
    return (primary, matched, scores)

# ===================== Hook / CTA / Voice signals =====================
CTA_PATTERNS = {
    "DM":          ["dm us", "dm me", "dm for", "send us a dm", "slide into our dms", "drop a dm"],
    "Link in bio": ["link in bio", "link bio", "linkinbio", "bio link", "tap the link", "click the link in bio"],
    "Book now":    ["book now", "book your", "book a viewing", "book a tour", "schedule a viewing", "schedule a tour"],
    "Register":    ["register now", "register today", "register your interest", "sign up", "signup", "rsvp"],
    "WhatsApp":    ["whatsapp", "whats app", "wa.me", "+971", "call us", "call now", "call:", "contact us"],
    "Visit":       ["visit us", "visit our", "visit the", "come visit", "swing by"],
    "Inquire":     ["inquire now", "enquire now", "for more details", "for details", "for inquiries", "for enquiries", "reach out"],
    "Follow":      ["follow us", "follow @", "stay tuned", "stay connected"],
}
CTA_LIST = list(CTA_PATTERNS.keys())

FIRST_PERSON_TOKENS = (" i ", " i'm", " im ", " i've", " ive ", " i'd", " my ", " me ", " mine ", " myself ", " we ", " our ", " us ")

def classify_cta(caption):
    """Returns (has_cta_bool, cta_type_str_or_empty)."""
    if not caption: return (False, "")
    low = " " + caption.lower() + " "
    for cta, pats in CTA_PATTERNS.items():
        for p in pats:
            if p in low:
                return (True, cta)
    return (False, "")

def first_three_words(caption):
    """Returns first 3 words of caption, lowercased, stripped of punctuation."""
    if not caption: return ""
    import re as _re
    # Strip leading emojis/symbols
    words = _re.findall(r"[A-Za-z][A-Za-z0-9'-]*", caption)
    return " ".join(words[:3]).lower() if words else ""

def is_founder_voice(caption):
    """Heuristic: caption >180 chars AND contains first-person pronoun → founder-voice flagged."""
    if not caption or len(caption) < 180:
        return False
    low = " " + caption.lower() + " "
    return any(tok in low for tok in FIRST_PERSON_TOKENS)


# Pre-load follower counts from each profile.json so we can compute follower-based ER

# Pre-load follower counts from each profile.json so we can compute follower-based ER
PROFILE_FOLLOWERS = {}
for _seg_label, _seg_dir in SEGMENT_DIRS:
    _seg_path = os.path.join(BASE, _seg_dir)
    if not os.path.isdir(_seg_path):
        continue
    for _handle in os.listdir(_seg_path):
        _pp = os.path.join(_seg_path, _handle, "profile.json")
        if os.path.exists(_pp):
            try:
                with open(_pp, "r", encoding="utf-8") as _fh:
                    _d = json.load(_fh)
                # Accept both normalized ("followers") and raw Apify ("followersCount") field names
                PROFILE_FOLLOWERS[_handle.lower()] = int(_d.get("followers") or _d.get("followersCount") or 0)
            except Exception:
                pass

for segment, handle_folder, path in discover_files():
    known_accounts[segment].add(handle_folder)
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            short = (row.get("shortCode") or "").strip()
            url = (row.get("url") or "").strip()
            key = short or url
            if not key or key in seen:
                continue
            seen.add(key)

            owner = (row.get("ownerUsername") or "").strip().lower()
            is_own = owner == handle_folder.lower()

            ts = parse_ts(row.get("timestamp") or "")
            ptype = (row.get("type") or "").strip()
            ptype_prod = (row.get("productType") or "").strip()
            if ptype_prod == "clips":   content_type = "Reel"
            elif ptype == "Video":      content_type = "Video"
            elif ptype == "Sidecar":    content_type = "Carousel"
            elif ptype == "Image":      content_type = "Image"
            else: content_type = ptype or ptype_prod or "Other"

            hashtags = [row[f"hashtags/{i}"].strip().lower()
                        for i in range(20) if row.get(f"hashtags/{i}")]
            tagged = [row[f"taggedUsers/{i}/username"].strip().lower()
                      for i in range(30) if row.get(f"taggedUsers/{i}/username")]
            mentions = [row[f"mentions/{i}"].strip().lower()
                        for i in range(20) if row.get(f"mentions/{i}")]
            # Rich tagged-user records: capture account ID, verified flag, full name (for collaboration analysis)
            tagged_full = []
            for i in range(30):
                u = (row.get(f"taggedUsers/{i}/username") or "").strip().lower()
                if not u: continue
                tagged_full.append({
                    "u": u,
                    "id": (row.get(f"taggedUsers/{i}/id") or "").strip(),
                    "name": (row.get(f"taggedUsers/{i}/full_name") or "").strip(),
                    "verified": to_bool(row.get(f"taggedUsers/{i}/is_verified")),
                })
            # IG-native Collab posts (coauthorProducers) — strongest collaboration signal
            coauthors = []
            for i in range(8):
                cid = (row.get(f"coauthorProducers/{i}/id") or "").strip()
                cun = (row.get(f"coauthorProducers/{i}/username") or "").strip().lower()
                if cid or cun:
                    coauthors.append({"u": cun, "id": cid})
            # Owner ID (for account-id capture)
            owner_id = (row.get("ownerId") or "").strip()
            # Fallback: regex-parse @mentions from caption when mentions column is missing
            if not mentions:
                cap_text = (row.get("caption") or "")
                import re as _re
                mentions = list({m.lower() for m in _re.findall(r"@([A-Za-z0-9._]{2,30})", cap_text)})
            location_name = (row.get("locationName") or "").strip()
            is_pinned = to_bool(row.get("isPinned"))

            slides = 0
            for i in range(20):
                if row.get(f"childPosts/{i}/id") or row.get(f"childPosts/{i}/shortCode"):
                    slides = i + 1

            likes = to_int(row.get("likesCount"))
            comments = to_int(row.get("commentsCount"))
            views = to_int(row.get("videoViewCount")) or to_int(row.get("videoPlayCount"))
            duration = to_int(row.get("videoDuration"))
            # Apify returns -1 when likes are hidden by the IG user — treat as missing for analytics
            likes_valid = likes >= 0
            if not likes_valid:
                likes = 0

            caption = (row.get("caption") or "").strip()
            song = (row.get("musicInfo/song_name") or "").strip()
            artist = (row.get("musicInfo/artist_name") or "").strip()
            uo = row.get("musicInfo/uses_original_audio")
            uses_orig = to_bool(uo) if uo not in (None, "") else None

            display_url = (row.get("displayUrl") or "").strip()
            if not display_url:
                for i in range(8):
                    d = row.get(f"childPosts/{i}/displayUrl")
                    if d:
                        display_url = d.strip(); break

            engagement = (likes + comments) if likes_valid else None
            # Industry-standard ER uses followers as denominator. Falls back to None if followers unknown.
            acc_followers = PROFILE_FOLLOWERS.get(handle_folder.lower(), 0)
            er = (engagement / acc_followers) if (acc_followers > 0 and engagement is not None) else None
            view_er = (engagement / views) if (views > 0 and engagement is not None) else None  # view-based ER (kept for reach analytics)
            vlr = (likes / views) if (views > 0 and likes_valid) else None

            # Content-theme classification (caption + hashtags + mentions)
            theme, themes_all, _ = classify_theme(caption, hashtags, mentions)
            # LLM cache override (mid priority)
            if short and short in THEME_CACHE:
                cached = THEME_CACHE[short]
                if cached and cached != "Uncategorized":
                    theme = cached
                    if cached not in themes_all:
                        themes_all = [cached] + themes_all
            # Manual override (highest priority — wins over everything)
            if short and short in THEME_OVERRIDES:
                manual = THEME_OVERRIDES[short]
                if manual:
                    theme = manual
                    if manual not in themes_all:
                        themes_all = [manual] + themes_all

            has_cta, cta_type = classify_cta(caption)
            hook = first_three_words(caption)
            founder_voice = is_founder_voice(caption)
            records.append({
                "segment": segment,
                "account": handle_folder,
                "owner": owner,
                "isOwn": is_own,
                "shortCode": short,
                "url": url,
                "displayUrl": display_url,
                "timestamp": ts.isoformat() if ts else None,
                "ts_ms": int(ts.timestamp() * 1000) if ts else None,
                "type": content_type,
                "likes": likes,
                "comments": comments,
                "views": views,
                "duration": duration,
                "slides": slides,
                "hashtags": hashtags,
                "hashtagCount": len(hashtags),
                "tagged": tagged,
                "taggedFull": tagged_full,
                "coauthors": coauthors,
                "ownerId": owner_id,
                "mentions": mentions,
                "location": location_name,
                "isPinned": is_pinned,
                "caption": caption[:500],
                "capLen": len(caption),
                "song": song,
                "artist": artist,
                "usesOriginal": uses_orig,
                "likesValid": likes_valid,
                "engagement": engagement,
                "er": er,
                "viewER": view_er,
                "vlr": vlr,
                "theme": theme,
                "themes": themes_all,
                "hasCTA": has_cta,
                "ctaType": cta_type,
                "hook": hook,
                "founderVoice": founder_voice,
                "likelyBoosted": False,  # populated in account-level second pass below
            })
print(f"Total unique posts: {len(records)}")

# ===================== Likely-boosted second pass (account-level) =====================
# Heuristic: views >= median(views) + 3 * MAD(views) for that account's video content
# only applies to records where views > 0 (videos / reels); statics ignored
def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0: return 0
    if n % 2 == 1: return s[n//2]
    return (s[n//2 - 1] + s[n//2]) / 2

_by_acc_views = {}
for r in records:
    if r.get("isOwn") and (r.get("views") or 0) > 0:
        _by_acc_views.setdefault(r["account"], []).append(r["views"])

_boost_thresholds = {}
for acc, vs in _by_acc_views.items():
    med = _median(vs)
    mad = _median([abs(v - med) for v in vs])
    # require both: at least 3xMAD above median AND at least 2.5x median absolute
    threshold = max(med + 3 * mad, med * 2.5)
    _boost_thresholds[acc] = threshold

boosted_count = 0
for r in records:
    if r.get("isOwn") and (r.get("views") or 0) > 0:
        thresh = _boost_thresholds.get(r["account"])
        if thresh and r["views"] >= thresh:
            r["likelyBoosted"] = True
            boosted_count += 1
print(f"Likely-boosted (view anomaly) flagged: {boosted_count} posts across {len(_boost_thresholds)} accounts")


# Build the catalog of accounts per segment and assign palette colors
accounts_catalog = []
for seg_label, seg_dir in SEGMENT_DIRS:
    for handle in sorted(known_accounts.get(seg_label, [])):
        own_count = sum(1 for r in records if r["segment"]==seg_label and r["account"]==handle and r["isOwn"])
        total_count = sum(1 for r in records if r["segment"]==seg_label and r["account"]==handle)

        # Profile metadata + avatar (accept jpg/jpeg/png/webp)
        prof_path = os.path.join(BASE, seg_dir, handle, "profile.json")
        prof = {}
        if os.path.exists(prof_path):
            try:
                with open(prof_path, "r", encoding="utf-8") as fh:
                    prof = json.load(fh)
            except Exception:
                prof = {}
        local_avatar = None
        for ext in ("jpg", "jpeg", "png", "webp", "svg"):
            avatar_path = os.path.join(BASE, seg_dir, handle, f"avatar.{ext}")
            if os.path.exists(avatar_path) and os.path.getsize(avatar_path) > 100:
                local_avatar = f"{seg_dir}/{handle}/avatar.{ext}"
                break
        accounts_catalog.append({
            "segment": seg_label,
            "handle": handle,
            "color": get_deterministic_color(handle),
            "own": own_count,
            "total": total_count,
            "fullName": prof.get("fullName") or handle,
            "biography": prof.get("biography") or "",
            # Accept both normalized and raw Apify field names
            "followers": prof.get("followers") or prof.get("followersCount") or 0,
            "following": prof.get("following") or prof.get("followsCount") or 0,
            "postsCount": prof.get("postsCount") or 0,
            "verified": prof.get("verified") or False,
            "category": prof.get("category") or prof.get("businessCategoryName") or "",
            "externalUrl": prof.get("externalUrl") or "",
            "avatarLocal": local_avatar,
            "avatarRemote": prof.get("profilePicUrl") or "",
            # Derive firstPostDate from earliest own-post timestamp if missing in profile
            "firstPostDate": prof.get("firstPostDate") or (
                min((r["timestamp"] for r in records
                     if r["segment"]==seg_label and r["account"]==handle and r["isOwn"] and r.get("timestamp")),
                    default="")
            ),
        })
for a in accounts_catalog:
    print(f"  [{a['segment']}] @{a['handle']}: {a['own']} own / {a['total']} total")

# ---------- HTML ----------
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Competitor Intelligence — Multi-Segment Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-chart-matrix@2.0.1/dist/chartjs-chart-matrix.min.js"></script>
<script>window.addEventListener('error',e=>{var d=document.createElement('pre');d.style.cssText='color:#ff7a7a;padding:16px;white-space:pre-wrap;font:12px monospace;background:#1a0f12;border:1px solid #ff7a7a';d.textContent='JS error: '+e.message+'\nat '+(e.filename||'')+':'+(e.lineno||'');document.body.prepend(d);});</script>
<style>
:root{--bg:#0a0e17;--card:#141b2b;--card2:#1a2238;--ink:#e8eef9;--mut:#8895ad;--dim:#5a6783;--ok:#46d3a0;--warn:#ffb454;--bad:#ff6b8a;--bd:#1f2a40;--sh:0 4px 20px rgba(0,0,0,.3)}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#0a0e17,#0c1120);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;min-height:100vh}
header{padding:24px 32px 16px;border-bottom:1px solid var(--bd);background:rgba(10,14,23,.85);backdrop-filter:blur(12px);position:sticky;top:0;z-index:30}
header .row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px}
h1{margin:0;font-size:30px;font-weight:800;letter-spacing:-.02em;cursor:pointer;user-select:none;display:inline-block;transition:opacity .15s,transform .15s}
h1:hover{opacity:.88;transform:translateX(-2px)}
h1:active{transform:translateX(-1px) scale(.99)}
h1 .accent{background:linear-gradient(90deg,#5b9cff,#ff7ab6);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--mut);font-size:12px;margin-top:4px}
.seg-switcher{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;align-items:center}
.seg-btn{padding:8px 18px;border-radius:10px;background:var(--card);border:1px solid var(--bd);cursor:pointer;font:600 13px/1 inherit;color:var(--mut);transition:.15s;display:flex;align-items:center;gap:8px}
.seg-btn:hover{color:var(--ink);border-color:#2d3a5a}
.seg-btn.active{background:linear-gradient(90deg,#5b9cff,#7ab0ff);color:#001022;border-color:transparent;box-shadow:0 4px 14px rgba(91,156,255,.3)}
.seg-btn .ct{font-weight:500;opacity:.75;font-size:11px}
.acc-chips{display:flex;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.acc-chip{display:inline-flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--bd);padding:5px 12px 5px 5px;border-radius:999px}
.acc-chip .av{width:26px;height:26px;border-radius:50%;background:#1d2940;display:inline-block;flex-shrink:0;overflow:hidden;border:2px solid transparent}
.acc-chip .av img{width:100%;height:100%;object-fit:cover;display:block}
.acc-chip .av.placeholder{display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11px}
.acc-chip strong{color:var(--ink)}
.verified-badge{color:#5b9cff;font-size:13px;margin-left:4px}
.profile-card{display:flex;gap:14px;align-items:center;padding:14px}
.profile-card .av{width:64px;height:64px;border-radius:50%;background:#1d2940;flex-shrink:0;overflow:hidden;border:2px solid var(--bd);position:relative}
.profile-card .av img{width:100%;height:100%;object-fit:cover}
.profile-card .av.placeholder{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:24px}
.profile-card .info{flex:1;min-width:0}
.profile-card .info .name{font-size:16px;font-weight:700;display:flex;align-items:center;gap:6px}
.profile-card .info .handle{color:#b8c5dc;font-size:13px;margin-top:3px;font-weight:500}
.profile-card .info .bio{font-size:14px;color:#e8eef9;margin-top:8px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;font-weight:400}
.profile-card .stats{display:flex;gap:14px;font-size:11px;color:var(--mut);margin-top:8px}
.profile-card .stats b{color:var(--ink);font-size:13px;display:block}
.acc-avatar{position:relative;width:26px;height:26px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:700;overflow:hidden;font-style:normal;vertical-align:middle;flex-shrink:0;background:#1d2940;font-size:11px}
.acc-avatar img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;border-radius:50%}
.acc-chip .acc-avatar,.scorecard .acc-avatar{width:26px;height:26px;font-size:11px}
.profile-card .acc-avatar{width:64px;height:64px;font-size:24px;border:2px solid var(--bd);background:#fff}
.profile-card .acc-avatar img{object-fit:contain;padding:6%;background:#fff}
.overview-card .acc-avatar{width:72px;height:72px;font-size:26px;border:3px solid var(--accent,#5b9cff);background:#fff}
.overview-card .acc-avatar img{object-fit:contain;padding:8%;background:#fff}
.pick-chip .acc-avatar{width:24px;height:24px;font-size:10px}
/* Founder avatars (real photos) use cover, enterprises (logos) get contain via above rules */
.founder-avatar .acc-avatar img{object-fit:cover !important;padding:0 !important;background:transparent !important}
/* Overview grid */
.overview-card{cursor:pointer;background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--bd);border-radius:16px;padding:20px;display:flex;flex-direction:column;gap:14px;transition:.2s;position:relative;overflow:hidden;min-height:340px;height:100%}
.overview-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent,#5b9cff);opacity:.8}
.overview-card:hover{transform:translateY(-3px);border-color:var(--accent,#5b9cff);box-shadow:0 12px 30px rgba(0,0,0,.4)}
.overview-card .head{display:flex;gap:14px;align-items:center;min-height:72px}
.overview-card .head .name{font-size:17px;font-weight:700;display:flex;align-items:center;gap:6px;line-height:1.2}
.overview-card .head .handle{font-size:13px;color:#b8c5dc;margin-top:5px;font-weight:500}
.overview-card .bio{font-size:13px;color:#e8eef9;line-height:1.55;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;height:40px;font-weight:400}
.overview-card .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:auto}
.overview-card .kpis .tile{background:rgba(0,0,0,.25);border:1px solid var(--bd);border-radius:10px;padding:10px 4px;text-align:center;min-width:0}
.overview-card .kpis .tile .v{font-size:14px;font-weight:700;letter-spacing:-.01em;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.overview-card .kpis .tile .l{font-size:9px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;margin-top:4px;line-height:1.2}
.overview-card .open-link{font-size:11px;color:var(--accent,#5b9cff);font-weight:600;letter-spacing:.05em;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;margin-top:4px}
.overview-card .open-link .arr{font-size:14px}
@media (max-width:1100px){.overview-card{min-height:300px}.overview-card .kpis{grid-template-columns:repeat(3,1fr)}.overview-card .kpis .tile:nth-child(n+4){display:none}}
.breadcrumb{grid-column:span 12;display:flex;align-items:center;gap:12px;padding:8px 4px;font-size:13px}
.breadcrumb a{cursor:pointer;color:var(--mut);font-weight:600}
.breadcrumb a:hover{color:var(--ink);text-decoration:none}
.breadcrumb .sep{color:var(--dim)}
.breadcrumb .curr{color:var(--ink);font-weight:700}
/* Compare battlecards (per selected account) */
.battlecard{padding:14px;display:flex;flex-direction:column;gap:10px;height:100%}
.battlecard .top{display:flex;align-items:center;gap:10px}
.battlecard .top .acc-avatar{width:40px;height:40px;font-size:16px;border:2px solid var(--accent)}
.battlecard .name{font-weight:700;font-size:14px;line-height:1.2}
.battlecard .handle{font-size:11px;color:var(--mut)}
.battlecard .rows{display:grid;grid-template-columns:1fr;gap:6px;margin-top:4px}
.battlecard .row{display:flex;justify-content:space-between;font-size:12px;padding:6px 8px;background:rgba(0,0,0,.2);border-radius:6px}
.battlecard .row .l{color:var(--mut);text-transform:uppercase;font-size:10px;letter-spacing:.06em;font-weight:600}
.battlecard .row .v{font-weight:700;font-variant-numeric:tabular-nums}
/* Metric selector */
.metric-bar{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;align-items:center}
.metric-bar .lbl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;font-weight:700;margin-right:6px}
.metric-btn{padding:5px 12px;border-radius:999px;background:var(--bd);cursor:pointer;border:1px solid transparent;font:600 11px/1 inherit;color:var(--mut);transition:.15s}
.metric-btn:hover{color:var(--ink)}
.metric-btn.on{background:linear-gradient(90deg,#5b9cff,#7ab0ff);color:#001022}
/* Compare picker */
.pick-bar{grid-column:span 12;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px;display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.pick-bar .lbl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;font-weight:700;margin-right:6px}
.pick-chip{display:inline-flex;align-items:center;gap:6px;background:var(--bd);border:1px solid transparent;padding:5px 12px 5px 5px;border-radius:999px;cursor:pointer;font-size:12px;color:var(--mut);transition:.15s}
.pick-chip:hover{color:var(--ink)}
.pick-chip.on{background:rgba(91,156,255,.15);border-color:var(--accent,#5b9cff);color:var(--ink)}
.pick-chip .av{width:24px;height:24px;border-radius:50%;background:#1d2940;overflow:hidden;display:inline-block;border:1px solid transparent}
.pick-chip .av img{width:100%;height:100%;object-fit:cover}
.pick-chip .av.placeholder{display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff}
.pick-chip .seg{font-size:9px;text-transform:uppercase;letter-spacing:.06em;opacity:.65;margin-left:4px}
.pick-bar .pick-actions{margin-left:auto;display:flex;gap:6px}
.pick-bar button.act{background:var(--bd);border:none;color:var(--ink);padding:5px 12px;border-radius:8px;font:600 11px/1 inherit;cursor:pointer}
.pick-bar button.act:hover{background:#2a3a5a}
/* Floating add-account button */
.fab{position:fixed;bottom:24px;right:24px;width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,#5b9cff,#ff7ab6);color:#001022;font-size:28px;font-weight:700;border:none;cursor:pointer;box-shadow:0 8px 24px rgba(91,156,255,.5);z-index:50;transition:.2s}
.fab:hover{transform:scale(1.08);box-shadow:0 12px 28px rgba(91,156,255,.7)}
.modal-bg{position:fixed;inset:0;background:rgba(5,8,15,.75);backdrop-filter:blur(6px);z-index:100;display:flex;align-items:center;justify-content:center;padding:20px}
.modal-bg.hidden{display:none}
.modal{background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--bd);border-radius:16px;padding:24px;width:100%;max-width:520px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.modal h2{margin:0 0 4px;font-size:18px}
.modal .sub{color:var(--mut);font-size:12px;margin-bottom:18px}
.modal label{display:block;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;font-weight:700;margin-bottom:6px;margin-top:14px}
.modal input[type=text],.modal select{width:100%;background:#0e1320;border:1px solid var(--bd);color:var(--ink);padding:10px 12px;border-radius:8px;font:14px/1 inherit}
.modal input[type=text]:focus{outline:none;border-color:#5b9cff}
.modal .seg-pick{display:flex;gap:8px;margin-top:4px}
.modal .seg-pick label{flex:1;cursor:pointer;text-align:center;background:#0e1320;border:1px solid var(--bd);padding:10px;border-radius:10px;font-size:13px;color:var(--ink);text-transform:none;letter-spacing:0;font-weight:600;margin:0}
.modal .seg-pick input{display:none}
.modal .seg-pick input:checked + span{color:#001022}
.modal .seg-pick label:has(input:checked){background:linear-gradient(135deg,#5b9cff,#7ab0ff);border-color:transparent;color:#001022}
.modal .opts{display:flex;gap:14px;margin-top:8px;font-size:13px}
.modal .opts label{display:inline-flex;align-items:center;gap:6px;text-transform:none;letter-spacing:0;font-weight:500;font-size:13px;color:var(--ink);margin:0}
.modal .actions{margin-top:20px;display:flex;gap:10px;justify-content:flex-end}
.modal button{padding:9px 18px;border-radius:8px;font:600 13px/1 inherit;cursor:pointer;border:none}
.modal button.cancel{background:var(--bd);color:var(--ink)}
.modal button.go{background:linear-gradient(135deg,#5b9cff,#7ab0ff);color:#001022}
.modal button:disabled{opacity:.5;cursor:wait}
.modal .log{margin-top:16px;background:#0a0e17;border:1px solid var(--bd);border-radius:8px;padding:12px;font-family:Menlo,Consolas,monospace;font-size:11px;color:var(--mut);max-height:240px;overflow-y:auto;line-height:1.5;display:none;white-space:pre-wrap}
.modal .log.show{display:block}
.modal .log .ok{color:#46d3a0}
.modal .log .err{color:#ff6b8a}
.modal .warn{margin-top:10px;padding:10px 12px;background:rgba(255,180,84,.1);border-left:3px solid #ffb454;border-radius:6px;font-size:12px;color:#ffd9a0}
main{padding:20px 32px;display:grid;grid-template-columns:repeat(12,1fr);gap:16px;max-width:1620px;margin:0 auto}
.card{background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--bd);border-radius:14px;padding:16px;box-shadow:var(--sh)}
.card h3{margin:0 0 12px;font-size:12px;color:var(--mut);font-weight:600;text-transform:uppercase;letter-spacing:.08em;display:flex;justify-content:space-between;align-items:center}
.card h3 .tag{font-size:10px;background:var(--bd);color:var(--mut);padding:2px 8px;border-radius:999px;text-transform:none;letter-spacing:0}
.kpi .v{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.1}
.kpi .d{font-size:11px;color:var(--mut);margin-top:6px;line-height:1.4}
.span-2{grid-column:span 2}.span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-5{grid-column:span 5}.span-6{grid-column:span 6}.span-7{grid-column:span 7}.span-8{grid-column:span 8}.span-9{grid-column:span 9}.span-12{grid-column:span 12}
@media (max-width:1200px){.span-2,.span-3,.span-4{grid-column:span 6}.span-5,.span-6,.span-7,.span-8,.span-9{grid-column:span 12}}
.chart-wrap{position:relative;height:280px}
.chart-wrap.sm{height:180px}.chart-wrap.md{height:240px}.chart-wrap.lg{height:340px}
table{width:100%;border-collapse:collapse;font-size:13px}
table.tag-matrix{font-size:12px}
table.tag-matrix th,table.tag-matrix td{padding:8px 10px;vertical-align:middle}
table.tag-matrix tbody tr:hover td{background:rgba(91,156,255,.06)}
table.tag-matrix tbody tr:hover td[style*="sticky"]{background:#1d2940 !important}
th,td{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.06em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.thumb{width:48px;height:48px;border-radius:8px;object-fit:cover;background:var(--bd);display:block}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:10px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
.bar{height:6px;border-radius:6px;background:var(--bd);overflow:hidden;min-width:60px}
.bar>span{display:block;height:100%}
.tabs{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.tab{padding:5px 12px;border-radius:999px;background:var(--bd);cursor:pointer;border:1px solid transparent;font:600 11px/1 inherit;color:var(--mut);transition:.15s}
.tab:hover{color:var(--ink)}
.tab.active{background:linear-gradient(90deg,#5b9cff,#7ab0ff);color:#001022}
a{color:#5b9cff;text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--mut);font-size:12px}
.insight{padding:12px 14px;background:rgba(91,156,255,.06);border-left:3px solid #5b9cff;border-radius:8px;margin-bottom:10px;font-size:13px;line-height:1.55}
.insight strong{color:var(--ink)}
.insight .label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin-right:8px;font-weight:700}
.hash-chip{display:inline-block;padding:3px 9px;border-radius:999px;background:var(--bd);font-size:11px;margin:2px}
.section-title{grid-column:span 12;margin-top:6px;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.1em;font-weight:600;border-bottom:1px solid var(--bd);padding-bottom:6px}
.empty{padding:48px;text-align:center;color:var(--mut);grid-column:span 12;background:var(--card);border-radius:12px;border:1px dashed var(--bd)}
.empty code{background:var(--bd);padding:2px 6px;border-radius:4px;font-size:12px;color:var(--ink)}
.scorecard{display:grid;grid-template-columns:1fr;gap:8px;padding:6px 0}
.scorecard .row{display:grid;grid-template-columns:120px 1fr 60px;gap:10px;align-items:center;font-size:13px}
.scorecard .row .name{font-weight:600;display:flex;align-items:center;gap:8px}
.scorecard .row .name i{display:inline-block;width:8px;height:8px;border-radius:50%}
.scorecard .row .barwrap{height:8px;background:var(--bd);border-radius:6px;overflow:hidden}
.scorecard .row .barwrap>span{display:block;height:100%}
.scorecard .row .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.scorecard h4{margin:14px 0 6px;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em}

/* --- New panels: archetype heatmap, gap matrix, so-what, momentum, flywheel, footer --- */
.archetype-grid{display:grid;gap:2px;background:var(--bd);padding:2px;border-radius:8px}
.archetype-cell{padding:8px 6px;font-size:11px;text-align:center;color:#fff;font-weight:600;border-radius:3px;cursor:default;line-height:1.3}
.archetype-cell.empty{background:#1a2238;color:var(--dim);font-weight:400}
.archetype-label{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;padding:6px 4px}

.gap-cell{padding:7px 5px;font-size:11px;text-align:center;font-variant-numeric:tabular-nums;border-radius:3px;font-weight:600}
.gap-cell.zero{color:var(--dim);font-weight:400}

.sowhat{padding:18px 20px;background:linear-gradient(135deg,rgba(91,156,255,.08),rgba(255,122,182,.06));border:1px solid rgba(91,156,255,.25);border-radius:12px}
.sowhat .lead{font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}
.sowhat .reco{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--bd);font-size:13.5px;line-height:1.55}
.sowhat .reco:first-of-type{border-top:none}
.sowhat .reco .icon{flex:0 0 24px;font-size:16px}
.sowhat .reco strong{color:var(--ink)}

.flywheel-row{display:grid;grid-template-columns:1fr auto 1fr;gap:18px;align-items:stretch;padding:16px;border:1px solid var(--bd);border-radius:12px;background:var(--card2);margin-bottom:12px}
.flywheel-side{display:flex;flex-direction:column;gap:6px}
.flywheel-side .name{font-weight:700;font-size:14px}
.flywheel-side .handle{color:var(--mut);font-size:11px}
.flywheel-side .kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px}
.flywheel-side .kpis .tile{background:rgba(255,255,255,.03);border-radius:6px;padding:6px 8px}
.flywheel-side .kpis .v{font-weight:700;font-size:15px}
.flywheel-side .kpis .l{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.flywheel-arrow{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:0 8px;border-left:1px dashed var(--bd);border-right:1px dashed var(--bd)}
.flywheel-arrow .gap{font-weight:700;font-size:22px;background:linear-gradient(90deg,#5b9cff,#ff7ab6);-webkit-background-clip:text;background-clip:text;color:transparent}
.flywheel-arrow .lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;text-align:center}

.momentum-row{display:flex;align-items:center;gap:10px;padding:6px 4px}
.momentum-arrow{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.momentum-arrow.up{color:var(--ok)}
.momentum-arrow.down{color:var(--bad)}
.momentum-arrow.flat{color:var(--mut)}

.dash-footer{margin-top:32px;padding:18px 22px;border-top:1px solid var(--bd);background:rgba(0,0,0,.18);font-size:11.5px;color:var(--mut);display:flex;flex-wrap:wrap;gap:24px;line-height:1.6}
.dash-footer .col strong{color:var(--ink);font-weight:600}
.dash-footer .stale{color:var(--warn)}

/* Print / PDF styles */
@media print {
  header{position:static!important;backdrop-filter:none!important;background:#fff!important;color:#000!important;border-bottom:2px solid #000!important;page-break-after:avoid}
  header h1, header .sub, header .seg-switcher, #btn-print, .fab, .modal-bg{display:none!important}
  header .row::before{content:"Competitor Intelligence — Instagram (PDF snapshot)";font-size:20px;font-weight:800;color:#000}
  body{background:#fff!important;color:#111!important;font-size:11px}
  main{padding:8px!important}
  .card,.battlecard,.overview-card,.flywheel-row,.sowhat{background:#fff!important;border:1px solid #888!important;color:#111!important;box-shadow:none!important;page-break-inside:avoid}
  .card h3,.section-title,.tile .v,.kpis .v{color:#000!important}
  .muted,.l,.lbl,.handle,.bio,.dash-footer{color:#555!important}
  .pill{border:1px solid #999;background:#eee!important;color:#222!important}
  canvas{max-height:280px!important}
  .tabs,.metric-bar,.metric-btn,.seg-switcher,.fab,.modal-bg,#btn-print{display:none!important}
  .chart-wrap{max-height:280px!important}
  .chart-wrap.lg{max-height:340px!important}
  table{font-size:10px}
  a{color:#0050cc!important;text-decoration:none}
  .section-title{break-before:auto;break-after:avoid;page-break-after:avoid}
}
</style>
</head>
<body>
<header>
  <div class="row">
    <div>
      <h1 id="home-link" title="Back to Founder overview"><span class="accent">Competitor Intelligence</span> — Instagram</h1>
      <div class="sub" id="datespan"></div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <button id="btn-print" title="Print / Save as PDF (Ctrl/Cmd+P)" style="background:rgba(91,156,255,.12);border:1px solid rgba(91,156,255,.4);color:#5b9cff;padding:8px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;letter-spacing:.04em">📄 Snapshot PDF</button>
      <div class="seg-switcher" id="seg-switcher"></div>
    </div>
  </div>
</header>
<main id="root"></main>
<footer class="dash-footer" id="dash-footer"></footer>
<button class="fab" id="fab" title="Add new account via Apify">＋</button>
<div class="modal-bg hidden" id="modal">
  <div class="modal">
    <h2>Add account via Apify</h2>
    <div class="sub">Scrapes posts + reels + profile, saves CSVs, rebuilds the dashboard. Requires <code>dashboard_server.py</code> running with <code>APIFY_TOKEN</code> set.</div>
    <div id="server-warn" class="warn" style="display:none">⚠ This dashboard is running from a static file. Start <code>python dashboard_server.py</code> and open <code>http://localhost:8765</code> to enable scraping.</div>
    <label>Instagram handle</label>
    <input type="text" id="m-handle" placeholder="e.g. rizwan.sajan (no @, no URL)" autocomplete="off"/>
    <label>Segment</label>
    <div class="seg-pick">
      <label><input type="radio" name="m-seg" value="Founder" checked/><span>👤 Founder</span></label>
      <label><input type="radio" name="m-seg" value="Enterprise"/><span>🏢 Enterprise</span></label>
    </div>
    <label>Include</label>
    <div class="opts">
      <label><input type="checkbox" id="m-posts" checked/> Posts</label>
      <label><input type="checkbox" id="m-reels" checked/> Reels</label>
      <label><input type="checkbox" id="m-profile" checked/> Profile + avatar</label>
    </div>
    <div class="log" id="m-log"></div>
    <div class="actions">
      <button class="cancel" id="m-cancel">Cancel</button>
      <button class="go" id="m-go">Scrape</button>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
const ACCOUNTS = __ACCOUNTS__;
const PALETTE  = __PALETTE__;
const META     = __META__;
let CURRENT_SEG = ACCOUNTS[0]?.segment || 'Founder';
let CURRENT_ACCOUNT = null;            // null = overview, handle string = drill-down
let COMPARE_PICK = ACCOUNTS.map(a=>a.handle);  // accounts selected in Comparison view
let COMPARE_METRIC = 'engagement';      // metric used for big bar race chart

// ---------- helpers ----------
Chart.defaults.color = '#8895ad';
Chart.defaults.borderColor = '#1f2a40';
Chart.defaults.font.family = '-apple-system,Segoe UI,Roboto,sans-serif';
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.boxHeight = 10;

// UAE locale constants — Gulf Standard Time = UTC+4, AED currency.
// Adding GST_OFFSET_MS to a UTC ms timestamp lets you read getUTCHours/getUTCDay
// and get the Dubai-local hour / day-of-week directly.
const GST_OFFSET_MS = 4 * 3600 * 1000;
const fmt   = n => n==null||isNaN(n)?'—':n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(Math.round(n));
const fmtPc = n => n==null||isNaN(n)?'—':(n*100).toFixed(1)+'%';
const avg   = (arr,k)=>{ const valid=arr.filter(p=>p[k]!=null); return valid.length?valid.reduce((s,p)=>s+p[k],0)/valid.length:0; };
const med   = arr=>{ const valid=arr.filter(x=>x!=null); if(!valid.length) return 0; const s=[...valid].sort((a,b)=>a-b); const m=s.length>>1; return s.length%2?s[m]:(s[m-1]+s[m])/2; };
function shade(hex,pct){ const n=parseInt(hex.slice(1),16); const r=(n>>16)&255,g=(n>>8)&255,b=n&255; const f=(x)=>Math.max(0,Math.min(255,Math.round(x+(pct<0?x:255-x)*pct))); return `rgb(${f(r)},${f(g)},${f(b)})`; }
function rgba(hex,a){ const n=parseInt(hex.slice(1),16); return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`; }
function escHtml(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// Avatar helper — initial sits in the wrapper as default; image overlays.
// On image error the img removes itself, the initial shows through. No HTML escaping shenanigans.
function avatarHTML(a){
  const initial = escHtml((a.fullName||a.handle||'?').replace('@','')[0].toUpperCase());
  const url = a.avatarLocal || a.avatarRemote || '';
  const bg = `background:${a.color}`;
  const img = url ? `<img src="${escHtml(url)}" referrerpolicy="no-referrer" onerror="this.remove()" alt=""/>` : '';
  return `<span class="acc-avatar" style="${bg}">${initial}${img}</span>`;
}

const isComparison = () => CURRENT_SEG === 'Comparison';
const overviewMode = () => !isComparison() && !CURRENT_ACCOUNT;

const segAccounts = () => {
  if(isComparison()) return ACCOUNTS.filter(a=>COMPARE_PICK.includes(a.handle));
  const inSeg = ACCOUNTS.filter(a=>a.segment===CURRENT_SEG);
  return CURRENT_ACCOUNT ? inSeg.filter(a=>a.handle===CURRENT_ACCOUNT) : inSeg;
};
const segData = () => {
  if(isComparison()) return DATA.filter(p=>COMPARE_PICK.includes(p.account));
  if(CURRENT_ACCOUNT) return DATA.filter(p=>p.account===CURRENT_ACCOUNT);
  return DATA.filter(p=>p.segment===CURRENT_SEG);
};
const segOwn   = () => segData().filter(p=>p.isOwn);
const ownByAcc = h => segData().filter(p=>p.isOwn && p.account===h);
const colorOf  = h => (segAccounts().find(a=>a.handle===h)?.color || ACCOUNTS.find(a=>a.handle===h)?.color || '#888');

// ---------- header date span ----------
{
  const ts = DATA.map(p=>p.ts_ms).filter(Boolean);
  if(ts.length){
    const min=new Date(Math.min(...ts)), max=new Date(Math.max(...ts));
    document.getElementById('datespan').textContent = `${ACCOUNTS.length} account(s) · ${DATA.length} posts · ${min.toISOString().slice(0,10)} → ${max.toISOString().slice(0,10)} · generated __GEN__`;
  } else {
    document.getElementById('datespan').textContent = 'No data found — run the ig-intel-fetcher agent to load data · generated __GEN__';
  }
}

// ---------- click title → home ----------
document.getElementById('home-link').addEventListener('click',()=>{
  CURRENT_SEG = ACCOUNTS.find(a=>a.segment==='Founder') ? 'Founder' : (ACCOUNTS[0]?.segment || 'Founder');
  CURRENT_ACCOUNT = null;
  COMPARE_PICK = ACCOUNTS.map(a=>a.handle);
  document.querySelectorAll('.seg-btn').forEach(b=>b.classList.toggle('active', b.dataset.seg===CURRENT_SEG));
  render();
  window.scrollTo({top:0,behavior:'smooth'});
});

// ---------- segment switcher ----------
{
  const segs = [...new Set(ACCOUNTS.map(a=>a.segment))];
  if(!segs.length){ segs.push('Founder','Enterprise'); }
  if(segs.length>=2 && !segs.includes('Comparison')) segs.push('Comparison');
  const html = segs.map(s=>{
    if(s==='Comparison'){
      return `<button class="seg-btn ${s===CURRENT_SEG?'active':''}" data-seg="${s}">⚖ Comparison <span class="ct">cross-segment</span></button>`;
    }
    const accs = ACCOUNTS.filter(a=>a.segment===s);
    const own = accs.reduce((x,a)=>x+a.own,0);
    return `<button class="seg-btn ${s===CURRENT_SEG?'active':''}" data-seg="${s}">${s} <span class="ct">${accs.length} acc · ${own} posts</span></button>`;
  }).join('');
  const wrap = document.getElementById('seg-switcher');
  wrap.innerHTML = html;
  wrap.addEventListener('click',e=>{
    const b=e.target.closest('.seg-btn'); if(!b) return;
    CURRENT_SEG = b.dataset.seg;
    CURRENT_ACCOUNT = null;
    wrap.querySelectorAll('.seg-btn').forEach(x=>x.classList.toggle('active',x===b));
    render();
  });
}

// ---------- segment-scoped date-range banner ----------
function dataRangeFor(scopeFn){
  const posts = DATA.filter(scopeFn);
  const ts = posts.map(p=>p.ts_ms).filter(Boolean);
  if(!ts.length) return null;
  return {min:new Date(Math.min(...ts)), max:new Date(Math.max(...ts)), count:posts.length};
}
function updateHeaderDateRange(){
  const el = document.getElementById('datespan');
  const totalAccs = ACCOUNTS.length;
  let scopeLabel, r;
  if(isComparison()){
    scopeLabel = `${COMPARE_PICK.length} compared`;
    r = dataRangeFor(p=>COMPARE_PICK.includes(p.account));
  } else if(CURRENT_ACCOUNT){
    scopeLabel = '@'+CURRENT_ACCOUNT;
    r = dataRangeFor(p=>p.account===CURRENT_ACCOUNT);
  } else {
    const segAccs = ACCOUNTS.filter(a=>a.segment===CURRENT_SEG);
    scopeLabel = `${CURRENT_SEG} · ${segAccs.length} acc`;
    r = dataRangeFor(p=>p.segment===CURRENT_SEG);
  }
  if(r){
    el.textContent = `${scopeLabel} · ${r.count} posts · ${r.min.toISOString().slice(0,10)} → ${r.max.toISOString().slice(0,10)} · generated __GEN__ · total tracked ${totalAccs}`;
  } else {
    el.textContent = `${scopeLabel} · no posts in this scope · generated __GEN__`;
  }
}

// ---------- main render ----------
function render(){
  const root = document.getElementById('root');
  updateHeaderDateRange();

  // Overview mode (segment landing) — clickable account cards with 5 KPI tiles
  if(overviewMode()){
    const segAccs = ACCOUNTS.filter(a=>a.segment===CURRENT_SEG);
    if(!segAccs.length){
      root.innerHTML = `<div class="empty"><h3 style="color:#e8eef9;font-size:18px;margin:0 0 8px">No accounts in "${CURRENT_SEG}" yet</h3>
        <p>Drop CSVs under <code>${CURRENT_SEG}/&lt;handle&gt;/*.csv</code> then run <code>python build_dashboard.py</code>,<br/>or invoke the <code>ig-intel-fetcher</code> agent to pull from Apify.</p></div>`;
      return;
    }
    root.innerHTML = renderOverview(segAccs);
    wireOverviewClicks();
    return;
  }

  // Comparison mode — chart-first layout
  if(isComparison()){
    if(!COMPARE_PICK.length){
      root.innerHTML = `${renderPicker()}<div class="empty">Pick at least one account above to compare.</div>`;
      wirePickerClicks();
      return;
    }
    const accs = segAccounts();
    root.innerHTML = renderPicker() + renderComparison(accs);
    wirePickerClicks();
    wireMetricClicks();
    drawComparison(accs);
    return;
  }

  // Individual account drill-down
  const accs = segAccounts();
  if(!accs.length){
    root.innerHTML = `<div class="empty">No data for @${CURRENT_ACCOUNT}.</div>`;
    return;
  }
  root.innerHTML = renderBreadcrumb() + buildLayout(accs);
  wireBackClick();
  drawAll(accs);
}

// ---------- overview mode ----------
function overviewKPIs(a){
  const own = DATA.filter(p=>p.account===a.handle && p.isOwn);
  const tsList = own.map(p=>p.ts_ms).filter(Boolean);
  let earliest = tsList.length ? new Date(Math.min(...tsList)) : null;
  // Prefer firstPostDate from profile.json (true account activation) over the scraped-window floor
  if(a.firstPostDate){ const d = new Date(a.firstPostDate); if(!isNaN(d)) earliest = d; }
  const totalReach = own.reduce((s,p)=>s+(p.views||0),0);
  // Follower-based ER (industry standard). p.er is precomputed as engagement/followers in Python.
  // Use MEDIAN as the headline metric — viral spikes (one reel reaching 30× follower count) inflate
  // the mean dramatically. Median represents the typical post and is what serious analytics tools show.
  const ersValid = own.filter(p=>p.er!=null).map(p=>p.er);
  const sorted = [...ersValid].sort((a,b)=>a-b);
  const medianER = sorted.length ? (sorted.length%2 ? sorted[sorted.length>>1] : (sorted[(sorted.length>>1)-1]+sorted[sorted.length>>1])/2) : 0;
  const meanER = ersValid.length ? ersValid.reduce((s,x)=>s+x,0)/ersValid.length : 0;
  // Inbound (tagged-in / about-this-account) records: posts whose folder is this handle but ownerUsername ≠ handle.
  // These are posts by OTHER accounts (brands, media, peers) that mention or tag this account.
  const inbound = DATA.filter(p => p.account === a.handle && !p.isOwn);
  // Top 3 inbound owners for a hint (e.g. "BNW, Fortune India, Entrepreneur ME, …")
  const inboundOwnerCounts = {};
  for(const p of inbound){ if(p.owner) inboundOwnerCounts[p.owner] = (inboundOwnerCounts[p.owner]||0) + 1; }
  const topInboundOwners = Object.entries(inboundOwnerCounts).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([h])=>'@'+h);
  return {
    followers: a.followers,
    activeSince: earliest ? earliest.toLocaleString('en-GB',{month:'short',year:'numeric',timeZone:'Asia/Dubai'}) : '—',
    totalPosts: a.postsCount,
    tracked: own.length,
    inboundCount: inbound.length,
    topInboundOwners: topInboundOwners,
    reach: totalReach,
    er: medianER,
    erMean: meanER,
  };
}

function renderOverview(accs){
  const cols = accs.length===1 ? 12 : accs.length===2 ? 6 : 4;
  const cards = accs.map(a=>{
    const k = overviewKPIs(a);
    const fc = a.segment==='Founder' ? 'founder-avatar' : '';
    return `<div class="span-${cols} ${fc}"><div class="overview-card" data-acc="${a.handle}" style="--accent:${a.color}">
      <div class="head">
        ${avatarHTML(a)}
        <div>
          <div class="name">${escHtml(a.fullName||a.handle)}${a.verified?'<span class="verified-badge">✓</span>':''}</div>
          <div class="handle">@${a.handle}${a.category?' · '+escHtml(a.category):''}</div>
        </div>
      </div>
      <div class="bio">${escHtml(a.biography||'')}</div>
      <div class="kpis">
        <div class="tile"><div class="v">${fmt(k.followers)}</div><div class="l">Followers</div></div>
        <div class="tile"><div class="v">${k.activeSince}</div><div class="l">Active since</div></div>
        <div class="tile"><div class="v">${fmt(k.totalPosts)}</div><div class="l">Total posts</div></div>
        <div class="tile" title="Own posts: ${k.tracked} (where this handle is the post owner). Inbound: ${k.inboundCount} posts by OTHER accounts that tagged / mentioned this handle${k.topInboundOwners.length?' — e.g. '+k.topInboundOwners.join(', ')+', etc.':''}."><div class="v">${k.tracked}<span style="color:#5b9cff;font-size:14px;font-weight:600;margin-left:6px">+ ${k.inboundCount}</span></div><div class="l">Own <span style="opacity:.6">posts</span> <span style="color:#5b9cff;opacity:.7">· inbound tags</span></div></div>
        <div class="tile"><div class="v">${fmt(k.reach)}</div><div class="l">Total reach</div></div>
        <div class="tile" title="Median engagement rate — typical post performance. Mean: ${(k.erMean*100).toFixed(2)}%${k.erMean>k.er*3?' (viral-inflated)':''}"><div class="v">${(k.er*100).toFixed(2)}%</div><div class="l">Median ER${k.erMean>k.er*3?' <span style="color:var(--warn);font-size:9px">⚠ mean '+(k.erMean*100).toFixed(0)+'%</span>':''}</div></div>
      </div>
      <div class="open-link"><span>Open full dashboard</span><span class="arr">→</span></div>
    </div></div>`;
  }).join('');
  const r = dataRangeFor(p=>p.segment===CURRENT_SEG);
  const rangeChip = r ? `<span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0;margin-left:8px">— data window: <strong style="color:var(--ink)">${r.min.toISOString().slice(0,10)}</strong> → <strong style="color:var(--ink)">${r.max.toISOString().slice(0,10)}</strong> · ${r.count} posts</span>` : '';
  return `<div class="section-title">${CURRENT_SEG} accounts ${rangeChip}<div style="font-size:11px;color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0;margin-top:4px">Click any card to open its full dashboard</div></div>${cards}`;
}

function wireOverviewClicks(){
  document.querySelectorAll('.overview-card').forEach(el=>{
    el.addEventListener('click',()=>{
      CURRENT_ACCOUNT = el.dataset.acc;
      render();
      window.scrollTo({top:0,behavior:'smooth'});
    });
  });
}

function renderBreadcrumb(){
  const acc = ACCOUNTS.find(a=>a.handle===CURRENT_ACCOUNT);
  return `<div class="breadcrumb"><a data-back="1">← Back to ${CURRENT_SEG}s</a><span class="sep">/</span><span class="curr">@${CURRENT_ACCOUNT}${acc?.verified?' ✓':''}</span></div>`;
}
function wireBackClick(){
  document.querySelectorAll('[data-back]').forEach(el=>{
    el.addEventListener('click',()=>{ CURRENT_ACCOUNT=null; render(); window.scrollTo({top:0,behavior:'smooth'}); });
  });
}

// ---------- comparison view (chart-first) ----------
const COMPARE_METRICS = [
  {key:'followers',   label:'Followers',         fmt:fmt,   get:a=>a.followers||0},
  {key:'engagement',  label:'Avg engagement',    fmt:fmt,   get:a=>avg(ownByAcc(a.handle),'engagement')},
  {key:'likes',       label:'Avg likes',         fmt:fmt,   get:a=>avg(ownByAcc(a.handle),'likes')},
  {key:'comments',    label:'Avg comments',      fmt:fmt,   get:a=>avg(ownByAcc(a.handle),'comments')},
  {key:'reach',       label:'Total reach',       fmt:fmt,   get:a=>ownByAcc(a.handle).reduce((s,p)=>s+(p.views||0),0)},
  {key:'er',          label:'Engagement rate (median)', fmt:fmtPc, get:a=>{const r=ownByAcc(a.handle).filter(p=>p.er!=null).map(p=>p.er).sort((x,y)=>x-y);if(!r.length)return 0;const m=r.length>>1;return r.length%2?r[m]:(r[m-1]+r[m])/2;}},
  {key:'cadence',     label:'Posts per week',    fmt:v=>v.toFixed(1), get:a=>{const arr=ownByAcc(a.handle);const ts=arr.map(p=>p.ts_ms).filter(Boolean);if(!ts.length)return 0;const s=(Math.max(...ts)-Math.min(...ts))/(7*864e5);return s>0?arr.length/s:arr.length;}},
];
function battlecardKPIs(a){
  const own = ownByAcc(a.handle);
  const reels = own.filter(p=>p.views>0);
  return [
    ['Followers',     fmt(a.followers||0)],
    ['Avg engagement',fmt(avg(own,'engagement'))],
    ['Total reach',   fmt(own.reduce((s,p)=>s+(p.views||0),0))],
    ['Engagement rate (median)',fmtPc((function(){const er=own.filter(p=>p.er!=null).map(p=>p.er).sort((a,b)=>a-b);if(!er.length)return 0;const m=er.length>>1;return er.length%2?er[m]:(er[m-1]+er[m])/2;})())],
    ['Posts tracked', own.length],
  ];
}
function renderComparison(accs){
  const cols = accs.length===1?12:accs.length===2?6:accs.length===3?4:3;
  const battlecards = accs.map(a=>{
    const fc = a.segment==='Founder' ? 'founder-avatar' : '';
    const stats = battlecardKPIs(a).map(([l,v])=>`<div class="row"><span class="l">${l}</span><span class="v">${v}</span></div>`).join('');
    return `<div class="card span-${cols} ${fc}" style="--accent:${a.color};border-color:${rgba(a.color,.4)};padding:0">
      <div class="battlecard">
        <div class="top">${avatarHTML(a)}<div><div class="name">${escHtml(a.fullName||a.handle)}${a.verified?' <span class="verified-badge">✓</span>':''}</div><div class="handle">@${a.handle} · ${a.segment}</div></div></div>
        <div class="rows">${stats}</div>
      </div>
    </div>`;
  }).join('');
  const metricBtns = COMPARE_METRICS.map(m=>`<button class="metric-btn ${m.key===COMPARE_METRIC?'on':''}" data-metric="${m.key}">${m.label}</button>`).join('');
  // Win/loss tally — count how many of the 7 metrics each selected account wins
  function buildWinLoss(){
    if(accs.length<2) return '';
    const wins = Object.fromEntries(accs.map(a=>[a.handle,0]));
    for(const m of COMPARE_METRICS){
      const vals = accs.map(a=>({h:a.handle, v:m.get(a)})).sort((a,b)=>b.v-a.v);
      if(vals.length && vals[0].v>0) wins[vals[0].h]++;
    }
    const sorted = Object.entries(wins).sort((a,b)=>b[1]-a[1]);
    const total = COMPARE_METRICS.length;
    return `<div class="card span-12" style="padding:16px 18px"><h3 style="margin-bottom:8px">Win-loss tally <span class="tag">out of ${total} metrics</span></h3>
      <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center">${sorted.map(([h,w])=>{
        const a=accs.find(x=>x.handle===h);
        return `<div style="display:flex;align-items:center;gap:8px;font-size:14px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${a.color}"></span><strong>@${h}</strong> <span style="color:var(--mut)">wins</span> <strong style="color:${a.color}">${w}/${total}</strong></div>`;
      }).join('')}</div></div>`;
  }
  return `
  ${buildWinLoss()}
  <div class="section-title">Head-to-head battlecards</div>
  ${battlecards}
  <div class="section-title">Comparative Auto Insights</div>
  <div class="card span-12" style="padding-bottom:6px"><div id="cmp_auto_insights"></div></div>
  <div class="section-title">Share of Voice</div>
  <div class="card span-4"><h3>Reach SOV</h3><div class="chart-wrap"><canvas id="cmp_sov_reach"></canvas></div></div>
  <div class="card span-4"><h3>Engagement SOV</h3><div class="chart-wrap"><canvas id="cmp_sov_eng"></canvas></div></div>
  <div class="card span-4"><h3>Post Volume SOV</h3><div class="chart-wrap"><canvas id="cmp_sov_posts"></canvas></div></div>
  <div class="section-title">Charts</div>
  <div class="card span-7"><h3>Metric leaderboard <span class="tag">click to switch</span></h3>
    <div class="metric-bar"><span class="lbl">Metric</span>${metricBtns}</div>
    <div class="chart-wrap lg"><canvas id="cmp_bar"></canvas></div>
  </div>
  <div class="card span-5"><h3>Strategy Positioning Matrix <span class="tag">Effort vs Quality</span></h3>
    <div class="chart-wrap lg"><canvas id="cmp_matrix"></canvas></div>
  </div>
  <div class="card span-8"><h3>Posts per week</h3><div class="chart-wrap lg"><canvas id="ch_cad"></canvas></div></div>
  <div class="card span-4"><h3>Own vs tagged</h3><div class="chart-wrap"><canvas id="ch_owntag"></canvas></div></div>
  <div class="card span-6"><h3>Engagement over time</h3><div class="chart-wrap lg"><canvas id="ch_engt"></canvas></div></div>
  <div class="card span-6"><h3>View → Like conversion</h3><div class="chart-wrap lg"><canvas id="ch_vlr"></canvas></div></div>
  <div class="card span-4"><h3>Content type mix</h3><div class="chart-wrap"><canvas id="ch_type"></canvas></div></div>
  <div class="card span-4"><h3>Avg likes by type <span class="tag">log</span></h3><div class="chart-wrap"><canvas id="ch_type_l"></canvas></div></div>
  <div class="card span-4"><h3>Avg comments by type</h3><div class="chart-wrap"><canvas id="ch_type_c"></canvas></div></div>

  <div class="section-title">Content themes &amp; pillars <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— head-to-head theme strategy</span></div>
  <div class="card span-6"><h3>Theme mix <span class="tag">stacked posts by pillar</span></h3><div class="chart-wrap lg"><canvas id="ch_themes"></canvas></div></div>
  <div class="card span-6"><h3>Engagement by theme <span class="tag">avg eng per theme · grouped</span></h3><div class="chart-wrap lg"><canvas id="ch_theme_eng"></canvas></div></div>
  <div class="card span-12"><h3>Theme leaderboard <span class="tag">aggregated across selected accounts</span></h3><div id="tbl_themes"></div></div>

  <div class="section-title">Tag analysis <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— who tags these accounts and who they tag</span></div>
  <div class="card span-12"><div id="tag_summary"></div></div>
  <div class="card span-12"><h3>Inbound tags <span class="tag">who tagged each account, by reach/eng impact · matrix view</span></h3><div id="tbl_tags_in" style="overflow-x:auto"></div></div>
  <div class="card span-12"><h3>Outbound tags <span class="tag">who each account tags, by avg eng on those posts · matrix view</span></h3><div id="tbl_tags_out" style="overflow-x:auto"></div></div>

  <div class="card span-12"><h3>Top 20 posts across selected accounts</h3>
    <div class="tabs" data-grp="top">
      <span class="tab active" data-top="all">All</span>
      ${accs.map(a=>`<span class="tab" data-top="${a.handle}">@${a.handle}</span>`).join('')}
    </div>
    <div class="tabs" data-grp="topsort">
      <span class="tab active" data-sort="engagement">Sort: engagement</span>
      <span class="tab" data-sort="views">Sort: views</span>
      <span class="tab" data-sort="er">Sort: ER</span>
    </div>
    <div id="tbl_top"></div>
  </div>`;
}
function drawComparison(accs){
  // Bar leaderboard chart
  const m = COMPARE_METRICS.find(x=>x.key===COMPARE_METRIC) || COMPARE_METRICS[0];
  const sorted = [...accs].sort((a,b)=>m.get(b)-m.get(a));
  new Chart(document.getElementById('cmp_bar'),{type:'bar',
    data:{labels:sorted.map(a=>'@'+a.handle),datasets:[{label:m.label,data:sorted.map(a=>m.get(a)),backgroundColor:sorted.map(a=>a.color),borderRadius:8,barThickness:'flex'}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>m.fmt(c.parsed.x)}}},
      scales:{x:{beginAtZero:true,ticks:{callback:v=>m.fmt(v)}}}}});

  // Strategy Matrix (Bubble Chart)
  // X = Posts/wk (Effort), Y = Engagement Rate (Quality), Bubble Size = Followers
  const getPostsWk = a => {
    const arr = ownByAcc(a.handle);
    const ts = arr.map(p=>p.ts_ms).filter(Boolean);
    if(!ts.length) return 0;
    const s = (Math.max(...ts)-Math.min(...ts))/(7*864e5);
    return s > 0 ? arr.length/s : arr.length;
  };
  const getER = a => {
    const r = ownByAcc(a.handle).filter(p=>p.er!=null);
    return r.length ? r.reduce((s,p)=>s+p.er,0)/r.length : 0;
  };
  
  const maxFollowers = accs.length ? Math.max(...accs.map(a=>a.followers||0)) : 1;
  
  const bubbleDs = accs.map(a=>{
    const rVal = a.followers || 0;
    // Scale radius using square root for area proportionality, max 40px
    const radius = maxFollowers > 0 ? Math.max(5, (Math.sqrt(rVal) / Math.sqrt(maxFollowers)) * 40) : 10;
    return {
      label: '@'+a.handle,
      backgroundColor: rgba(a.color, 0.7),
      borderColor: a.color,
      borderWidth: 2,
      data: [{
        x: getPostsWk(a),
        y: getER(a) * 100, // percentage
        r: radius,
        rawFollowers: rVal
      }]
    };
  });
  
  new Chart(document.getElementById('cmp_matrix'), {
    type: 'bubble',
    data: { datasets: bubbleDs },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: c => {
              const d = c.raw;
              return `${c.dataset.label}: ${d.x.toFixed(1)} posts/wk | ${d.y.toFixed(2)}% ER | ${fmt(d.rawFollowers)} Followers`;
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'Posting Frequency (Posts / Week)' }, beginAtZero: true },
        y: { title: { display: true, text: 'Avg Engagement Rate (%)' }, beginAtZero: true }
      }
    }
  });

  const reachSOV = accs.map(a=>ownByAcc(a.handle).reduce((s,p)=>s+(p.views||0),0));
  const engSOV = accs.map(a=>ownByAcc(a.handle).reduce((s,p)=>s+(p.engagement||0),0));
  const postSOV = accs.map(a=>ownByAcc(a.handle).length);
  function drawPie(id, data){
    const el = document.getElementById(id);
    if(el){
      new Chart(el, {
        type: 'doughnut',
        data: {
          labels: accs.map(a=>'@'+a.handle),
          datasets: [{data: data, backgroundColor: accs.map(a=>a.color), borderWidth: 2, borderColor: '#141b2b'}]
        },
        options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {position: 'bottom'}}}
      });
    }
  }
  drawPie('cmp_sov_reach', reachSOV);
  drawPie('cmp_sov_eng', engSOV);
  drawPie('cmp_sov_posts', postSOV);

  // Reuse existing charts for the bottom section
  cadenceChart(accs);
  ownTaggedChart(accs);
  engTimeChart(accs);
  vlrChart(accs);
  typeMixChart(accs);
  typeMetricChart(accs,'ch_type_l','likes',true);
  typeMetricChart(accs,'ch_type_c','comments',false);
  themeMixChart(accs);
  themeEngagementChart(accs);
  themeLeaderboardTable(accs);
  tagSummary(accs);
  inboundTagsTable(accs);
  outboundTagsTable(accs);
  topPosts(accs);
  buildComparativeInsights(accs);
  // wire top-posts tabs
  document.querySelectorAll('.tabs[data-grp="top"], .tabs[data-grp="topsort"]').forEach(box=>{
    box.addEventListener('click',e=>{
      const t=e.target.closest('.tab'); if(!t) return;
      [...box.children].forEach(c=>c.classList.remove('active'));
      t.classList.add('active');
      topPosts(accs);
    });
  });
}
function wireMetricClicks(){
  document.querySelectorAll('.metric-btn').forEach(b=>{
    b.addEventListener('click',()=>{ COMPARE_METRIC = b.dataset.metric; render(); });
  });
}

// ---------- comparison picker ----------
function renderPicker(){
  const chips = ACCOUNTS.map(a=>{
    const sel = COMPARE_PICK.includes(a.handle);
    return `<button class="pick-chip ${sel?'on':''}" data-acc="${a.handle}" style="${sel?'border-color:'+a.color+';background:'+rgba(a.color,.12):''}">${avatarHTML(a)}<span>@${a.handle}</span><span class="seg">${a.segment}</span></button>`;
  }).join('');
  return `<div class="pick-bar">
    <span class="lbl">Compare</span>
    ${chips}
    <div class="pick-actions">
      <button class="act" data-pick-all="1">All</button>
      <button class="act" data-pick-founder="1">Founders</button>
      <button class="act" data-pick-enterprise="1">Enterprises</button>
      <button class="act" data-pick-none="1">Clear</button>
    </div>
  </div>`;
}
function wirePickerClicks(){
  document.querySelectorAll('.pick-chip').forEach(el=>{
    el.addEventListener('click',()=>{
      const h=el.dataset.acc;
      if(COMPARE_PICK.includes(h)) COMPARE_PICK = COMPARE_PICK.filter(x=>x!==h);
      else COMPARE_PICK = [...COMPARE_PICK, h];
      render(); window.scrollTo({top:0,behavior:'smooth'});
    });
  });
  const set=(arr)=>{ COMPARE_PICK = arr; render(); };
  const q=document.querySelector('[data-pick-all]'); if(q) q.addEventListener('click',()=>set(ACCOUNTS.map(a=>a.handle)));
  const f=document.querySelector('[data-pick-founder]'); if(f) f.addEventListener('click',()=>set(ACCOUNTS.filter(a=>a.segment==='Founder').map(a=>a.handle)));
  const e=document.querySelector('[data-pick-enterprise]'); if(e) e.addEventListener('click',()=>set(ACCOUNTS.filter(a=>a.segment==='Enterprise').map(a=>a.handle)));
  const n=document.querySelector('[data-pick-none]'); if(n) n.addEventListener('click',()=>set([]));
}

function profileCards(accs){
  const cols = Math.max(1, Math.min(4, Math.ceil(12/accs.length)));
  return accs.map(a=>{
    const fc = a.segment==='Founder' ? 'founder-avatar' : '';
    return `<div class="card span-${cols*3<=12?cols*3:12} ${fc}" style="border-color:${rgba(a.color,.5)};padding:0">
      <div class="profile-card">
        ${avatarHTML(a)}
        <div class="info">
          <div class="name">${escHtml(a.fullName||a.handle)}${a.verified?'<span class="verified-badge">✓</span>':''}</div>
          <div class="handle">@${a.handle}${a.category?' · '+escHtml(a.category):''}</div>
          ${a.biography?`<div class="bio">${escHtml(a.biography)}</div>`:''}
          <div class="stats">
            <div><b>${fmt(a.followers)}</b> followers</div>
            <div><b>${fmt(a.postsCount)}</b> posts</div>
            <div><b>${a.own}</b> tracked</div>
          </div>
        </div>
      </div>
    </div>`;
  }).join('');
}

function buildLayout(accs){
  const accIds = accs.map(a=>a.handle);
  const profRow = isComparison() ? '' : `<div class="section-title">Tracked accounts</div>${profileCards(accs)}`;
  return `
  ${profRow}
  <div class="section-title">Headline metrics — ${CURRENT_SEG}</div>
  ${kpiCards(accs)}
  <div class="card span-7"><h3>Head-to-head scorecard <span class="tag">own posts</span></h3><div id="scorecard"></div></div>
  <div class="card span-5"><h3>Auto insights</h3><div id="insights"></div></div>

  <div class="section-title">Cadence &amp; timing</div>
  <div class="card span-8"><h3>Posts per week</h3><div class="chart-wrap lg"><canvas id="ch_cad"></canvas></div></div>
  <div class="card span-4"><h3>Own vs tagged</h3><div class="chart-wrap"><canvas id="ch_owntag"></canvas></div></div>

  ${accs.map(a=>`<div class="card span-6"><h3>Posting heatmap — @${a.handle} <span class="tag">GST day × hour (Dubai, UTC+4)</span></h3><div class="chart-wrap md"><canvas id="ch_heat_${cssId(a.handle)}"></canvas></div></div>`).join('')}

  <div class="card span-6"><h3>Avg engagement by day of week</h3><div class="chart-wrap"><canvas id="ch_dow"></canvas></div></div>
  <div class="card span-6"><h3>Posting gap (days)</h3><div class="chart-wrap"><canvas id="ch_gap"></canvas></div></div>

  <div class="section-title">Content mix &amp; performance</div>
  <div class="card span-4"><h3>Content type mix</h3><div class="chart-wrap"><canvas id="ch_type"></canvas></div></div>
  <div class="card span-4"><h3>Avg likes by type <span class="tag">log</span></h3><div class="chart-wrap"><canvas id="ch_type_l"></canvas></div></div>
  <div class="card span-4"><h3>Avg comments by type</h3><div class="chart-wrap"><canvas id="ch_type_c"></canvas></div></div>

  <div class="card span-6"><h3>Reel views distribution</h3><div class="chart-wrap"><canvas id="ch_views"></canvas></div></div>
  <div class="card span-6"><h3>View → Like conversion</h3><div class="chart-wrap"><canvas id="ch_vlr"></canvas></div></div>

  <div class="card span-6"><h3>Engagement over time</h3><div class="chart-wrap lg"><canvas id="ch_engt"></canvas></div></div>
  <div class="card span-6"><h3>Video duration vs views</h3><div class="chart-wrap lg"><canvas id="ch_dur"></canvas></div></div>

  <div class="card span-6"><h3>Caption length vs engagement</h3><div class="chart-wrap"><canvas id="ch_cap"></canvas></div></div>
  <div class="card span-6"><h3>Carousel slides vs engagement</h3><div class="chart-wrap"><canvas id="ch_slides"></canvas></div></div>

  <div class="section-title">Tag analysis <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— who tags this account and who this account tags</span></div>
  <div class="card span-12"><div id="tag_summary"></div></div>
  <div class="card span-6"><h3>Inbound tags <span class="tag">accounts that tagged this account, ranked by reach/eng they drove</span></h3><div id="tbl_tags_in"></div></div>
  <div class="card span-6"><h3>Outbound tags <span class="tag">accounts this account tags in own posts, ranked by avg eng</span></h3><div id="tbl_tags_out"></div></div>

  <div class="section-title">Content themes &amp; pillars <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— what kind of content this account produces</span></div>
  <div class="card span-6"><h3>Theme mix <span class="tag">% of posts by content pillar</span></h3><div class="chart-wrap"><canvas id="ch_themes"></canvas></div></div>
  <div class="card span-6"><h3>Engagement by theme <span class="tag">avg eng per theme</span></h3><div class="chart-wrap"><canvas id="ch_theme_eng"></canvas></div></div>
  <div class="card span-12"><h3>Theme leaderboard</h3><div id="tbl_themes"></div></div>

  <div class="section-title">Posting calendar &amp; geography</div>
  ${accs.map(a=>`<div class="card span-12"><h3>Posting calendar — @${a.handle} <span class="tag">last ~52 weeks · color intensity = posts that day</span></h3><div id="cal_${cssId(a.handle)}"></div></div>`).join('')}
  <div class="card span-6"><h3>Top locations <span class="tag">where posts were geo-tagged</span></h3><div id="tbl_loc"></div></div>
  <div class="card span-6"><h3>Top mentions <span class="tag">@accounts this acc tags in own captions</span></h3><div id="tbl_mentions"></div></div>

  <div class="section-title">Standout posts</div>
  <div class="card span-12"><h3>Posts that beat normal engagement <span class="tag">≥3× this account's median</span></h3><div id="tbl_standouts"></div></div>

  <div class="section-title">Topics, hashtags &amp; audio</div>
  <div class="card span-6"><h3>Top hashtags</h3>
    <div class="tabs" data-grp="hash">${accs.map((a,i)=>`<span class="tab ${i===0?'active':''}" data-acc="${a.handle}">@${a.handle}</span>`).join('')}</div>
    <div id="tbl_hash"></div>
  </div>
  <div class="card span-6"><h3>Hashtag effectiveness <span class="tag">avg eng / post</span></h3>
    <div class="tabs" data-grp="hash_eff">${accs.map((a,i)=>`<span class="tab ${i===0?'active':''}" data-acc="${a.handle}">@${a.handle}</span>`).join('')}</div>
    <div id="tbl_hash_eff"></div>
  </div>

  <div class="card span-4"><h3>Audio mix</h3><div class="chart-wrap"><canvas id="ch_audio"></canvas></div></div>
  <div class="card span-4"><h3>Audio performance <span class="tag">avg views, log</span></h3><div class="chart-wrap"><canvas id="ch_audio_perf"></canvas></div></div>
  <div class="card span-4"><h3>Top songs used</h3><div id="tbl_songs"></div></div>

  <div class="card span-6"><h3>Top tagged accounts</h3>
    <div class="tabs" data-grp="tag">${accs.map((a,i)=>`<span class="tab ${i===0?'active':''}" data-acc="${a.handle}">@${a.handle}</span>`).join('')}</div>
    <div id="tbl_tag"></div>
  </div>
  <div class="card span-6"><h3>Caption word cloud</h3><div id="wordcloud"></div></div>

  <div class="section-title">Top performers</div>
  <div class="card span-12"><h3>Top 20 posts by engagement</h3>
    <div class="tabs" data-grp="top">
      <span class="tab active" data-top="all">All</span>
      ${accs.map(a=>`<span class="tab" data-top="${a.handle}">@${a.handle}</span>`).join('')}
    </div>
    <div class="tabs" data-grp="topsort">
      <span class="tab active" data-sort="engagement">Sort: engagement</span>
      <span class="tab" data-sort="views">Sort: views</span>
      <span class="tab" data-sort="er">Sort: ER</span>
    </div>
    <div id="tbl_top"></div>
  </div>
  `;
}

function cssId(s){ return s.replace(/[^a-z0-9]/gi,'_'); }

function kpiCards(accs){
  const own = segOwn();
  const all = segData();
  const reelsOwn = own.filter(p=>p.views>0);
  function weekly(arr){const ts=arr.map(p=>p.ts_ms).filter(Boolean);if(!ts.length) return 0;const span=(Math.max(...ts)-Math.min(...ts))/(7*864e5);return span>0?arr.length/span:arr.length;}
  return `
  <div class="card kpi span-3"><h3>Posts <span class="tag">own / total</span></h3><div class="v">${own.length} / ${all.length}</div><div class="d">${accs.map(a=>`@${a.handle}: ${a.own}`).join(' · ')}</div></div>
  <div class="card kpi span-3"><h3>Avg engagement / own post</h3><div class="v">${fmt(avg(own,'engagement'))}</div><div class="d">likes + comments</div></div>
  <div class="card kpi span-3"><h3>Avg reel views</h3><div class="v">${fmt(avg(reelsOwn,'views'))}</div><div class="d">${reelsOwn.length} reels</div></div>
  <div class="card kpi span-3"><h3>Weekly cadence</h3><div class="v">${weekly(own).toFixed(1)}</div><div class="d">own posts/week across segment</div></div>`;
}

// ---------- draw all charts ----------
function drawAll(accs){
  scorecard(accs);
  insights(accs);
  cadenceChart(accs);
  ownTaggedChart(accs);
  accs.forEach(a=>heatmap(a));
  dowChart(accs);
  gapChart(accs);
  typeMixChart(accs);
  typeMetricChart(accs,'ch_type_l','likes',true);
  typeMetricChart(accs,'ch_type_c','comments',false);
  viewsDistChart(accs);
  vlrChart(accs);
  engTimeChart(accs);
  durChart(accs);
  capEngChart(accs);
  slidesChart(accs);
  audioMixChart(accs);
  audioPerfChart(accs);
  topSongs(accs);
  wireListTabs();
  refreshLists(accs);
  audioMix:1;
  topPostsWire(accs);
  topPosts(accs);
  wordcloud(accs);
  accs.forEach(calendarHeatmap);
  locationsTable(accs);
  mentionsTable(accs);
  standoutPosts(accs);
  themeMixChart(accs);
  themeEngagementChart(accs);
  themeLeaderboardTable(accs);
  tagSummary(accs);
  inboundTagsTable(accs);
  outboundTagsTable(accs);
}

// ---------- tag analysis (inbound + outbound) ----------
function tagSummary(accs){
  const el=document.getElementById('tag_summary'); if(!el) return;
  const rows=accs.map(a=>{
    // Inbound: posts where account is this acc and isOwn=false (someone else's post that includes this acc)
    const inbound = DATA.filter(p=>p.account===a.handle && !p.isOwn);
    const inboundReach = inbound.reduce((s,p)=>s+(p.views||0),0);
    const inboundEng = inbound.reduce((s,p)=>s+(p.engagement||0),0);
    const uniqueTaggers = new Set(inbound.map(p=>p.owner)).size;

    // Outbound: this acc's own posts; tagged[] + mentions[] arrays
    const own = ownByAcc(a.handle);
    let outboundCount = 0, outboundPostsWithTags = 0, outboundEngSum = 0;
    const uniqueTaggedSet = new Set();
    for(const p of own){
      const combined = new Set([...(p.tagged||[]), ...(p.mentions||[])].filter(u => u && u !== a.handle));
      if(combined.size){
        outboundPostsWithTags++;
        outboundEngSum += p.engagement;
        for(const u of combined){ outboundCount++; uniqueTaggedSet.add(u); }
      }
    }
    const outboundAvgEng = outboundPostsWithTags ? outboundEngSum/outboundPostsWithTags : 0;
    return {a, inboundN:inbound.length, uniqueTaggers, inboundReach, inboundEng,
            outboundN:outboundCount, uniqueTagged:uniqueTaggedSet.size, outboundPostsWithTags, outboundAvgEng};
  });

  el.innerHTML = rows.map(r=>`<div style="display:grid;grid-template-columns:repeat(${accs.length>1?2:6},1fr);gap:14px;padding:6px 4px">
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Inbound posts</div><div style="font-size:22px;font-weight:700">${fmt(r.inboundN)}</div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Unique taggers</div><div style="font-size:22px;font-weight:700">${fmt(r.uniqueTaggers)}</div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Reach driven (inbound)</div><div style="font-size:22px;font-weight:700">${fmt(r.inboundReach)}</div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Engagement driven (inbound)</div><div style="font-size:22px;font-weight:700">${fmt(r.inboundEng)}</div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Outbound tags (unique)</div><div style="font-size:22px;font-weight:700">${fmt(r.uniqueTagged)} <span style="color:var(--mut);font-size:13px;font-weight:500">in ${r.outboundPostsWithTags} posts</span></div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Avg eng on tag posts</div><div style="font-size:22px;font-weight:700">${fmt(r.outboundAvgEng)}</div></div>
  </div>`).join('');
}

function inboundTagsTable(accs){
  const el=document.getElementById('tbl_tags_in'); if(!el) return;

  if(accs.length<=1){
    // Single-account: keep flat list view
    const a = accs[0];
    const inbound = DATA.filter(p=>p.account===a.handle && !p.isOwn);
    const byOwner = {};
    for(const p of inbound){
      if(!p.owner) continue;
      if(!byOwner[p.owner]) byOwner[p.owner]={n:0,reach:0,eng:0,topPost:null};
      byOwner[p.owner].n++;
      byOwner[p.owner].reach += p.views||0;
      byOwner[p.owner].eng   += p.engagement||0;
      if(!byOwner[p.owner].topPost || p.engagement>(byOwner[p.owner].topPost.engagement||0)){
        byOwner[p.owner].topPost = p;
      }
    }
    const rows = Object.entries(byOwner).map(([owner,v])=>({owner,...v}))
      .sort((a,b)=>(b.reach+b.eng*5)-(a.reach+a.eng*5));
    if(!rows.length){el.innerHTML='<div class="muted">No inbound tagged-in posts in dataset</div>';return;}
    el.innerHTML='<table><thead><tr><th>Tagger</th><th class="num">Posts</th><th class="num" title="Video views only — IG does not expose reach for static images/carousels">Reach (video)</th><th class="num">Total eng</th><th>Best post</th></tr></thead><tbody>'+
      rows.slice(0,25).map(r=>{
        const tp=r.topPost;
        const tpCell = tp ? `<a href="${escHtml(tp.url||'')}" target="_blank">${fmt(tp.engagement)} eng${tp.views?` · ${fmt(tp.views)} views`:''} ↗</a>` : '—';
        const reachCell = r.reach>0 ? `<span>${fmt(r.reach)}</span>` : `<span class="muted" title="No video views — static posts only.">— <span style="font-size:10px;opacity:.6">static</span></span>`;
        return `<tr><td><a target="_blank" href="https://www.instagram.com/${escHtml(r.owner)}/">@${escHtml(r.owner)}</a></td><td class="num">${r.n}</td><td class="num">${reachCell}</td><td class="num">${fmt(r.eng)}</td><td>${tpCell}</td></tr>`;
      }).join('')+'</tbody></table><div style="font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5">⚑ <strong>Reach (video)</strong> shows total video/reel views only. IG does not expose reach for static images/carousels.</div>';
    return;
  }

  // MULTI-ACCOUNT MATRIX: rows = unique taggers, columns = each tracked account
  // Cell shows posts·eng contributed by that tagger to that account (— if none)
  const matrix = {};  // taggerHandle -> { accHandle: {n, reach, eng, topPost}, totals: {...} }
  for(const a of accs){
    const inbound = DATA.filter(p=>p.account===a.handle && !p.isOwn);
    for(const p of inbound){
      if(!p.owner) continue;
      if(!matrix[p.owner]) matrix[p.owner] = {accCells:{}, totalN:0, totalReach:0, totalEng:0, accHits:0};
      const m = matrix[p.owner];
      if(!m.accCells[a.handle]){ m.accCells[a.handle]={n:0,reach:0,eng:0,topPost:null}; m.accHits++; }
      const c = m.accCells[a.handle];
      c.n++; c.reach+=p.views||0; c.eng+=p.engagement||0;
      if(!c.topPost || (p.engagement||0)>(c.topPost.engagement||0)) c.topPost=p;
      m.totalN++; m.totalReach+=p.views||0; m.totalEng+=p.engagement||0;
    }
  }
  const rows = Object.entries(matrix).map(([owner,v])=>({owner,...v}))
    .sort((a,b)=> b.accHits!==a.accHits ? b.accHits-a.accHits : (b.totalReach+b.totalEng*5)-(a.totalReach+a.totalEng*5));
  if(!rows.length){el.innerHTML='<div class="muted">No inbound tagged-in posts in dataset</div>';return;}

  // Compact matrix table with horizontal scroll. Each cell is single-line.
  let html='<table class="tag-matrix"><thead><tr><th style="position:sticky;left:0;background:var(--card2);z-index:2">Tagger</th><th class="num" title="Accounts this tagger touched out of selected">Hit</th>';
  for(const a of accs) html+=`<th class="num" style="min-width:130px"><span class="pill" style="background:${rgba(a.color,.18)};color:${a.color};white-space:nowrap;font-size:10px">@${escHtml(a.handle)}</span></th>`;
  html+='<th class="num">Total eng</th></tr></thead><tbody>';
  for(const r of rows.slice(0,30)){
    html+=`<tr><td style="position:sticky;left:0;background:var(--card)"><a target="_blank" href="https://www.instagram.com/${escHtml(r.owner)}/">@${escHtml(r.owner)}</a></td><td class="num"><strong>${r.accHits}</strong>/${accs.length}</td>`;
    for(const a of accs){
      const c = r.accCells[a.handle];
      if(!c){ html+='<td class="num"><span class="muted">—</span></td>'; continue; }
      const tp = c.topPost;
      const tpLink = tp && tp.url ? ` <a href="${escHtml(tp.url)}" target="_blank" style="font-size:11px;opacity:.7;text-decoration:none">↗</a>` : '';
      const reachTxt = c.reach>0 ? ` · ${fmt(c.reach)} reach` : '';
      html+=`<td class="num" style="white-space:nowrap"><strong>${c.n}</strong> <span style="color:var(--mut);font-size:11px">· ${fmt(c.eng)} eng${reachTxt}</span>${tpLink}</td>`;
    }
    html+=`<td class="num"><strong>${fmt(r.totalEng)}</strong></td></tr>`;
  }
  html+='</tbody></table>';
  html+='<div style="font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5">Sorted by <strong>accounts touched</strong> first (shared amplifiers come up top). Each cell: <strong>posts</strong> · total engagement · reach (video only) · ↗ link to best post. Hover the row to see full content.</div>';
  el.innerHTML=html;
}

function outboundTagsTable(accs){
  const el=document.getElementById('tbl_tags_out'); if(!el) return;

  if(accs.length<=1){
    // Single-account: flat list
    const a = accs[0];
    const own = ownByAcc(a.handle);
    const byTagged = {};
    for(const p of own){
      const combined = new Set([...(p.tagged||[]), ...(p.mentions||[])].filter(u => u && u !== a.handle));
      for(const u of combined){
        if(!byTagged[u]) byTagged[u]={n:0,engSum:0,reachSum:0,topPost:null};
        byTagged[u].n++;
        byTagged[u].engSum += p.engagement||0;
        byTagged[u].reachSum += p.views||0;
        if(!byTagged[u].topPost || (p.engagement||0)>(byTagged[u].topPost.engagement||0)) byTagged[u].topPost=p;
      }
    }
    const rows = Object.entries(byTagged).map(([u,v])=>({tagged:u,...v,avgEng:v.engSum/v.n}))
      .sort((a,b)=>b.avgEng-a.avgEng);
    if(!rows.length){el.innerHTML='<div class="muted">No outbound tags found</div>';return;}
    el.innerHTML='<table><thead><tr><th>Tagged account</th><th class="num">Times tagged</th><th class="num">Avg eng (those posts)</th><th class="num" title="Video views only — IG does not expose reach for static images/carousels">Reach (video)</th><th>Top post</th></tr></thead><tbody>'+
      rows.slice(0,25).map(r=>{
        const tp=r.topPost;
        const tpCell = tp ? `<a href="${escHtml(tp.url||'')}" target="_blank">${fmt(tp.engagement)} eng · ${tp.timestamp?.slice(0,10)} ↗</a>` : '—';
        const reachCell = r.reachSum>0 ? `<span>${fmt(r.reachSum)}</span>` : `<span class="muted">— <span style="font-size:10px;opacity:.6">static</span></span>`;
        return `<tr><td><a target="_blank" href="https://www.instagram.com/${escHtml(r.tagged)}/">@${escHtml(r.tagged)}</a></td><td class="num">${r.n}</td><td class="num">${fmt(r.avgEng)}</td><td class="num">${reachCell}</td><td>${tpCell}</td></tr>`;
      }).join('')+'</tbody></table>';
    return;
  }

  // MULTI-ACCOUNT MATRIX: rows = unique tagged accounts, columns = each tracked acc, cell = how often this acc tags target + avg eng
  const matrix = {};  // tagged -> {accCells:{handle:{n,engSum,reachSum,topPost}}, totalN, accHits}
  for(const a of accs){
    const own = ownByAcc(a.handle);
    for(const p of own){
      const combined = new Set([...(p.tagged||[]), ...(p.mentions||[])].filter(u=>u && u!==a.handle));
      for(const u of combined){
        if(!matrix[u]) matrix[u]={accCells:{}, totalN:0, accHits:0, totalEng:0};
        const m = matrix[u];
        if(!m.accCells[a.handle]){ m.accCells[a.handle]={n:0,engSum:0,reachSum:0,topPost:null}; m.accHits++; }
        const c = m.accCells[a.handle];
        c.n++; c.engSum += p.engagement||0; c.reachSum += p.views||0;
        if(!c.topPost || (p.engagement||0)>(c.topPost.engagement||0)) c.topPost=p;
        m.totalN++; m.totalEng += p.engagement||0;
      }
    }
  }
  const rows = Object.entries(matrix).map(([tagged,v])=>({tagged,...v}))
    .sort((a,b)=> b.accHits!==a.accHits ? b.accHits-a.accHits : b.totalN-a.totalN);
  if(!rows.length){el.innerHTML='<div class="muted">No outbound tags found</div>';return;}

  let html='<table class="tag-matrix"><thead><tr><th style="position:sticky;left:0;background:var(--card2);z-index:2">Tagged account</th><th class="num" title="How many of selected accounts tag this target">By</th>';
  for(const a of accs) html+=`<th class="num" style="min-width:130px"><span class="pill" style="background:${rgba(a.color,.18)};color:${a.color};white-space:nowrap;font-size:10px">@${escHtml(a.handle)}</span></th>`;
  html+='<th class="num">Total tags</th></tr></thead><tbody>';
  for(const r of rows.slice(0,30)){
    html+=`<tr><td style="position:sticky;left:0;background:var(--card)"><a target="_blank" href="https://www.instagram.com/${escHtml(r.tagged)}/">@${escHtml(r.tagged)}</a></td><td class="num"><strong>${r.accHits}</strong>/${accs.length}</td>`;
    for(const a of accs){
      const c = r.accCells[a.handle];
      if(!c){ html+='<td class="num"><span class="muted">—</span></td>'; continue; }
      const avgEng = c.n ? c.engSum/c.n : 0;
      const tp = c.topPost;
      const tpLink = tp && tp.url ? ` <a href="${escHtml(tp.url)}" target="_blank" style="font-size:11px;opacity:.7;text-decoration:none">↗</a>` : '';
      html+=`<td class="num" style="white-space:nowrap"><strong>${c.n}</strong> <span style="color:var(--mut);font-size:11px">· ${fmt(avgEng)} avg</span>${tpLink}</td>`;
    }
    html+=`<td class="num"><strong>${r.totalN}</strong></td></tr>`;
  }
  html+='</tbody></table>';
  html+='<div style="font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5">Sorted by <strong>accounts tagging this target</strong> first (shared targets at top — likely common partners/vendors/venues). Cell: <strong>tags</strong> · avg engagement on those posts · ↗ to top post.</div>';
  el.innerHTML=html;
}

// ---------- theme analysis ----------
const THEME_PALETTE = {
  'Project Launch':'#5b9cff','Investment':'#46d3a0','Event / Occasion':'#ffb454',
  'Real Estate Market':'#9d7aff','Business / Leadership':'#ff7ab6','Press / Media Coverage':'#52d4e5',
  'Behind the Scenes / Team':'#b8c5dc','Motivational / Inspirational':'#ff8c5a',
  'Partnership / Collaboration':'#7cffaa','Lifestyle / Personal':'#ffd166',
  'Cultural / Community':'#e07eff','Personal Storytelling':'#ffd6a0',
  'Uncategorized':'#5a6783',
};
function themeStats(arr){
  // returns sorted array of {theme, count, sumEng, avgEng}
  const m={};
  for(const p of arr){
    const t=p.theme||'Uncategorized';
    if(!m[t]) m[t]={count:0,sumEng:0};
    m[t].count++; m[t].sumEng+=p.engagement;
  }
  return Object.entries(m).map(([t,v])=>({theme:t,count:v.count,sumEng:v.sumEng,avgEng:v.sumEng/v.count}))
    .sort((a,b)=>b.count-a.count);
}
function themeMixChart(accs){
  const el=document.getElementById('ch_themes');
  // For drill-down (1 acc): single donut. For multi-account: stacked bar.
  if(accs.length===1){
    const stats=themeStats(ownByAcc(accs[0].handle));
    new Chart(el,{type:'doughnut',
      data:{labels:stats.map(s=>s.theme),datasets:[{data:stats.map(s=>s.count),backgroundColor:stats.map(s=>THEME_PALETTE[s.theme]||'#888'),borderWidth:0}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{boxWidth:10,boxHeight:10,font:{size:11}}},tooltip:{callbacks:{label:c=>`${c.label}: ${c.parsed} posts (${(c.parsed/stats.reduce((s,x)=>s+x.count,0)*100).toFixed(1)}%)`}}},cutout:'55%'}});
  } else {
    // Stacked horizontal bar: one row per account, segments per theme
    const allThemes=[...new Set(accs.flatMap(a=>themeStats(ownByAcc(a.handle)).map(s=>s.theme)))];
    const datasets=allThemes.map(t=>({label:t,backgroundColor:THEME_PALETTE[t]||'#888',
      data:accs.map(a=>{const s=themeStats(ownByAcc(a.handle)).find(x=>x.theme===t);return s?s.count:0;})}));
    new Chart(el,{type:'bar',data:{labels:accs.map(a=>'@'+a.handle),datasets},
      options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,beginAtZero:true},y:{stacked:true}},plugins:{legend:{position:'bottom',labels:{boxWidth:10,boxHeight:10,font:{size:11}}}}}});
  }
}
function themeEngagementChart(accs){
  const el=document.getElementById('ch_theme_eng');
  if(accs.length===1){
    const stats=themeStats(ownByAcc(accs[0].handle)).filter(s=>s.count>=2);
    stats.sort((a,b)=>b.avgEng-a.avgEng);
    new Chart(el,{type:'bar',
      data:{labels:stats.map(s=>s.theme),datasets:[{label:'Avg engagement',data:stats.map(s=>Math.round(s.avgEng)),backgroundColor:stats.map(s=>THEME_PALETTE[s.theme]||'#888'),borderRadius:6}]},
      options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmt(c.parsed.x)+' avg eng · '+stats[c.dataIndex].count+' posts'}}},scales:{x:{beginAtZero:true,ticks:{callback:v=>fmt(v)}}}}});
  } else {
    // Group by theme, one bar group per theme, datasets per account
    const allThemes=[...new Set(accs.flatMap(a=>themeStats(ownByAcc(a.handle)).filter(s=>s.count>=2).map(s=>s.theme)))];
    const datasets=accs.map(a=>{const stats=themeStats(ownByAcc(a.handle));
      return {label:'@'+a.handle,backgroundColor:a.color,borderRadius:6,
        data:allThemes.map(t=>{const s=stats.find(x=>x.theme===t);return s?Math.round(s.avgEng):0;})};});
    new Chart(el,{type:'bar',data:{labels:allThemes,datasets},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{callback:v=>fmt(v)}}}}});
  }
}
function themeLeaderboardTable(accs){
  const el=document.getElementById('tbl_themes');
  // Single account → aggregate view (existing behavior). Multi-account → per-account columns.
  if(accs.length<=1){
    const m={};
    for(const a of accs) for(const p of ownByAcc(a.handle)){
      const t=p.theme||'Uncategorized';
      if(!m[t]) m[t]={count:0,sumEng:0,sumViews:0,topPost:null};
      m[t].count++; m[t].sumEng+=p.engagement; m[t].sumViews+=(p.views||0);
      if(!m[t].topPost || p.engagement>m[t].topPost.engagement) m[t].topPost=p;
    }
    const rows=Object.entries(m).map(([t,v])=>({theme:t,...v,avgEng:v.sumEng/v.count})).sort((a,b)=>b.count-a.count);
    if(!rows.length){el.innerHTML='<div class="muted">No theme data</div>';return;}
    const totalPosts=rows.reduce((s,x)=>s+x.count,0);
    el.innerHTML='<table><thead><tr><th>Theme</th><th class="num">Posts</th><th class="num">% of total</th><th class="num">Avg eng</th><th class="num" title="Video views only — IG does not expose reach for static images/carousels">Reach (video)</th><th>Top post in theme</th></tr></thead><tbody>'+
      rows.map(r=>{
        const tp=r.topPost;
        const tpLink = tp && tp.url ? `<a href="${escHtml(tp.url)}" target="_blank">${fmt(tp.engagement)} eng · ${tp.timestamp?.slice(0,10)} ↗</a>` : '—';
        const color = THEME_PALETTE[r.theme] || '#888';
        return `<tr><td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle"></span>${escHtml(r.theme)}</td><td class="num">${r.count}</td><td class="num">${(r.count/totalPosts*100).toFixed(1)}%</td><td class="num">${fmt(r.avgEng)}</td><td class="num">${r.sumViews?fmt(r.sumViews):'—'}</td><td>${tpLink}</td></tr>`;
      }).join('')+'</tbody></table>';
    return;
  }

  // Multi-account comparison view: per-theme × per-account matrix
  // Build a nested structure: themes[theme][handle] = {count, sumEng, sumViews, topPost}
  const byTheme = {};
  const accTotals = {};
  for(const a of accs){
    accTotals[a.handle] = 0;
    for(const p of ownByAcc(a.handle)){
      const t = p.theme || 'Uncategorized';
      if(!byTheme[t]) byTheme[t] = {};
      if(!byTheme[t][a.handle]) byTheme[t][a.handle] = {count:0, sumEng:0, sumViews:0, topPost:null};
      const cell = byTheme[t][a.handle];
      cell.count++;
      cell.sumEng += p.engagement;
      cell.sumViews += (p.views || 0);
      if(!cell.topPost || p.engagement > cell.topPost.engagement) cell.topPost = p;
      accTotals[a.handle]++;
    }
  }
  // Sort themes by total posts descending
  const themesByVolume = Object.entries(byTheme).map(([t,perAcc])=>{
    const totalCount = Object.values(perAcc).reduce((s,x)=>s+x.count,0);
    const totalEng   = Object.values(perAcc).reduce((s,x)=>s+x.sumEng,0);
    return {theme:t, totalCount, totalEng, perAcc};
  }).sort((a,b)=>b.totalCount-a.totalCount);

  if(!themesByVolume.length){el.innerHTML='<div class="muted">No theme data</div>';return;}

  // Build header
  let html = '<table><thead><tr><th>Theme</th><th class="num">Total posts</th>';
  for(const a of accs){
    html += `<th class="num"><span class="pill" style="background:${rgba(a.color,.18)};color:${a.color};white-space:nowrap">@${a.handle}</span></th>`;
  }
  html += '</tr></thead><tbody>';

  // Body
  for(const row of themesByVolume){
    const color = THEME_PALETTE[row.theme] || '#888';
    html += `<tr><td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle"></span>${escHtml(row.theme)}</td><td class="num"><strong>${row.totalCount}</strong></td>`;
    // Find best avg-eng account this row (for highlight)
    let bestHandle = null, bestAvg = 0;
    for(const a of accs){
      const c = row.perAcc[a.handle];
      if(c && c.count>=2){
        const avg = c.sumEng/c.count;
        if(avg>bestAvg){ bestAvg=avg; bestHandle=a.handle; }
      }
    }
    for(const a of accs){
      const c = row.perAcc[a.handle];
      if(!c){
        html += '<td class="num"><span class="muted">—</span></td>';
        continue;
      }
      const avgEng = c.sumEng/c.count;
      const pct = accTotals[a.handle] ? (c.count/accTotals[a.handle]*100).toFixed(0) : 0;
      const isBest = a.handle===bestHandle;
      const bestMark = isBest ? `<span style="color:${a.color};margin-left:4px" title="Highest avg engagement on this theme">▲</span>` : '';
      const tp = c.topPost;
      const tpLink = tp && tp.url ? `<br/><a href="${escHtml(tp.url)}" target="_blank" style="font-size:10px;opacity:.7">top: ${fmt(tp.engagement)} ↗</a>` : '';
      html += `<td class="num"><div><strong>${c.count}</strong> <span style="color:var(--mut);font-size:11px">(${pct}%)</span>${bestMark}</div><div style="font-size:11px;color:var(--mut)">${fmt(avgEng)} avg eng</div>${tpLink}</td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  html += '<div style="font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5">Cell shows: <strong>posts</strong> (% of that account\'s total) · avg engagement on those posts · top post link.  ▲ marks the account with the highest avg engagement in that theme (min 2 posts).</div>';
  el.innerHTML = html;
}

// ---------- new charts/sections ----------
function calendarHeatmap(a){
  const id='cal_'+cssId(a.handle);
  const el=document.getElementById(id); if(!el) return;
  const arr=ownByAcc(a.handle); if(!arr.length){el.innerHTML='<div class="muted">No posts</div>';return;}
  // Build daily count for past 52 weeks ending today
  const today=new Date(); today.setUTCHours(0,0,0,0);
  const dayMs=86400000;
  // Find earliest in window (max of 52w ago and account's earliest post)
  const earliest=Math.min(...arr.map(p=>p.ts_ms).filter(Boolean));
  const start = new Date(Math.max(earliest, today.getTime()-365*dayMs));
  // Align to previous Monday
  const startDay=(start.getUTCDay()+6)%7;
  start.setUTCDate(start.getUTCDate()-startDay); start.setUTCHours(0,0,0,0);
  const weeks=Math.ceil((today.getTime()-start.getTime())/dayMs/7)+1;
  const counts={};
  for(const p of arr){ if(!p.ts_ms) continue;
    const d=new Date(p.ts_ms); const key=d.toISOString().slice(0,10);
    if(!counts[key]) counts[key]={n:0,eng:0};
    counts[key].n++; counts[key].eng+=p.engagement;
  }
  const maxN=Math.max(...Object.values(counts).map(x=>x.n),1);
  const dows=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  // Render as a grid: 7 rows × N cols
  const cell=12, gap=2;
  const w=weeks*(cell+gap), h=7*(cell+gap)+18;
  let svg=`<svg width="${w+40}" height="${h+18}" style="font:10px sans-serif;color:#8895ad">`;
  // Month labels
  let lastMonth=-1;
  for(let wk=0;wk<weeks;wk++){
    const d=new Date(start.getTime()+wk*7*dayMs);
    if(d.getUTCMonth()!==lastMonth && d.getUTCDate()<=7){
      svg+=`<text x="${40+wk*(cell+gap)}" y="10" fill="#8895ad">${d.toLocaleString('en-GB',{month:'short',timeZone:'Asia/Dubai'})}</text>`;
      lastMonth=d.getUTCMonth();
    }
  }
  // DoW labels (Mon/Wed/Fri only to save space)
  for(let dy=0;dy<7;dy++){
    if(dy===0||dy===2||dy===4) svg+=`<text x="0" y="${18+dy*(cell+gap)+10}" fill="#8895ad">${dows[dy]}</text>`;
  }
  // Cells
  for(let wk=0;wk<weeks;wk++){
    for(let dy=0;dy<7;dy++){
      const d=new Date(start.getTime()+wk*7*dayMs+dy*dayMs);
      if(d>today) continue;
      const key=d.toISOString().slice(0,10);
      const stats=counts[key];
      const n=stats?stats.n:0;
      const alpha=n?(.2+.8*n/maxN):.05;
      const fill=n?rgba(a.color,alpha):'#1a2238';
      const title=`${key} · ${n} post${n!==1?'s':''}${stats?' · '+fmt(stats.eng)+' eng':''}`;
      svg+=`<rect x="${40+wk*(cell+gap)}" y="${18+dy*(cell+gap)}" width="${cell}" height="${cell}" fill="${fill}" rx="2"><title>${title}</title></rect>`;
    }
  }
  // Legend
  svg+=`<text x="${40}" y="${h+10}" fill="#8895ad">Less</text>`;
  for(let i=0;i<5;i++){
    const alpha=.2+.8*i/4;
    svg+=`<rect x="${75+i*(cell+gap)}" y="${h}" width="${cell}" height="${cell}" fill="${rgba(a.color,alpha)}" rx="2"/>`;
  }
  svg+=`<text x="${75+5*(cell+gap)+4}" y="${h+10}" fill="#8895ad">More</text>`;
  svg+='</svg>';
  el.innerHTML=`<div style="overflow-x:auto;padding:6px 0">${svg}</div>`;
}

function locationsTable(accs){
  const m={};
  for(const a of accs) for(const p of ownByAcc(a.handle)){
    if(!p.location) continue;
    if(!m[p.location]) m[p.location]={n:0,eng:0,accs:new Set()};
    m[p.location].n++; m[p.location].eng+=p.engagement; m[p.location].accs.add(a.handle);
  }
  const rows=Object.entries(m).sort((a,b)=>b[1].n-a[1].n).slice(0,10);
  const el=document.getElementById('tbl_loc');
  if(!rows.length){el.innerHTML='<div class="muted">No geo-tagged posts</div>';return;}
  el.innerHTML='<table><thead><tr><th>Location</th><th class="num">Posts</th><th class="num">Avg eng</th></tr></thead><tbody>'+
    rows.map(([loc,v])=>`<tr><td>${escHtml(loc)}</td><td class="num">${v.n}</td><td class="num">${fmt(v.eng/v.n)}</td></tr>`).join('')+'</tbody></table>';
}

function mentionsTable(accs){
  // Aggregate: per mentioned-account, collect the list of posts (with full metadata)
  // where that account was mentioned. Sorted by recency so the latest mention appears first.
  const m={};
  for(const a of accs) for(const p of ownByAcc(a.handle)){
    for(const u of (p.mentions||[])){
      if(u===a.handle) continue;
      if(!m[u]) m[u]={n:0,eng:0,posts:[]};
      m[u].n++; m[u].eng+=(p.engagement||0); m[u].posts.push(p);
    }
  }
  // Sort posts within each mention bucket by recency
  for(const u in m){ m[u].posts.sort((a,b)=>(b.ts_ms||0)-(a.ts_ms||0)); }
  const rows=Object.entries(m).filter(([,v])=>v.n>=1).sort((a,b)=>b[1].n-a[1].n).slice(0,12);
  const el=document.getElementById('tbl_mentions');
  if(!rows.length){el.innerHTML='<div class="muted">No outbound mentions</div>';return;}

  // Render: main row + expandable details row showing all mention-posts (thumbnails, captions, eng, links)
  let html = '<table><thead><tr><th></th><th>@account</th><th class="num">Mentions</th><th class="num">Avg eng</th><th>Latest post</th></tr></thead><tbody>';
  rows.forEach(([u,v],i)=>{
    const latest = v.posts[0];
    const latestThumb = latest && latest.displayUrl
      ? `<a href="${escHtml(latest.url||'')}" target="_blank"><img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${escHtml(latest.displayUrl)}" onerror="this.style.display='none'" style="width:32px;height:32px;border-radius:4px;object-fit:cover"/></a>`
      : '';
    const latestCap = latest ? escHtml(latest.caption||'').slice(0,80) : '';
    const latestDate = latest && latest.timestamp ? latest.timestamp.slice(0,10) : '';
    const latestEng = latest ? fmt(latest.engagement) : '';
    const latestLink = latest && latest.url ? `<a href="${escHtml(latest.url)}" target="_blank" style="color:#5b9cff;text-decoration:none">↗</a>` : '';
    // Build all-posts expansion list (full thumbnail strip)
    const allPostsHtml = v.posts.slice(0,6).map(p=>{
      const thumb = p.displayUrl
        ? `<img loading="lazy" referrerpolicy="no-referrer" src="${escHtml(p.displayUrl)}" onerror="this.style.display='none'" style="width:54px;height:54px;border-radius:5px;object-fit:cover;flex-shrink:0"/>`
        : `<div style="width:54px;height:54px;border-radius:5px;background:#1a2238;flex-shrink:0"></div>`;
      const d = p.timestamp ? p.timestamp.slice(0,10) : '';
      const cap = escHtml(p.caption||'').slice(0,110);
      const acc = accs.length>1 ? `<span class="pill" style="background:${rgba(colorOf(p.account),.2)};color:${colorOf(p.account)};font-size:9px;margin-right:6px">@${escHtml(p.account)}</span>` : '';
      return `<a href="${escHtml(p.url||'')}" target="_blank" style="display:flex;gap:10px;padding:6px;border-radius:6px;text-decoration:none;color:inherit;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04)" onmouseover="this.style.background='rgba(91,156,255,.06)'" onmouseout="this.style.background='rgba(255,255,255,.02)'">
        ${thumb}
        <div style="flex:1;min-width:0">
          <div style="font-size:11px;color:#8895ad;display:flex;align-items:center;gap:6px">${acc}${d} · ${p.type} · <span style="color:#e8eef9;font-weight:600">${fmt(p.engagement)} eng</span></div>
          <div style="font-size:11.5px;color:#cbd5e1;line-height:1.4;margin-top:2px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${cap}</div>
        </div>
        <div style="color:#5b9cff;font-size:14px;align-self:center">↗</div>
      </a>`;
    }).join('');
    const moreNote = v.posts.length > 6 ? `<div style="font-size:11px;color:#5a6783;text-align:center;padding:6px 0">+ ${v.posts.length - 6} more</div>` : '';
    html += `<tr class="mentions-row" data-idx="${i}" style="cursor:pointer">
      <td style="width:24px"><span class="mentions-toggle" style="color:#5a6783;font-size:11px;transition:transform .15s;display:inline-block">▶</span></td>
      <td><a target="_blank" href="https://www.instagram.com/${escHtml(u)}/" onclick="event.stopPropagation()">@${escHtml(u)}</a></td>
      <td class="num">${v.n}</td>
      <td class="num">${fmt(v.eng/v.n)}</td>
      <td style="font-size:11px;color:#8895ad">${latestThumb} <span style="vertical-align:middle">${latestDate} · ${latestEng} eng ${latestLink}</span></td>
    </tr>
    <tr class="mentions-detail" data-idx="${i}" style="display:none"><td colspan="5" style="padding:8px 12px 14px 36px;background:rgba(255,255,255,.015)">
      <div style="display:grid;grid-template-columns:1fr;gap:6px">${allPostsHtml}</div>
      ${moreNote}
    </td></tr>`;
  });
  html += '</tbody></table>';
  html += '<div style="font-size:11px;color:#5a6783;margin-top:6px">Click any row to expand the full post list where this account was mentioned.</div>';
  el.innerHTML = html;
  // Wire click-to-expand
  el.querySelectorAll('.mentions-row').forEach(tr=>{
    tr.addEventListener('click', ()=>{
      const idx = tr.dataset.idx;
      const detail = el.querySelector(`.mentions-detail[data-idx="${idx}"]`);
      const toggle = tr.querySelector('.mentions-toggle');
      if(detail.style.display === 'none'){
        detail.style.display = '';
        toggle.style.transform = 'rotate(90deg)';
        toggle.style.color = '#5b9cff';
      } else {
        detail.style.display = 'none';
        toggle.style.transform = 'rotate(0deg)';
        toggle.style.color = '#5a6783';
      }
    });
  });
}

function standoutPosts(accs){
  const el=document.getElementById('tbl_standouts');
  const rows=[];
  const pinnedExcluded=[];
  for(const a of accs){
    // Exclude pinned posts from the "standout" pool — they accumulate engagement unfairly over months
    const arrAll=ownByAcc(a.handle);
    const arr=arrAll.filter(p=>!p.isPinned); if(arr.length<5) continue;
    arrAll.filter(p=>p.isPinned).forEach(p=>pinnedExcluded.push({a,p}));
    const median=med(arr.map(p=>p.engagement));
    if(median<=0) continue;
    const standouts=arr.filter(p=>p.engagement >= 3*median).sort((a,b)=>b.engagement-a.engagement).slice(0,10);
    for(const p of standouts){
      rows.push({a,p,lift:p.engagement/median});
    }
  }
  rows.sort((a,b)=>b.lift-a.lift);
  if(!rows.length){el.innerHTML='<div class="muted">No posts hit ≥3× normal yet</div>';return;}
  const pinnedFootnote = pinnedExcluded.length
    ? `<div style="font-size:11px;color:var(--mut);margin:6px 0 10px">Excluded ${pinnedExcluded.length} pinned post${pinnedExcluded.length>1?'s':''} (long-running, inflate engagement unfairly). Shown separately below.</div>`
    : '';
  let html = pinnedFootnote +
    '<table><thead><tr><th></th><th>Date</th><th>Account</th><th>Type</th><th class="num">Engagement</th><th class="num">vs median</th><th class="num">Views</th><th>Caption</th><th>↗</th></tr></thead><tbody>'+
    rows.slice(0,25).map(({a,p,lift})=>{
      const acc=`<span class="pill" style="background:${rgba(a.color,.2)};color:${a.color}">@${p.account}</span>`;
      const d=p.timestamp?p.timestamp.slice(0,10):'';
      const cap=escHtml(p.caption||'').slice(0,140);
      const img=p.displayUrl?`<a href="${escHtml(p.url)}" target="_blank"><img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${escHtml(p.displayUrl)}" onerror="this.style.display='none'"/></a>`:'';
      const boost = p.likelyBoosted ? ' <span class="pill" style="background:rgba(255,180,84,.18);color:#ffb454;font-size:10px">Likely boosted</span>' : '';
      return `<tr><td>${img}</td><td>${d}</td><td>${acc}</td><td>${p.type}${boost}</td><td class="num">${fmt(p.engagement)}</td><td class="num"><strong>${lift.toFixed(1)}×</strong></td><td class="num">${p.views?fmt(p.views):'—'}</td><td>${cap}</td><td>${p.url?`<a href="${escHtml(p.url)}" target="_blank">↗</a>`:''}</td></tr>`;
    }).join('')+'</tbody></table>';
  if(pinnedExcluded.length){
    html += '<details style="margin-top:14px"><summary style="cursor:pointer;color:var(--mut);font-size:12px">Show pinned posts (excluded from ranking)</summary><table style="margin-top:8px"><thead><tr><th></th><th>Date</th><th>Account</th><th>Type</th><th class="num">Engagement</th><th class="num">Views</th><th>Caption</th></tr></thead><tbody>'+
      pinnedExcluded.map(({a,p})=>{
        const acc=`<span class="pill" style="background:${rgba(a.color,.2)};color:${a.color}">@${p.account}</span>`;
        const d=p.timestamp?p.timestamp.slice(0,10):'';
        const cap=escHtml(p.caption||'').slice(0,140);
        const img=p.displayUrl?`<a href="${escHtml(p.url)}" target="_blank"><img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${escHtml(p.displayUrl)}" onerror="this.style.display='none'"/></a>`:'';
        return `<tr><td>${img}</td><td>${d}</td><td>${acc} <span class="pill" style="background:rgba(91,156,255,.18);color:#5b9cff;font-size:10px">📌 PINNED</span></td><td>${p.type}</td><td class="num">${fmt(p.engagement)}</td><td class="num">${p.views?fmt(p.views):'—'}</td><td>${cap}</td></tr>`;
      }).join('')+'</tbody></table></details>';
  }
  el.innerHTML = html;
}

// ---------- scorecard ----------
function scorecard(accs){
  const metrics = [
    ['Posts',           a=>ownByAcc(a.handle).length, fmt],
    ['Avg likes',       a=>avg(ownByAcc(a.handle),'likes'), fmt],
    ['Avg comments',    a=>avg(ownByAcc(a.handle),'comments'), fmt],
    ['Median eng.',     a=>med(ownByAcc(a.handle).map(p=>p.engagement)), fmt],
    ['Avg reel views',  a=>avg(ownByAcc(a.handle).filter(p=>p.views>0),'views'), fmt],
    ['Engagement rate', a=>avg(ownByAcc(a.handle).filter(p=>p.er!=null).map(p=>({x:p.er})),'x'), fmtPc],
    ['View→like',       a=>avg(ownByAcc(a.handle).filter(p=>p.views>0).map(p=>({x:p.vlr||0})),'x'), fmtPc],
    ['Caption length',  a=>avg(ownByAcc(a.handle),'capLen'), v=>Math.round(v)+' ch'],
    ['Hashtags/post',   a=>avg(ownByAcc(a.handle).map(p=>({x:p.hashtags.length})),'x'), v=>v.toFixed(1)],
    ['Video duration',  a=>avg(ownByAcc(a.handle).filter(p=>p.duration>0),'duration'), v=>v?Math.round(v)+'s':'—'],
  ];
  let html='';
  for(const [label,fn,f] of metrics){
    const vals = accs.map(a=>({a,v:fn(a)||0}));
    const mx = Math.max(...vals.map(x=>x.v),1);
    html += `<h4>${label}</h4>`;
    for(const {a,v} of vals){
      html += `<div class="row"><div class="name">${avatarHTML(a)}<span>@${a.handle}</span></div>
        <div class="barwrap"><span style="width:${(v/mx*100).toFixed(1)}%;background:${a.color}"></span></div>
        <div class="val">${f(v)}</div></div>`;
    }
  }
  document.getElementById('scorecard').innerHTML = html;
}

// ---------- cadence (weekly) ----------
function weekKey(ms){
  const d=new Date(ms); const t=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()));
  const dn=(t.getUTCDay()+6)%7; t.setUTCDate(t.getUTCDate()-dn+3);
  const ft=new Date(Date.UTC(t.getUTCFullYear(),0,4));
  const w=1+Math.round(((t-ft)/864e5-3+((ft.getUTCDay()+6)%7))/7);
  return t.getUTCFullYear()+'-W'+String(w).padStart(2,'0');
}
function cadenceChart(accs){
  const b={};
  for(const p of segOwn()){ if(!p.ts_ms) continue; const k=weekKey(p.ts_ms); b[k]=b[k]||{}; b[k][p.account]=(b[k][p.account]||0)+1; }
  const labels=Object.keys(b).sort();
  const ds=accs.map(a=>({label:'@'+a.handle,data:labels.map(l=>b[l][a.handle]||0),borderColor:a.color,backgroundColor:rgba(a.color,.15),tension:.35,fill:true,pointRadius:3}));
  new Chart(document.getElementById('ch_cad'),{type:'line',data:{labels,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{y:{beginAtZero:true,ticks:{precision:0}},x:{grid:{display:false}}}}});
}

function ownTaggedChart(accs){
  const labels=accs.map(a=>'@'+a.handle);
  const own=accs.map(a=>a.own);
  const tag=accs.map(a=>a.total-a.own);
  new Chart(document.getElementById('ch_owntag'),{type:'bar',
    data:{labels,datasets:[
      {label:'Own',data:own,backgroundColor:'#46d3a0',borderRadius:6},
      {label:'Tagged in',data:tag,backgroundColor:'#ffb454',borderRadius:6}]},
    options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,beginAtZero:true},y:{stacked:true}},plugins:{legend:{position:'bottom'}}}});
}

function heatmap(a){
  const id='ch_heat_'+cssId(a.handle);
  const counts={};
  for(const p of ownByAcc(a.handle)){ if(!p.ts_ms) continue;
    const d=new Date(p.ts_ms+GST_OFFSET_MS); const dow=(d.getUTCDay()+6)%7; const h=d.getUTCHours();
    const k=dow+'_'+h; counts[k]=(counts[k]||0)+1; }
  const data=[]; let mx=0;
  for(let dow=0;dow<7;dow++) for(let h=0;h<24;h++){ const v=counts[dow+'_'+h]||0; data.push({x:h,y:dow,v}); if(v>mx) mx=v; }
  const dows=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  new Chart(document.getElementById(id),{type:'matrix',
    data:{datasets:[{label:'@'+a.handle,data,backgroundColor:c=>{
      const v=c.raw.v; if(!v) return '#141b2b';
      const alpha=Math.min(1,.2+.8*v/Math.max(1,mx));
      return rgba(a.color,alpha);
    },borderColor:'#0e1320',borderWidth:1,width:c=>(c.chart.chartArea?.width||0)/24-2,height:c=>(c.chart.chartArea?.height||0)/7-2}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{title:i=>dows[i[0].raw.y]+' '+String(i[0].raw.x).padStart(2,'0')+':00',label:c=>c.raw.v+' post(s)'}}},
      scales:{x:{type:'linear',min:-0.5,max:23.5,ticks:{stepSize:3,callback:v=>String(v).padStart(2,'0')},grid:{display:false}},y:{type:'linear',min:-0.5,max:6.5,reverse:true,ticks:{stepSize:1,callback:v=>dows[v]||''},grid:{display:false}}}}});
}

function dowChart(accs){
  const dows=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  function dowAvg(arr){ const s=new Array(7).fill(0),c=new Array(7).fill(0);
    for(const p of arr){ if(!p.ts_ms) continue; const i=(new Date(p.ts_ms+GST_OFFSET_MS).getUTCDay()+6)%7; s[i]+=p.engagement; c[i]++; }
    return s.map((x,i)=>c[i]?Math.round(x/c[i]):0); }
  const ds=accs.map(a=>({label:'@'+a.handle,data:dowAvg(ownByAcc(a.handle)),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_dow'),{type:'bar',
    data:{labels:dows,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true}}}});
}

function gapChart(accs){
  const bins=[0,1,2,3,5,7,10,14,21,30,60];
  const labs=bins.map((b,i)=>i===bins.length-1?b+'+ d':b+'-'+bins[i+1]+'d');
  function hist(arr){ const ts=arr.map(p=>p.ts_ms).filter(Boolean).sort((a,b)=>a-b); const g=[]; for(let i=1;i<ts.length;i++) g.push((ts[i]-ts[i-1])/864e5);
    const c=new Array(bins.length).fill(0); for(const x of g) for(let i=bins.length-1;i>=0;i--){if(x>=bins[i]){c[i]++;break;}} return c; }
  const ds=accs.map(a=>({label:'@'+a.handle,data:hist(ownByAcc(a.handle)),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_gap'),{type:'bar',data:{labels:labs,datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
}

function typeMixChart(accs){
  const types=[...new Set(segOwn().map(p=>p.type))];
  const ds=accs.map(a=>({label:'@'+a.handle,data:types.map(t=>ownByAcc(a.handle).filter(p=>p.type===t).length),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_type'),{type:'bar',data:{labels:types,datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true}}}});
}

function typeMetricChart(accs,id,key,log){
  const types=[...new Set(segOwn().map(p=>p.type))];
  function avgOf(h,t){ const xs=ownByAcc(h).filter(p=>p.type===t); return xs.length?Math.round(xs.reduce((s,p)=>s+(p[key]||0),0)/xs.length):0; }
  const ds=accs.map(a=>({label:'@'+a.handle,data:types.map(t=>avgOf(a.handle,t)),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById(id),{type:'bar',data:{labels:types,datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,type:log?'logarithmic':'linear'}}}});
}

function viewsDistChart(accs){
  const bks=[0,1e3,5e3,1e4,5e4,1e5,5e5,1e6,5e6];
  const labs=bks.map((b,i)=>i===bks.length-1?fmt(b)+'+':fmt(b)+'-'+fmt(bks[i+1]));
  function hist(arr){ const c=new Array(bks.length).fill(0); for(const p of arr){ if(!p.views) continue; for(let i=bks.length-1;i>=0;i--){if(p.views>=bks[i]){c[i]++;break;}} } return c; }
  const ds=accs.map(a=>({label:'@'+a.handle,data:hist(ownByAcc(a.handle).filter(p=>p.views>0)),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_views'),{type:'bar',data:{labels:labs,datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
}

function vlrChart(accs){
  const ds=accs.map(a=>({
    label:'@'+a.handle,
    data:[avg(ownByAcc(a.handle).filter(p=>p.vlr!=null), 'vlr') * 100], 
    backgroundColor:a.color, 
    borderRadius:6
  }));
  new Chart(document.getElementById('ch_vlr'),{
    type:'bar',
    data:{labels:['Avg View-to-Like Rate (%)'],datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(2)+'%'}}},
      scales:{y:{beginAtZero:true,title:{display:true,text:'Conversion Rate (%)'},ticks:{callback:v=>v+'%'}}}}
  });
}

function engTimeChart(accs){
  const allMonths = new Set();
  const ds = accs.map(a=>{
    const posts = ownByAcc(a.handle).filter(p=>p.ts_ms && p.engagement != null);
    const byMonth = {};
    for(const p of posts){
      const m = new Date(p.ts_ms).toISOString().slice(0,7);
      allMonths.add(m);
      if(!byMonth[m]) byMonth[m] = {sum:0, count:0};
      byMonth[m].sum += p.engagement;
      byMonth[m].count++;
    }
    return {
      label: '@'+a.handle,
      borderColor: a.color,
      backgroundColor: a.color,
      tension: 0.4,
      fill: false,
      borderWidth: 3,
      pointRadius: 4,
      dataMap: byMonth
    };
  });
  
  const labels = Array.from(allMonths).sort();
  ds.forEach(d => {
    d.data = labels.map(l => d.dataMap[l] ? d.dataMap[l].sum / d.dataMap[l].count : null);
  });

  new Chart(document.getElementById('ch_engt'),{
    type:'line',
    data:{labels:labels,datasets:ds},
    options:{
      responsive:true,
      maintainAspectRatio:false,
      spanGaps: true,
      plugins:{legend:{position:'bottom'}, tooltip:{mode: 'index', intersect: false}},
      scales:{
        x:{title:{display:true,text:'Month'}},
        y:{type:'logarithmic', title:{display:true,text:'Avg Engagement (Likes + Comments)'}}
      }
    }
  });
}

function durChart(accs){
  const ds=accs.map(a=>({label:'@'+a.handle,backgroundColor:a.color,
    data:ownByAcc(a.handle).filter(p=>p.duration>0&&p.views>0).map(p=>({x:p.duration,y:p.views}))}));
  new Chart(document.getElementById('ch_dur'),{type:'scatter',data:{datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},
      scales:{x:{title:{display:true,text:'Duration (s)'},beginAtZero:true},y:{type:'logarithmic',title:{display:true,text:'Views'}}}}});
}

function capEngChart(accs){
  const ds=accs.map(a=>({label:'@'+a.handle,backgroundColor:a.color,
    data:ownByAcc(a.handle).filter(p=>p.capLen>0).map(p=>({x:p.capLen,y:Math.max(1,p.engagement)}))}));
  new Chart(document.getElementById('ch_cap'),{type:'scatter',data:{datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},
      scales:{x:{title:{display:true,text:'Caption length (chars)'}},y:{type:'logarithmic',title:{display:true,text:'Engagement'}}}}});
}

function slidesChart(accs){
  function buckets(arr){ const m={}; for(const p of arr) m[p.slides]=(m[p.slides]||[]).concat(p.engagement);
    return Object.keys(m).sort((a,b)=>a-b).map(k=>({k:+k,avg:m[k].reduce((s,x)=>s+x,0)/m[k].length})); }
  const labs=[...new Set(accs.flatMap(a=>ownByAcc(a.handle).filter(p=>p.slides>0).map(p=>p.slides)))].sort((a,b)=>a-b);
  const ds=accs.map(a=>{const b=buckets(ownByAcc(a.handle).filter(p=>p.slides>0)); return {label:'@'+a.handle,data:labs.map(l=>{const x=b.find(x=>x.k===l);return x?Math.round(x.avg):0;}),backgroundColor:a.color,borderRadius:6};});
  new Chart(document.getElementById('ch_slides'),{type:'bar',data:{labels:labs.map(l=>l+' slides'),datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true}}}});
}

function audioMixChart(accs){
  function counts(arr){ let o=0,l=0,u=0; for(const p of arr.filter(x=>x.type==='Reel'||x.type==='Video')){ if(p.usesOriginal===true) o++; else if(p.usesOriginal===false) l++; else u++; } return [o,l,u]; }
  const ds=accs.map(a=>({label:'@'+a.handle,data:counts(ownByAcc(a.handle)),backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_audio'),{type:'bar',data:{labels:['Original','Licensed','Unknown'],datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
}

function audioPerfChart(accs){
  function perf(arr,flag){const xs=arr.filter(p=>(p.type==='Reel'||p.type==='Video')&&p.usesOriginal===flag);return Math.round(avg(xs,'views'));}
  const ds=accs.map(a=>({label:'@'+a.handle,data:[perf(ownByAcc(a.handle),true),perf(ownByAcc(a.handle),false)],backgroundColor:a.color,borderRadius:6}));
  new Chart(document.getElementById('ch_audio_perf'),{type:'bar',data:{labels:['Original','Licensed'],datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'},tooltip:{callbacks:{label:c=>c.dataset.label+': '+fmt(c.parsed.y)}}},scales:{y:{beginAtZero:true,type:'logarithmic'}}}});
}

function topSongs(){
  const m={};
  for(const p of segOwn()){ if(!p.song) continue; const k=p.song+' — '+(p.artist||'—'); if(!m[k]) m[k]={n:0,e:0}; m[k].n++; m[k].e+=p.engagement; }
  const rows=Object.entries(m).sort((a,b)=>b[1].n-a[1].n).slice(0,10);
  if(!rows.length){ document.getElementById('tbl_songs').innerHTML='<div class="muted">No music metadata</div>'; return; }
  document.getElementById('tbl_songs').innerHTML='<table><thead><tr><th>Song</th><th class="num">Uses</th><th class="num">Avg eng</th></tr></thead><tbody>'+
    rows.map(([k,v])=>`<tr><td>${escHtml(k)}</td><td class="num">${v.n}</td><td class="num">${fmt(v.e/v.n)}</td></tr>`).join('')+'</tbody></table>';
}

// --- ranked lists with per-tab account ---
function tally(arr,field){ const m={}; for(const p of arr) for(const v of (p[field]||[])) m[v]=(m[v]||0)+1; return Object.entries(m).sort((a,b)=>b[1]-a[1]); }
function effective(arr,field){
  const m={};
  for(const p of arr) for(const v of (p[field]||[])){ if(!m[v]) m[v]={n:0,e:0}; m[v].n++; m[v].e+=p.engagement; }
  return Object.entries(m).filter(([,x])=>x.n>=2).map(([k,x])=>[k,Math.round(x.e/x.n),x.n]).sort((a,b)=>b[1]-a[1]);
}
function renderRanked(id,rows,color,limit=15){
  if(!rows.length){document.getElementById(id).innerHTML='<div class="muted">Not enough data</div>';return;}
  const mx=Math.max(...rows.map(r=>r[1]));
  document.getElementById(id).innerHTML='<table>'+rows.slice(0,limit).map(r=>
    `<tr><td>${escHtml(r[0])}</td><td class="num">${fmt(r[1])}${r[2]?` <span class="muted">/${r[2]}p</span>`:''}</td><td style="width:35%"><div class="bar"><span style="width:${r[1]/mx*100}%;background:${color}"></span></div></td></tr>`
  ).join('')+'</table>';
}
function refreshLists(accs){
  function getActive(grp){ const t=document.querySelector(`.tabs[data-grp="${grp}"] .tab.active`); return t?t.dataset.acc:accs[0].handle; }
  const hash=getActive('hash'), eff=getActive('hash_eff'), tag=getActive('tag');
  renderRanked('tbl_hash',tally(ownByAcc(hash),'hashtags'),colorOf(hash));
  renderRanked('tbl_hash_eff',effective(ownByAcc(eff),'hashtags'),colorOf(eff));
  renderRanked('tbl_tag',tally(ownByAcc(tag),'tagged'),colorOf(tag));
}
function wireListTabs(){
  document.querySelectorAll('.tabs[data-grp]').forEach(box=>{
    box.addEventListener('click',e=>{
      const t=e.target.closest('.tab'); if(!t) return;
      [...box.children].forEach(c=>c.classList.remove('active'));
      t.classList.add('active');
      const grp=box.dataset.grp;
      if(grp==='top'||grp==='topsort') topPosts(segAccounts());
      else refreshLists(segAccounts());
    });
  });
}
function topPostsWire(){}

function topPosts(accs){
  const fT=document.querySelector('.tabs[data-grp="top"] .tab.active');
  const sT=document.querySelector('.tabs[data-grp="topsort"] .tab.active');
  const filter=fT?fT.dataset.top:'all', sort=sT?sT.dataset.sort:'engagement';
  let arr=segOwn().slice();
  if(filter!=='all') arr=arr.filter(p=>p.account===filter);
  arr.sort((a,b)=>(b[sort]||0)-(a[sort]||0));
  arr=arr.slice(0,20);
  function sortHead(key,label,extra){return `<th class="${extra||''}" data-col-sort="${key}" style="cursor:pointer;user-select:none">${label}${sort===key?' ▼':''}</th>`;}
  document.getElementById('tbl_top').innerHTML='<table><thead><tr><th></th>'+sortHead('ts_ms','Date')+'<th>Account</th><th>Type</th><th>Theme</th>'+sortHead('likes','Likes','num')+sortHead('comments','Comments','num')+sortHead('views','Views','num')+sortHead('er','ER','num')+'<th>Caption</th><th>↗</th></tr></thead><tbody>'+
    arr.map(p=>{
      const c=colorOf(p.account);
      const accObj = segAccounts().find(x=>x.handle===p.account) || {handle:p.account,color:c,fullName:p.account};
      const av = avatarHTML(accObj);
      const acc=`<span style="display:inline-flex;align-items:center;gap:6px">${av}<span class="pill" style="background:${rgba(c,.2)};color:${c}">@${p.account}</span></span>`;
      const d=p.timestamp?p.timestamp.slice(0,10):'';
      const cap=escHtml(p.caption||'').slice(0,160);
      const img=p.displayUrl?`<a href="${escHtml(p.url)}" target="_blank"><img class="thumb" loading="lazy" referrerpolicy="no-referrer" src="${escHtml(p.displayUrl)}" onerror="this.style.display='none'"/></a>`:'';
      const tColor = (typeof THEME_PALETTE!=='undefined') ? (THEME_PALETTE[p.theme]||'#888') : '#888';
      const themePill = p.theme ? `<span style="font-size:10px;padding:2px 8px;border-radius:999px;background:${rgba(tColor,.18)};color:${tColor};white-space:nowrap">${escHtml(p.theme)}</span>` : '';
      return `<tr><td>${img}</td><td>${d}</td><td>${acc}</td><td>${p.type}</td><td>${themePill}</td><td class="num">${fmt(p.likes)}</td><td class="num">${fmt(p.comments)}</td><td class="num">${p.views?fmt(p.views):'—'}</td><td class="num">${p.er!=null?fmtPc(p.er):'—'}</td><td>${cap}</td><td>${p.url?`<a href="${escHtml(p.url)}" target="_blank">↗</a>`:''}</td></tr>`;
    }).join('')+'</tbody></table>';
  // Wire sortable column headers → trigger the matching sort tab if present, else update directly
  document.querySelectorAll('#tbl_top [data-col-sort]').forEach(th=>{
    th.addEventListener('click',()=>{
      const key = th.dataset.colSort;
      const tab = document.querySelector(`.tabs[data-grp="topsort"] .tab[data-sort="${key}"]`);
      if(tab){ tab.click(); }
      else {
        // No matching pill (e.g. Date sort) — set a synthetic active by simulating
        document.querySelectorAll('.tabs[data-grp="topsort"] .tab').forEach(c=>c.classList.remove('active'));
        topPosts(accs); // re-render with the override; but sort uses tab.active so we need state
      }
    });
  });
}

function wordcloud(){
  const STOP=new Set('the a an and or but if so on in for of to with at by from is are was were be been being have has had do does did this that these those it its as we our us you your they them their he she his her not no yes will would could should can may i my me about into out up down over under all any more most some such only own same than too very just one two three first new'.split(' '));
  const m={};
  for(const p of segOwn()){ const text=(p.caption||'').toLowerCase().replace(/[^\p{L}\s#]/gu,' ');
    for(const w of text.split(/\s+/)){ if(w.length<4||STOP.has(w)||w.startsWith('http')) continue; m[w]=(m[w]||0)+1; } }
  const rows=Object.entries(m).sort((a,b)=>b[1]-a[1]).slice(0,60);
  if(!rows.length){ document.getElementById('wordcloud').innerHTML='<div class="muted">No captions</div>'; return; }
  const mx=rows[0][1], mn=rows[rows.length-1][1];
  document.getElementById('wordcloud').innerHTML=rows.map(([w,n])=>{const s=11+Math.round(20*(n-mn)/Math.max(1,mx-mn));const o=.55+.45*(n-mn)/Math.max(1,mx-mn);return `<span class="hash-chip" style="font-size:${s}px;opacity:${o.toFixed(2)}">${escHtml(w)} <span class="muted">${n}</span></span>`;}).join('');
}

function insights(accs){
  // Per-account smart insights. Each rule emits a bullet only if it has enough data to be meaningful.
  // In drill-down view accs is 1 account. In multi-account contexts we cap output per account.
  const ins = [];
  const dows = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

  function contentMix(arr){
    const c = {}; for(const p of arr) c[p.type]=(c[p.type]||0)+1;
    const total = arr.length;
    const sorted = Object.entries(c).sort((a,b)=>b[1]-a[1]);
    const top3 = sorted.slice(0,3).map(([t,n])=>`${Math.round(n/total*100)}% ${t}`).join(' · ');
    return {total, summary:top3, dominant:sorted[0]?.[0]||'', dominantPct:Math.round((sorted[0]?.[1]||0)/total*100)};
  }
  function formatROI(arr){
    const byT={}; for(const p of arr){(byT[p.type]=byT[p.type]||[]).push(p.engagement);}
    const avgs = Object.entries(byT).filter(([,v])=>v.length>=3).map(([t,v])=>({type:t,avg:v.reduce((s,x)=>s+x,0)/v.length,n:v.length})).sort((a,b)=>b.avg-a.avg);
    if(avgs.length<2) return {best:null};
    return {best:avgs[0].type, bestEng:avgs[0].avg, nextType:avgs[1].type, nextEng:avgs[1].avg, ratio:avgs[0].avg/Math.max(1,avgs[1].avg)};
  }
  function bestDayHour(arr){
    const b={};
    let totalEng=0,count=0;
    for(const p of arr){
      if(!p.ts_ms) continue;
      const d=new Date(p.ts_ms+GST_OFFSET_MS); const dow=(d.getUTCDay()+6)%7; const hh=d.getUTCHours(); const hb=Math.floor(hh/3)*3;
      const k=dow+'_'+hb;
      if(!b[k]) b[k]={sum:0,n:0,dow,hb};
      b[k].sum+=p.engagement; b[k].n++; totalEng+=p.engagement; count++;
    }
    const avg = count?totalEng/count:0;
    const entries = Object.values(b).filter(x=>x.n>=3).sort((a,b)=>(b.sum/b.n)-(a.sum/a.n));
    if(!entries.length) return {eng:0};
    const top = entries[0];
    return {day:dows[top.dow], hourLabel:`${String(top.hb).padStart(2,'0')}–${String(top.hb+3).padStart(2,'0')}h UTC`, eng:top.sum/top.n, lift:avg?(top.sum/top.n)/avg:0};
  }
  function tagInbound(handle){
    const tagged = DATA.filter(p=>p.account===handle && !p.isOwn);
    const byOwner = {};
    for(const p of tagged) byOwner[p.owner] = (byOwner[p.owner]||0) + 1;
    const sorted = Object.entries(byOwner).sort((a,b)=>b[1]-a[1]);
    return {count:tagged.length, uniqueTaggers:sorted.length, top:sorted.slice(0,3)};
  }
  function hashtagROI(arr){
    const m={};
    for(const p of arr) for(const h of (p.hashtags||[])){
      if(!m[h]) m[h]={sum:0,n:0};
      m[h].sum+=p.engagement; m[h].n++;
    }
    const e = Object.entries(m).filter(([,v])=>v.n>=2).map(([t,v])=>({tag:t,avgEng:v.sum/v.n,posts:v.n})).sort((a,b)=>b.avgEng-a.avgEng);
    return e[0] || {tag:null};
  }
  function captionSweetSpot(arr){
    const buckets = [
      {label:'<50 chars',  min:0,   max:50},
      {label:'50–150',     min:50,  max:150},
      {label:'150–300',    min:150, max:300},
      {label:'300–500',    min:300, max:500},
      {label:'500+',       min:500, max:99999},
    ];
    const s={}; let totalEng=0,totalN=0;
    for(const p of arr){
      const len=p.capLen||0;
      const b=buckets.find(x=>len>=x.min&&len<x.max);
      if(!b) continue;
      if(!s[b.label]) s[b.label]={sum:0,n:0};
      s[b.label].sum+=p.engagement; s[b.label].n++; totalEng+=p.engagement; totalN++;
    }
    const e = Object.entries(s).filter(([,v])=>v.n>=4).map(([k,v])=>({bucket:k,eng:v.sum/v.n,n:v.n})).sort((a,b)=>b.eng-a.eng);
    if(!e.length) return {bucket:null};
    const avg = totalN?totalEng/totalN:0;
    return {bucket:e[0].bucket, eng:e[0].eng, lift:avg?e[0].eng/avg:0};
  }
  function audioStrategy(arr){
    const reels = arr.filter(p=>p.type==='Reel'||p.type==='Video');
    if(reels.length<4) return {reels:0};
    const orig = reels.filter(p=>p.usesOriginal===true);
    const lic  = reels.filter(p=>p.usesOriginal===false);
    const origEng = orig.length?orig.reduce((s,p)=>s+p.engagement,0)/orig.length:0;
    const licEng  = lic.length ?lic.reduce((s,p)=>s+p.engagement,0)/lic.length:0;
    let verdict;
    if(orig.length>=2 && lic.length>=2){
      verdict = origEng>licEng*1.2 ? `original audio drives <strong>${(origEng/Math.max(1,licEng)).toFixed(1)}× higher engagement</strong>` :
                licEng>origEng*1.2 ? `licensed audio drives <strong>${(licEng/Math.max(1,origEng)).toFixed(1)}× higher engagement</strong>` :
                'original and licensed perform similarly';
    } else verdict = orig.length>lic.length ? 'leans heavily on original audio' : 'leans on licensed/trending audio';
    return {reels:reels.length, originalPct:Math.round(orig.length/reels.length*100), verdict};
  }
  function velocityTrend(arr){
    const ts = arr.map(p=>p.ts_ms).filter(Boolean);
    if(ts.length<5) return {recent30:0,full:0};
    const max=Math.max(...ts), min=Math.min(...ts);
    const fullWeeks = (max-min)/(7*864e5);
    const full = fullWeeks>0 ? arr.length/fullWeeks : 0;
    const cutoff = max - 30*864e5;
    const recent = arr.filter(p=>p.ts_ms && p.ts_ms>=cutoff).length;
    const recent30 = recent/(30/7);
    return {recent30, full};
  }
  function collabSignal(arr){
    const w = arr.filter(p=>(p.tagged||[]).length>0);
    return {pct:Math.round(w.length/Math.max(1,arr.length)*100), count:w.length};
  }

  for(const a of accs){
    const arr = ownByAcc(a.handle);
    if(!arr.length){
      ins.push({c:a.color, l:'@'+a.handle, h:`No tracked posts for <strong>@${a.handle}</strong> yet.`});
      continue;
    }
    const bullets = [];

    // 1. Content mix
    const mix = contentMix(arr);
    if(mix.total>=5){
      bullets.push(`<strong>Content mix:</strong> ${mix.summary}. ${mix.dominant} carries ${mix.dominantPct}% of output.`);
    }
    // 2. Format ROI
    const roi = formatROI(arr);
    if(roi.best && roi.ratio>1.3){
      bullets.push(`<strong>${roi.best}s drive ${roi.ratio.toFixed(1)}× the engagement</strong> of ${roi.nextType}s (${fmt(roi.bestEng)} vs ${fmt(roi.nextEng)} avg).`);
    }
    // 3. Best day×hour
    const dh = bestDayHour(arr);
    if(dh.eng>0){
      const liftTxt = dh.lift>1.5 ? ` (${dh.lift.toFixed(1)}× normal)` : '';
      bullets.push(`Sweet spot: <strong>${dh.day} ${dh.hourLabel}</strong> · ${fmt(dh.eng)} avg eng${liftTxt}.`);
    }
    // 4. Tag inbound
    const ti = tagInbound(a.handle);
    if(ti.count>=2 && ti.top.length){
      const examples = ti.top.map(([o,n])=>'@'+o+(n>1?' ×'+n:'')).join(', ');
      bullets.push(`<strong>${ti.count} inbound tag-mentions</strong> from ${ti.uniqueTaggers} unique accounts — top: ${examples}.`);
    }
    // 5. Hashtag ROI
    const hr = hashtagROI(arr);
    if(hr.tag && hr.posts>=2){
      bullets.push(`Best hashtag: <strong>#${hr.tag}</strong> · ${fmt(hr.avgEng)} avg eng/post (${hr.posts} uses).`);
    }
    // 6. Caption sweet spot
    const cap = captionSweetSpot(arr);
    if(cap.bucket && cap.lift>1.2){
      bullets.push(`Caption sweet spot: <strong>${cap.bucket}</strong> captions · ${fmt(cap.eng)} avg eng (${cap.lift.toFixed(1)}× vs other lengths).`);
    }
    // 7. Audio strategy
    const audio = audioStrategy(arr);
    if(audio.reels>=4){
      bullets.push(`Audio: <strong>${audio.originalPct}% original</strong> across ${audio.reels} videos — ${audio.verdict}.`);
    }
    // 8. Velocity trend
    const vel = velocityTrend(arr);
    if(vel.recent30>0 && vel.full>0){
      const change = ((vel.recent30 - vel.full) / vel.full) * 100;
      const dir = change>15 ? `<strong>↑ accelerating</strong> (+${change.toFixed(0)}%)` :
                  change<-15 ? `<strong>↓ slowing</strong> (${change.toFixed(0)}%)` : '→ steady';
      bullets.push(`Velocity: ${dir} · ${vel.recent30.toFixed(1)} posts/wk last 30d vs ${vel.full.toFixed(1)} all-time.`);
    }
    // 9. Collab signal
    const collab = collabSignal(arr);
    if(collab.pct>=10){
      bullets.push(`<strong>${collab.pct}% of posts feature collabs/tagged users</strong> (${collab.count} posts) — partnership-heavy strategy.`);
    }
    // 10. Top post
    const top = [...arr].sort((x,y)=>y.engagement-x.engagement)[0];
    if(top){
      const link = top.url?` · <a target="_blank" href="${escHtml(top.url)}">view ↗</a>`:'';
      bullets.push(`Top post: <strong>${fmt(top.engagement)} eng.</strong> · ${top.type} · ${top.timestamp?.slice(0,10)}${link}`);
    }

    // Cap to 7 bullets per account in solo, 4 in multi
    const cap2 = accs.length===1 ? 8 : 4;
    for(const b of bullets.slice(0, cap2)){
      ins.push({c:a.color, l:'@'+a.handle, h:b});
    }
  }

  document.getElementById('insights').innerHTML = ins.map(x=>`<div class="insight" style="border-color:${x.c}"><span class="label">${x.l}</span>${x.h}</div>`).join('');
}

// Initial render
render();

// ============ Add-account modal & Apify scrape integration ============
(function(){
  const isServed = location.protocol === 'http:' || location.protocol === 'https:';
  const fab = document.getElementById('fab');
  const modal = document.getElementById('modal');
  const warn = document.getElementById('server-warn');
  const inp  = document.getElementById('m-handle');
  const logEl= document.getElementById('m-log');
  const go   = document.getElementById('m-go');
  const cancel = document.getElementById('m-cancel');
  if(!isServed) warn.style.display='block';

  function open(){ modal.classList.remove('hidden'); inp.focus(); logEl.classList.remove('show'); logEl.innerHTML=''; go.disabled=false; }
  function close(){ modal.classList.add('hidden'); }
  fab.addEventListener('click', open);
  cancel.addEventListener('click', close);
  modal.addEventListener('click',e=>{ if(e.target===modal) close(); });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') close(); });

  async function startScrape(){
    const handle = inp.value.trim().replace(/^@/,'');
    const segment = document.querySelector('[name=m-seg]:checked').value;
    const posts   = document.getElementById('m-posts').checked;
    const reels   = document.getElementById('m-reels').checked;
    const profile = document.getElementById('m-profile').checked;
    if(!handle){ inp.focus(); return; }
    go.disabled=true; logEl.classList.add('show');
    logEl.innerHTML = `<div>→ submitting scrape for @${handle} (${segment})…</div>`;
    try{
      const res = await fetch('/api/scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({handle,segment,posts,reels,profile})});
      const data = await res.json();
      if(!res.ok){ logEl.innerHTML += `<div class="err">✕ ${data.error||'failed'}</div>`; go.disabled=false; return; }
      logEl.innerHTML += `<div>job <code>${data.jobId.slice(0,8)}</code> started — polling…</div>`;
      await pollJob(data.jobId);
    } catch(e){
      logEl.innerHTML += `<div class="err">✕ ${e.message} — make sure dashboard_server.py is running</div>`;
      go.disabled=false;
    }
  }

  async function pollJob(jobId){
    let lastLen = 0;
    while(true){
      await new Promise(r=>setTimeout(r,2500));
      let j;
      try{ const r = await fetch('/api/jobs/'+jobId); j = await r.json(); }
      catch(e){ logEl.innerHTML += `<div class="err">poll failed: ${e.message}</div>`; break; }
      if(!j) break;
      // append only new log lines
      for(let i=lastLen;i<(j.log||[]).length;i++){
        const line = j.log[i];
        const cls = /ERROR|✕/i.test(line) ? 'err' : (/✓|rebuilt/.test(line)?'ok':'');
        logEl.innerHTML += `<div class="${cls}">${line}</div>`;
      }
      lastLen = (j.log||[]).length;
      logEl.scrollTop = logEl.scrollHeight;
      if(j.status==='done'){
        logEl.innerHTML += `<div class="ok">✓ done — reloading dashboard in 2s</div>`;
        setTimeout(()=>location.reload(), 2000);
        return;
      }
      if(j.status==='failed'){ go.disabled=false; return; }
    }
  }

  go.addEventListener('click', startScrape);
  inp.addEventListener('keydown', e=>{ if(e.key==='Enter') startScrape(); });
})();

function buildComparativeInsights(accs){
  const box = document.getElementById('cmp_auto_insights');
  if(!box) return;
  if(accs.length < 2) {
    box.innerHTML = '<div class="empty" style="margin-top:-10px">Select at least 2 accounts to see comparative insights.</div>';
    return;
  }
  
  // Helpers
  const dows = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  function contentMix(arr){
    const c = {}; for(const p of arr) c[p.type]=(c[p.type]||0)+1;
    const total = arr.length;
    const sorted = Object.entries(c).sort((a,b)=>b[1]-a[1]);
    return sorted.slice(0,3).map(([t,n])=>`${Math.round(n/total*100)}% ${t}`).join('<br/>');
  }
  function bestDayHour(arr){
    const b={}; let totalEng=0,count=0;
    for(const p of arr){
      if(!p.ts_ms) continue;
      const d=new Date(p.ts_ms+GST_OFFSET_MS); const dow=(d.getUTCDay()+6)%7; const hh=d.getUTCHours(); const hb=Math.floor(hh/3)*3;
      const k=dow+'_'+hb;
      if(!b[k]) b[k]={sum:0,n:0,dow,hb};
      b[k].sum+=p.engagement; b[k].n++; totalEng+=p.engagement; count++;
    }
    const avg = count?totalEng/count:0;
    const entries = Object.values(b).filter(x=>x.n>=3).sort((a,b)=>(b.sum/b.n)-(a.sum/a.n));
    if(!entries.length) return '-';
    const top = entries[0];
    return `<strong>${dows[top.dow]} ${String(top.hb).padStart(2,'0')}–${String(top.hb+3).padStart(2,'0')}h UTC</strong><br/>${fmt(top.sum/top.n)} avg eng`;
  }
  function tagInbound(handle){
    const tagged = DATA.filter(p=>p.account===handle && !p.isOwn);
    return `<strong>${tagged.length}</strong> inbound mentions`;
  }
  function hashtagROI(arr){
    const m={};
    for(const p of arr) for(const h of (p.hashtags||[])){
      if(!m[h]) m[h]={sum:0,n:0}; m[h].sum+=p.engagement; m[h].n++;
    }
    const e = Object.entries(m).filter(([,v])=>v.n>=2).map(([t,v])=>({tag:t,avgEng:v.sum/v.n,posts:v.n})).sort((a,b)=>b.avgEng-a.avgEng);
    return e[0] ? `<strong>#${e[0].tag}</strong><br/>${fmt(e[0].avgEng)} avg` : '-';
  }
  function captionSweetSpot(arr){
    const buckets = [ {label:'<50 chars',min:0,max:50}, {label:'50–150',min:50,max:150}, {label:'150–300',min:150,max:300}, {label:'300–500',min:300,max:500}, {label:'500+',min:500,max:99999} ];
    const s={};
    for(const p of arr){
      const len=p.capLen||0; const b=buckets.find(x=>len>=x.min&&len<x.max);
      if(!b) continue;
      if(!s[b.label]) s[b.label]={sum:0,n:0};
      s[b.label].sum+=p.engagement; s[b.label].n++;
    }
    const e = Object.entries(s).filter(([,v])=>v.n>=4).sort((a,b)=>(b[1].sum/b[1].n)-(a[1].sum/a[1].n));
    return e.length ? `<strong>${e[0][0]}</strong><br/>${fmt(e[0][1].sum/e[0][1].n)} avg` : '-';
  }
  function audioStrategy(arr){
    const reels = arr.filter(p=>p.type==='Reel'||p.type==='Video');
    if(reels.length<4) return '-';
    const orig = reels.filter(p=>p.usesOriginal===true).length;
    return `<strong>${Math.round(orig/reels.length*100)}%</strong> original`;
  }
  function velocityTrend(arr){
    const ts = arr.map(p=>p.ts_ms).filter(Boolean);
    if(ts.length<5) return '-';
    const max=Math.max(...ts), min=Math.min(...ts);
    const fullWeeks = (max-min)/(7*864e5);
    const full = fullWeeks>0 ? arr.length/fullWeeks : 0;
    const cutoff = max - 30*864e5;
    const recent30 = arr.filter(p=>p.ts_ms && p.ts_ms>=cutoff).length / (30/7);
    const change = ((recent30 - full) / Math.max(0.1, full)) * 100;
    const dir = change>15 ? `↑` : change<-15 ? `↓` : '→';
    return `<strong>${dir} ${recent30.toFixed(1)}/wk</strong><br/>(all-time: ${full.toFixed(1)})`;
  }
  function collabSignal(arr){
    const w = arr.filter(p=>(p.tagged||[]).length>0);
    return `<strong>${Math.round(w.length/Math.max(1,arr.length)*100)}%</strong> of posts`;
  }

  // Build the matrix
  const dimensions = [
    { label: 'Content Mix', get: a => contentMix(ownByAcc(a.handle)) },
    { label: 'Sweet Spot', get: a => bestDayHour(ownByAcc(a.handle)) },
    { label: 'Caption Length', get: a => captionSweetSpot(ownByAcc(a.handle)) },
    { label: 'Best Hashtag', get: a => hashtagROI(ownByAcc(a.handle)) },
    { label: 'Audio Strategy', get: a => audioStrategy(ownByAcc(a.handle)) },
    { label: 'Velocity Trend', get: a => velocityTrend(ownByAcc(a.handle)) },
    { label: 'Collab Focus', get: a => collabSignal(ownByAcc(a.handle)) },
    { label: 'Inbound Tags', get: a => tagInbound(a.handle) },
  ];

  let html = `<table class="tbl" style="width:100%; font-size:14px; margin:0; border:none">`;
  html += `<thead><tr><th style="width:140px; background:rgba(0,0,0,0.2)">Dimension</th>`;
  accs.forEach(a => { html += `<th style="background:rgba(0,0,0,0.2)"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${a.color};margin-right:6px"></span>@${a.handle}</th>`; });
  html += `</tr></thead><tbody>`;

  dimensions.forEach(dim => {
    html += `<tr><td style="font-weight:600;color:var(--mut);background:rgba(0,0,0,0.1)">${dim.label}</td>`;
    accs.forEach(a => { html += `<td>${dim.get(a)}</td>`; });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  box.innerHTML = html;
  // Let's remove the padding from the card to make it look clean like a full-bleed table
  box.parentElement.style.padding = '0';
  box.parentElement.style.overflow = 'hidden';
}

// =============================================================================
// NEW PANELS (review v2): archetype heatmap, hook leaderboard, CTA correlation,
// founder-voice signal, content gap matrix, inbound credibility, so-what panel,
// likely-boosted, founder→brand flywheel, 90d momentum, footer, PDF print.
// =============================================================================

// ---- Archetype heatmap (caption length × hashtag count → median ER) ----
function archetypeHeatmap(accs){
  const el = document.getElementById('panel_archetype'); if(!el) return;
  const capBuckets = [
    {key:'short',  lbl:'Short (<80)',     test:p=>p.capLen<80},
    {key:'med',    lbl:'Medium (80-250)', test:p=>p.capLen>=80 && p.capLen<250},
    {key:'long',   lbl:'Long (250-600)',  test:p=>p.capLen>=250 && p.capLen<600},
    {key:'xlong',  lbl:'XLong (600+)',    test:p=>p.capLen>=600},
  ];
  const tagBuckets = [
    {key:'none',   lbl:'0',     test:p=>(p.hashtagCount||0)===0},
    {key:'few',    lbl:'1-3',   test:p=>p.hashtagCount>=1 && p.hashtagCount<=3},
    {key:'mid',    lbl:'4-8',   test:p=>p.hashtagCount>=4 && p.hashtagCount<=8},
    {key:'many',   lbl:'9+',    test:p=>p.hashtagCount>=9},
  ];
  const own = accs.flatMap(a=>ownByAcc(a.handle)).filter(p=>p.er!=null);
  if(!own.length){ el.innerHTML='<div class="muted">No engagement-rate data</div>'; return; }
  // Compute median ER per cell + count
  const cells = capBuckets.map(c=>tagBuckets.map(t=>{
    const subset = own.filter(p=>c.test(p)&&t.test(p));
    const ers = subset.map(p=>p.er).filter(x=>x!=null).sort((a,b)=>a-b);
    const mid = Math.floor(ers.length/2);
    const medER = ers.length ? (ers.length%2? ers[mid] : (ers[mid-1]+ers[mid])/2) : null;
    return {n:subset.length, medER};
  }));
  // Find max ER for shading
  const maxER = Math.max(...cells.flat().map(c=>c.medER||0));
  const colW = `1fr`;
  let html = `<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Median engagement-rate by post archetype (across ${accs.length} selected account${accs.length>1?'s':''}). Cell shading shows where engagement actually lives.</div>`;
  html += `<div class="archetype-grid" style="grid-template-columns:140px repeat(${tagBuckets.length},${colW})">`;
  html += `<div class="archetype-label">Caption ↓ / Tags →</div>`;
  for(const t of tagBuckets) html += `<div class="archetype-label" style="text-align:center">${t.lbl}</div>`;
  for(let i=0;i<capBuckets.length;i++){
    html += `<div class="archetype-label">${capBuckets[i].lbl}</div>`;
    for(let j=0;j<tagBuckets.length;j++){
      const c = cells[i][j];
      if(!c.n){ html += `<div class="archetype-cell empty">—</div>`; continue; }
      const intensity = maxER ? Math.min(1, c.medER/maxER) : 0;
      const bg = `rgba(91,156,255,${0.18 + 0.65*intensity})`;
      html += `<div class="archetype-cell" style="background:${bg}" title="${c.n} posts">${(c.medER*100).toFixed(2)}%<div style="font-size:9px;font-weight:400;opacity:.75">n=${c.n}</div></div>`;
    }
  }
  html += `</div>`;
  // Pick the winning archetype
  let bestI=-1, bestJ=-1, bestER=-1;
  for(let i=0;i<capBuckets.length;i++) for(let j=0;j<tagBuckets.length;j++){
    const c = cells[i][j]; if(c.n>=5 && (c.medER||0) > bestER){ bestER=c.medER; bestI=i; bestJ=j; }
  }
  if(bestI>=0) html += `<div style="margin-top:10px;padding:8px 12px;background:rgba(70,211,160,.1);border-left:3px solid var(--ok);border-radius:4px;font-size:12.5px"><strong>Winning archetype:</strong> ${capBuckets[bestI].lbl.toLowerCase()} caption × ${tagBuckets[bestJ].lbl} hashtags → median ER <strong>${(bestER*100).toFixed(2)}%</strong></div>`;
  el.innerHTML = html;
}

// ---- Hook leaderboard (first 3 words → avg engagement) ----
function hookLeaderboard(accs){
  const el = document.getElementById('panel_hook'); if(!el) return;
  const own = accs.flatMap(a=>ownByAcc(a.handle)).filter(p=>p.hook && p.engagement!=null);
  if(!own.length){ el.innerHTML='<div class="muted">No caption hooks</div>'; return; }
  const m = {};
  for(const p of own){
    if(!m[p.hook]) m[p.hook]={n:0,sumEng:0,sumER:0,erN:0,topPost:null,accs:new Set()};
    m[p.hook].n++; m[p.hook].sumEng+=p.engagement||0;
    if(p.er!=null){ m[p.hook].sumER+=p.er; m[p.hook].erN++; }
    m[p.hook].accs.add(p.account);
    if(!m[p.hook].topPost || (p.engagement||0)>(m[p.hook].topPost.engagement||0)) m[p.hook].topPost=p;
  }
  const rows = Object.entries(m).filter(([,v])=>v.n>=2).map(([h,v])=>({hook:h,...v,avgEng:v.sumEng/v.n,avgER:v.erN?v.sumER/v.erN:0}))
    .sort((a,b)=>b.avgEng-a.avgEng).slice(0,20);
  if(!rows.length){ el.innerHTML='<div class="muted">Need ≥2 posts per hook</div>'; return; }
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Top stop-scroll hooks (first 3 words of caption, repeated ≥2 times). Reel hooks are the strongest signal here.</div>';
  html += '<table><thead><tr><th>Hook (first 3 words)</th><th class="num">Posts</th><th class="num">Accounts</th><th class="num">Avg eng</th><th class="num">Avg ER</th><th>Top example</th></tr></thead><tbody>';
  for(const r of rows){
    const tp=r.topPost;
    const tpLink = tp && tp.url ? `<a href="${escHtml(tp.url)}" target="_blank">@${escHtml(tp.account)} · ${fmt(tp.engagement)} eng ↗</a>` : '—';
    html += `<tr><td><strong>"${escHtml(r.hook)}…"</strong></td><td class="num">${r.n}</td><td class="num">${r.accs.size}</td><td class="num">${fmt(r.avgEng)}</td><td class="num">${(r.avgER*100).toFixed(2)}%</td><td>${tpLink}</td></tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// ---- CTA detection panel ----
function ctaPanel(accs){
  const el = document.getElementById('panel_cta'); if(!el) return;
  const own = accs.flatMap(a=>ownByAcc(a.handle)).filter(p=>p.engagement!=null);
  if(!own.length){ el.innerHTML='<div class="muted">No data</div>'; return; }
  const withCTA = own.filter(p=>p.hasCTA);
  const noCTA   = own.filter(p=>!p.hasCTA);
  const avgEngCTA = withCTA.length ? withCTA.reduce((s,p)=>s+p.engagement,0)/withCTA.length : 0;
  const avgEngNoCTA = noCTA.length ? noCTA.reduce((s,p)=>s+p.engagement,0)/noCTA.length : 0;
  const erCTA = withCTA.filter(p=>p.er!=null);
  const erNoCTA = noCTA.filter(p=>p.er!=null);
  const avgERCTA = erCTA.length ? erCTA.reduce((s,p)=>s+p.er,0)/erCTA.length : 0;
  const avgERNoCTA = erNoCTA.length ? erNoCTA.reduce((s,p)=>s+p.er,0)/erNoCTA.length : 0;
  const lift = avgERNoCTA>0 ? ((avgERCTA/avgERNoCTA - 1)*100) : 0;

  // CTA type breakdown
  const byType = {};
  for(const p of withCTA){
    const t = p.ctaType || 'Other';
    if(!byType[t]) byType[t]={n:0,sumEng:0,sumER:0,erN:0};
    byType[t].n++; byType[t].sumEng+=p.engagement||0;
    if(p.er!=null){ byType[t].sumER+=p.er; byType[t].erN++; }
  }
  const ctaRows = Object.entries(byType).map(([t,v])=>({type:t,...v,avgEng:v.sumEng/v.n,avgER:v.erN?v.sumER/v.erN:0}))
    .sort((a,b)=>b.avgER-a.avgER);

  const liftBadge = lift>0
    ? `<span class="pill" style="background:rgba(70,211,160,.18);color:var(--ok)">+${lift.toFixed(0)}% vs no-CTA</span>`
    : `<span class="pill" style="background:rgba(255,107,138,.18);color:var(--bad)">${lift.toFixed(0)}% vs no-CTA</span>`;

  let html = `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px">
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Posts with CTA</div><div style="font-size:22px;font-weight:700">${withCTA.length} <span style="color:var(--mut);font-size:13px">(${(withCTA.length/own.length*100).toFixed(0)}%)</span></div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Avg ER with CTA</div><div style="font-size:22px;font-weight:700">${(avgERCTA*100).toFixed(2)}%</div></div>
    <div><div style="font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em">Avg ER without CTA</div><div style="font-size:22px;font-weight:700">${(avgERNoCTA*100).toFixed(2)}% ${liftBadge}</div></div>
  </div>`;
  if(ctaRows.length){
    html += '<table><thead><tr><th>CTA type</th><th class="num">Posts</th><th class="num">Avg eng</th><th class="num">Avg ER</th></tr></thead><tbody>';
    for(const r of ctaRows){
      html += `<tr><td><strong>${escHtml(r.type)}</strong></td><td class="num">${r.n}</td><td class="num">${fmt(r.avgEng)}</td><td class="num">${(r.avgER*100).toFixed(2)}%</td></tr>`;
    }
    html += '</tbody></table>';
  }
  el.innerHTML = html;
}

// ---- Founder-voice signal panel ----
function voiceSignalPanel(accs){
  const el = document.getElementById('panel_voice'); if(!el) return;
  const rows = accs.map(a=>{
    const own = ownByAcc(a.handle);
    const fv = own.filter(p=>p.founderVoice);
    const nonFv = own.filter(p=>!p.founderVoice);
    const fvER = fv.filter(p=>p.er!=null);
    const nfER = nonFv.filter(p=>p.er!=null);
    const avgFvER = fvER.length ? fvER.reduce((s,p)=>s+p.er,0)/fvER.length : 0;
    const avgNfER = nfER.length ? nfER.reduce((s,p)=>s+p.er,0)/nfER.length : 0;
    return {a, total:own.length, fvN:fv.length, share:own.length?fv.length/own.length:0, avgFvER, avgNfER};
  });
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Founder-voice = caption >180 chars with first-person pronouns (I/we/my/our). Distinguishes founder-led brands from corporate-sounding ones.</div>';
  html += '<table><thead><tr><th>Account</th><th class="num">Founder-voice posts</th><th class="num">% of own posts</th><th class="num">Avg ER (FV)</th><th class="num">Avg ER (other)</th><th>Lift</th></tr></thead><tbody>';
  for(const r of rows){
    const lift = r.avgNfER>0 ? ((r.avgFvER/r.avgNfER-1)*100) : 0;
    const liftBadge = lift>10
      ? `<span class="pill" style="background:rgba(70,211,160,.18);color:var(--ok)">+${lift.toFixed(0)}%</span>`
      : lift<-10
      ? `<span class="pill" style="background:rgba(255,107,138,.18);color:var(--bad)">${lift.toFixed(0)}%</span>`
      : `<span class="pill" style="background:rgba(136,149,173,.18);color:var(--mut)">${lift>=0?'+':''}${lift.toFixed(0)}%</span>`;
    html += `<tr><td><span class="pill" style="background:${rgba(r.a.color,.2)};color:${r.a.color}">@${r.a.handle}</span></td><td class="num">${r.fvN} / ${r.total}</td><td class="num"><strong>${(r.share*100).toFixed(0)}%</strong></td><td class="num">${(r.avgFvER*100).toFixed(2)}%</td><td class="num">${(r.avgNfER*100).toFixed(2)}%</td><td>${liftBadge}</td></tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// ---- Content gap matrix (themes × accounts heat) ----
function contentGapMatrix(accs){
  const el = document.getElementById('panel_gap'); if(!el) return;
  if(accs.length<2){ el.innerHTML='<div class="muted">Select 2+ accounts in Comparison to see content gap matrix.</div>'; return; }
  const themeOrder = ['Project Launch','Investment','Event / Occasion','Real Estate Market','Business / Leadership','Press / Media Coverage','Behind the Scenes / Team','Motivational / Inspirational','Partnership / Collaboration','Cultural / Community','Personal Storytelling','Lifestyle / Personal','Uncategorized'];
  // Build shares: theme → { handle → % of that account's own posts }
  const shares = {};
  for(const t of themeOrder) shares[t] = {};
  for(const a of accs){
    const own = ownByAcc(a.handle); const total = own.length || 1;
    const counts = {};
    for(const p of own){ const t = p.theme||'Uncategorized'; counts[t] = (counts[t]||0)+1; }
    for(const t of themeOrder) shares[t][a.handle] = (counts[t]||0)/total;
  }
  // Render matrix
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Each cell = that account\'s % of own posts in that theme. Greener = over-indexed, redder = under-indexed (vs row avg). Find your content gaps at a glance.</div>';
  html += `<div class="archetype-grid" style="grid-template-columns:180px repeat(${accs.length},1fr)">`;
  html += `<div class="archetype-label">Theme ↓ / Account →</div>`;
  for(const a of accs) html += `<div class="archetype-label" style="text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><span style="color:${a.color}">●</span> @${escHtml(a.handle)}</div>`;
  for(const t of themeOrder){
    const vals = accs.map(a=>shares[t][a.handle]);
    const rowAvg = vals.reduce((s,x)=>s+x,0)/vals.length;
    if(rowAvg < 0.005) continue; // skip themes that nobody uses
    const color = THEME_PALETTE[t]||'#888';
    html += `<div class="archetype-label" style="text-align:left;white-space:nowrap"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px;vertical-align:middle"></span>${escHtml(t)}</div>`;
    for(let i=0;i<accs.length;i++){
      const v = vals[i]; const delta = v - rowAvg;
      const pct = (v*100).toFixed(0)+'%';
      let bg;
      if(delta > 0.05) bg = `rgba(70,211,160,${Math.min(0.55, 0.2+delta*3)})`;
      else if(delta < -0.05) bg = `rgba(255,107,138,${Math.min(0.55, 0.2+Math.abs(delta)*3)})`;
      else bg = 'rgba(255,255,255,.05)';
      const lbl = v<0.005 ? '—' : pct;
      const cls = v<0.005 ? 'gap-cell zero' : 'gap-cell';
      html += `<div class="${cls}" style="background:${bg}" title="@${accs[i].handle} · ${escHtml(t)} · ${pct} (${(delta*100>=0?'+':'')}${(delta*100).toFixed(1)}pp vs row avg)">${lbl}</div>`;
    }
  }
  html += `</div>`;
  el.innerHTML = html;
}

// ---- Inbound credibility scoreboard (weighted) ----
function inboundCredibilityScoreboard(accs){
  const el = document.getElementById('panel_credibility'); if(!el) return;
  // Per tagger, aggregate: total eng, total reach, # accounts touched
  // Credibility score = (credTier multiplier) * (totalEng/1000 + accHits*5)
  const score = {};
  for(const a of accs){
    const inbound = DATA.filter(p=>p.account===a.handle && !p.isOwn);
    for(const p of inbound){
      if(!p.owner) continue;
      if(!score[p.owner]) score[p.owner]={accs:new Set(),sumEng:0,sumReach:0,n:0,topPost:null};
      const s = score[p.owner];
      s.accs.add(a.handle); s.sumEng += p.engagement||0; s.sumReach += p.views||0; s.n++;
      if(!s.topPost || (p.engagement||0)>(s.topPost.engagement||0)) s.topPost=p;
    }
  }
  const rows = Object.entries(score).map(([owner,v])=>{
    const tier = META.credibilityTiers[owner] || 1;
    const cred = tier * (v.sumEng/1000 + v.accs.size*5);
    return {owner, ...v, accHits:v.accs.size, tier, cred};
  }).sort((a,b)=>b.cred-a.cred).slice(0,20);
  if(!rows.length){ el.innerHTML='<div class="muted">No inbound taggers in dataset</div>'; return; }
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Earned-media ranking: <strong>credibility score = tier-weight × (Σ engagement/1000 + accounts touched × 5)</strong>. Tier 3 = major media / verified celeb; tier 2 = mid; tier 1 = niche/unknown.</div>';
  html += '<table><thead><tr><th>Tagger</th><th class="num">Tier</th><th class="num">Accounts touched</th><th class="num">Σ engagement</th><th class="num">Σ reach</th><th class="num">Credibility</th><th>Best post</th></tr></thead><tbody>';
  for(const r of rows){
    const tierBadge = r.tier===3 ? '<span class="pill" style="background:rgba(70,211,160,.25);color:var(--ok)">3 · TOP</span>'
      : r.tier===2 ? '<span class="pill" style="background:rgba(255,180,84,.2);color:var(--warn)">2 · MID</span>'
      : '<span class="pill" style="background:rgba(136,149,173,.15);color:var(--mut)">1 · STD</span>';
    const tp = r.topPost;
    const tpLink = tp && tp.url ? `<a href="${escHtml(tp.url)}" target="_blank">${fmt(tp.engagement)} eng ↗</a>` : '—';
    html += `<tr><td><a target="_blank" href="https://www.instagram.com/${escHtml(r.owner)}/">@${escHtml(r.owner)}</a></td><td class="num">${tierBadge}</td><td class="num">${r.accHits}/${accs.length}</td><td class="num">${fmt(r.sumEng)}</td><td class="num">${r.sumReach?fmt(r.sumReach):'—'}</td><td class="num"><strong>${fmt(r.cred)}</strong></td><td>${tpLink}</td></tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// ---- Likely-boosted panel ----
function likelyBoostedPanel(accs){
  const el = document.getElementById('panel_boosted'); if(!el) return;
  const rows = accs.map(a=>{
    const own = ownByAcc(a.handle);
    const reels = own.filter(p=>(p.views||0)>0);
    const boosted = reels.filter(p=>p.likelyBoosted);
    return {a, reelsN:reels.length, boostedN:boosted.length, share:reels.length?boosted.length/reels.length:0, boosted};
  });
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px"><strong>Heuristic estimate.</strong> Flags posts with views ≥ max(median + 3×MAD, 2.5×median) for that account\'s video content. Real paid/organic split is only visible to the account owner. Use this for directional comparison only.</div>';
  html += '<table><thead><tr><th>Account</th><th class="num">Reels/Videos</th><th class="num">Likely boosted</th><th class="num">% boosted</th><th>Recent likely-boosted posts</th></tr></thead><tbody>';
  for(const r of rows){
    const top3 = r.boosted.sort((a,b)=>(b.views||0)-(a.views||0)).slice(0,3);
    const links = top3.length ? top3.map(p=>`<a href="${escHtml(p.url||'')}" target="_blank">${fmt(p.views)} views ↗</a>`).join(' · ') : '<span class="muted">—</span>';
    html += `<tr><td><span class="pill" style="background:${rgba(r.a.color,.2)};color:${r.a.color}">@${r.a.handle}</span></td><td class="num">${r.reelsN}</td><td class="num">${r.boostedN}</td><td class="num"><strong>${(r.share*100).toFixed(0)}%</strong></td><td>${links}</td></tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// ---- Founder→Brand flywheel ----
function founderBrandFlywheel(){
  const el = document.getElementById('panel_flywheel'); if(!el) return;
  const pairs = META.founderBrandPairs.map(([f,b])=>{
    const fa = ACCOUNTS.find(x=>x.handle===f);
    const ba = ACCOUNTS.find(x=>x.handle===b);
    return fa && ba ? {founder:fa, brand:ba} : null;
  }).filter(Boolean);
  if(!pairs.length){ el.innerHTML='<div class="muted">No founder-brand pairs available.</div>'; return; }
  function stats(a){
    const own = DATA.filter(p=>p.account===a.handle && p.isOwn);
    const ers = own.filter(p=>p.er!=null);
    return {
      followers: a.followers||0,
      posts: own.length,
      avgEng: own.length ? own.reduce((s,p)=>s+(p.engagement||0),0)/own.length : 0,
      avgER: ers.length ? ers.reduce((s,p)=>s+p.er,0)/ers.length : 0,
    };
  }
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:12px">Founder accounts have built-in trust currency. The gap between founder and brand engagement = unrealized amplification opportunity.</div>';
  for(const {founder, brand} of pairs){
    const fs = stats(founder); const bs = stats(brand);
    const engLift = bs.avgEng>0 ? (fs.avgEng/bs.avgEng) : 0;
    const erLift  = bs.avgER>0  ? (fs.avgER/bs.avgER)   : 0;
    html += `<div class="flywheel-row">
      <div class="flywheel-side">
        <div class="name">👤 ${escHtml(founder.fullName||founder.handle)}</div>
        <div class="handle">@${escHtml(founder.handle)} · Founder</div>
        <div class="kpis">
          <div class="tile"><div class="v">${fmt(fs.followers)}</div><div class="l">Followers</div></div>
          <div class="tile"><div class="v">${fmt(fs.avgEng)}</div><div class="l">Avg eng</div></div>
          <div class="tile"><div class="v">${(fs.avgER*100).toFixed(2)}%</div><div class="l">Avg ER</div></div>
          <div class="tile"><div class="v">${fs.posts}</div><div class="l">Posts</div></div>
        </div>
      </div>
      <div class="flywheel-arrow">
        <div class="gap">${engLift>0 ? engLift.toFixed(1)+'×' : '—'}</div>
        <div class="lbl">Founder<br/>vs Brand<br/>(avg eng)</div>
        <div class="gap" style="font-size:14px;margin-top:8px">${erLift>0 ? erLift.toFixed(1)+'×' : '—'}</div>
        <div class="lbl">ER multiplier</div>
      </div>
      <div class="flywheel-side">
        <div class="name">🏢 ${escHtml(brand.fullName||brand.handle)}</div>
        <div class="handle">@${escHtml(brand.handle)} · Brand</div>
        <div class="kpis">
          <div class="tile"><div class="v">${fmt(bs.followers)}</div><div class="l">Followers</div></div>
          <div class="tile"><div class="v">${fmt(bs.avgEng)}</div><div class="l">Avg eng</div></div>
          <div class="tile"><div class="v">${(bs.avgER*100).toFixed(2)}%</div><div class="l">Avg ER</div></div>
          <div class="tile"><div class="v">${bs.posts}</div><div class="l">Posts</div></div>
        </div>
      </div>
    </div>`;
  }
  el.innerHTML = html;
}

// ---- 90d momentum delta ----
function momentum90dPanel(accs){
  const el = document.getElementById('panel_momentum'); if(!el) return;
  const allTs = DATA.map(p=>p.ts_ms).filter(Boolean);
  if(!allTs.length){ el.innerHTML='<div class="muted">No data</div>'; return; }
  const cutoffNow = Math.max(...allTs);
  const dayMs = 864e5;
  const recentStart = cutoffNow - 90*dayMs;
  const priorStart  = cutoffNow - 180*dayMs;
  const rows = accs.map(a=>{
    const own = ownByAcc(a.handle);
    const recent = own.filter(p=>p.ts_ms>=recentStart);
    const prior  = own.filter(p=>p.ts_ms>=priorStart && p.ts_ms<recentStart);
    const recER = recent.filter(p=>p.er!=null);
    const prER  = prior.filter(p=>p.er!=null);
    const recAvg = recER.length ? recER.reduce((s,p)=>s+p.er,0)/recER.length : 0;
    const prAvg  = prER.length  ? prER.reduce((s,p)=>s+p.er,0)/prER.length   : 0;
    const recEng = recent.length ? recent.reduce((s,p)=>s+p.engagement,0)/recent.length : 0;
    const prEng  = prior.length  ? prior.reduce((s,p)=>s+p.engagement,0)/prior.length   : 0;
    const erDelta = prAvg>0 ? (recAvg/prAvg-1)*100 : 0;
    const engDelta = prEng>0 ? (recEng/prEng-1)*100 : 0;
    return {a, recN:recent.length, prN:prior.length, recAvg, prAvg, erDelta, recEng, prEng, engDelta};
  });
  rows.sort((a,b)=>b.erDelta-a.erDelta);
  let html = '<div style="font-size:11px;color:var(--mut);margin-bottom:8px">Last 90d vs prior 90d engagement-rate trajectory. Who is accelerating, who is plateauing.</div>';
  html += '<table><thead><tr><th>Account</th><th class="num">Posts last 90d</th><th class="num">Prior 90d ER</th><th class="num">Last 90d ER</th><th>ER Δ</th><th class="num">Prior eng</th><th class="num">Last eng</th><th>Eng Δ</th></tr></thead><tbody>';
  for(const r of rows){
    const erCls = r.erDelta>5 ? 'up' : r.erDelta<-5 ? 'down' : 'flat';
    const erArrow = r.erDelta>5?'▲':r.erDelta<-5?'▼':'▬';
    const engCls = r.engDelta>5 ? 'up' : r.engDelta<-5 ? 'down' : 'flat';
    const engArrow = r.engDelta>5?'▲':r.engDelta<-5?'▼':'▬';
    html += `<tr><td><span class="pill" style="background:${rgba(r.a.color,.2)};color:${r.a.color}">@${r.a.handle}</span></td><td class="num">${r.recN}</td><td class="num">${(r.prAvg*100).toFixed(2)}%</td><td class="num">${(r.recAvg*100).toFixed(2)}%</td><td><span class="momentum-arrow ${erCls}">${erArrow} ${(r.erDelta>=0?'+':'')}${r.erDelta.toFixed(0)}%</span></td><td class="num">${fmt(r.prEng)}</td><td class="num">${fmt(r.recEng)}</td><td><span class="momentum-arrow ${engCls}">${engArrow} ${(r.engDelta>=0?'+':'')}${r.engDelta.toFixed(0)}%</span></td></tr>`;
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

// ---- "So What" recommendation engine ----
function soWhatPanel(accs){
  const el = document.getElementById('panel_sowhat'); if(!el) return;
  if(accs.length<2){ el.innerHTML='<div class="muted">Select 2+ accounts to generate prescriptive recommendations.</div>'; return; }
  // Identify "the focal account" = either Pantheon if selected, else first one
  const focal = accs.find(a=>a.handle.includes('pantheon')) || accs[0];
  const peers = accs.filter(a=>a.handle!==focal.handle);
  const focalOwn = ownByAcc(focal.handle);
  function avgER(arr){ const v=arr.filter(p=>p.er!=null); return v.length?v.reduce((s,p)=>s+p.er,0)/v.length:0; }
  function themeShares(arr){ const t={}; const tot=arr.length||1; for(const p of arr){const k=p.theme||'Uncategorized';t[k]=(t[k]||0)+1;} for(const k in t) t[k]/=tot; return t; }
  function avgEng(arr){ const v=arr.filter(p=>p.engagement!=null); return v.length?v.reduce((s,p)=>s+p.engagement,0)/v.length:0; }
  function ctaShare(arr){ return arr.length?arr.filter(p=>p.hasCTA).length/arr.length:0; }
  function fvShare(arr){ return arr.length?arr.filter(p=>p.founderVoice).length/arr.length:0; }

  const recos = [];

  // 1. ER gap vs best peer
  const focalER = avgER(focalOwn);
  const peerERs = peers.map(p=>({h:p.handle,er:avgER(ownByAcc(p.handle))})).sort((a,b)=>b.er-a.er);
  if(peerERs.length && peerERs[0].er > focalER*1.5){
    const ratio = (peerERs[0].er/focalER).toFixed(1);
    recos.push({icon:'🚨', txt:`<strong>ER gap:</strong> @${peerERs[0].h} runs <strong>${ratio}× your ER</strong> (${(peerERs[0].er*100).toFixed(2)}% vs ${(focalER*100).toFixed(2)}%). Investigate their winning archetypes below.`});
  }

  // 2. Theme drivers — find themes where each peer outperforms focal
  const focalThemeShares = themeShares(focalOwn);
  const focalThemeAvgEng = {};
  for(const p of focalOwn){ const t=p.theme||'Uncategorized'; (focalThemeAvgEng[t] ||= []).push(p.engagement||0); }
  // Top themes driving peers' lift
  const peerThemeLifts = {};
  for(const peer of peers){
    const peerOwn = ownByAcc(peer.handle);
    for(const t of Object.keys(themeShares(peerOwn))){
      const peerThemePosts = peerOwn.filter(p=>p.theme===t);
      const peerThemeEng = peerThemePosts.length ? peerThemePosts.reduce((s,p)=>s+(p.engagement||0),0)/peerThemePosts.length : 0;
      const focalThemeEng = focalThemeAvgEng[t]?.length ? focalThemeAvgEng[t].reduce((s,x)=>s+x,0)/focalThemeAvgEng[t].length : 0;
      if(peerThemeEng > focalThemeEng*1.5 && peerThemePosts.length>=3){
        peerThemeLifts[t] = Math.max(peerThemeLifts[t]||0, peerThemeEng);
      }
    }
  }
  const topLiftThemes = Object.entries(peerThemeLifts).sort((a,b)=>b[1]-a[1]).slice(0,3);
  if(topLiftThemes.length){
    recos.push({icon:'🎯', txt:`<strong>Themes peers win on:</strong> ${topLiftThemes.map(([t])=>escHtml(t)).join(', ')}. Lean into these — they consistently outperform your equivalents.`});
  }

  // 3. Themes focal under-indexes vs peer mean
  const allThemes = new Set();
  accs.forEach(a=>ownByAcc(a.handle).forEach(p=>allThemes.add(p.theme||'Uncategorized')));
  const underIdx = [];
  for(const t of allThemes){
    const focalShare = focalThemeShares[t]||0;
    const peerAvgShare = peers.reduce((s,p)=>s+(themeShares(ownByAcc(p.handle))[t]||0),0)/Math.max(peers.length,1);
    if(peerAvgShare - focalShare > 0.05 && peerAvgShare>0.08){
      underIdx.push({t, gap:(peerAvgShare-focalShare)*100});
    }
  }
  underIdx.sort((a,b)=>b.gap-a.gap);
  if(underIdx.slice(0,2).length){
    recos.push({icon:'📉', txt:`<strong>Content gaps:</strong> You under-index on ${underIdx.slice(0,2).map(x=>`<em>${escHtml(x.t)}</em> (-${x.gap.toFixed(0)}pp)`).join(' and ')}. Peers spend meaningful share here.`});
  }

  // 4. CTA share
  const focalCTA = ctaShare(focalOwn);
  const peerCTAavg = peers.reduce((s,p)=>s+ctaShare(ownByAcc(p.handle)),0)/Math.max(peers.length,1);
  if(peerCTAavg - focalCTA > 0.1){
    recos.push({icon:'📞', txt:`<strong>CTA discipline:</strong> Only ${(focalCTA*100).toFixed(0)}% of your posts carry a CTA vs peer average ${(peerCTAavg*100).toFixed(0)}%. Add Book / Register / WhatsApp prompts to leads-generating posts.`});
  }

  // 5. Founder voice
  const focalFV = fvShare(focalOwn);
  if(focalFV < 0.05 && focal.handle.includes('pantheon')){
    recos.push({icon:'🎤', txt:`<strong>Founder voice:</strong> Only ${(focalFV*100).toFixed(0)}% of your posts read as founder-led. Your peers leverage personality — your brand sounds corporate.`});
  }

  // 6. Cadence
  function postsWk(arr){ const ts=arr.map(p=>p.ts_ms).filter(Boolean); if(!ts.length)return 0; const s=(Math.max(...ts)-Math.min(...ts))/(7*864e5); return s>0?arr.length/s:arr.length; }
  const focalCad = postsWk(focalOwn);
  const peerCadAvg = peers.reduce((s,p)=>s+postsWk(ownByAcc(p.handle)),0)/Math.max(peers.length,1);
  if(peerCadAvg > focalCad*1.3){
    recos.push({icon:'⏱️', txt:`<strong>Cadence:</strong> You post ${focalCad.toFixed(1)}/wk vs peers averaging ${peerCadAvg.toFixed(1)}/wk. Reach starvation may be partly a volume issue.`});
  } else if(focalCad > peerCadAvg*1.3){
    recos.push({icon:'⏱️', txt:`<strong>Cadence:</strong> You post ${focalCad.toFixed(1)}/wk vs peers ${peerCadAvg.toFixed(1)}/wk — your problem is NOT volume. Look at quality and distribution.`});
  }

  // 7. Likely-boosted footprint
  const focalReels = focalOwn.filter(p=>(p.views||0)>0);
  const focalBoosted = focalReels.filter(p=>p.likelyBoosted).length;
  let mostBoostedPeer = null, mostBoostedPct = 0;
  for(const peer of peers){
    const peerReels = ownByAcc(peer.handle).filter(p=>(p.views||0)>0);
    if(!peerReels.length) continue;
    const pct = peerReels.filter(p=>p.likelyBoosted).length/peerReels.length;
    if(pct > mostBoostedPct){ mostBoostedPct = pct; mostBoostedPeer = peer; }
  }
  if(mostBoostedPeer && mostBoostedPct > 0.1){
    recos.push({icon:'💰', txt:`<strong>Likely paid amplification:</strong> ~${(mostBoostedPct*100).toFixed(0)}% of @${mostBoostedPeer.handle}'s reels show view anomalies (heuristic — likely boosted). Their organic-only numbers are smaller than headline.`});
  }

  if(!recos.length){
    el.innerHTML = '<div class="sowhat"><div class="lead">Recommendations</div><div class="reco"><span class="icon">✅</span><span>Selected accounts are roughly balanced — no major gaps detected.</span></div></div>';
    return;
  }
  let html = `<div class="sowhat"><div class="lead">What to do — recommendations for <strong style="color:${focal.color}">@${escHtml(focal.handle)}</strong> vs peers</div>`;
  for(const r of recos){
    html += `<div class="reco"><span class="icon">${r.icon}</span><span>${r.txt}</span></div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
}

// ---- Dashboard footer (freshness, cost, count) ----
function renderDashFooter(){
  const el = document.getElementById('dash-footer'); if(!el) return;
  const now = Date.now();
  const ageDays = META.dataMaxTsMs ? Math.floor((now - META.dataMaxTsMs)/864e5) : null;
  const isStale = ageDays!=null && ageDays > 7;
  const freshness = META.dataMaxTsMs ? new Date(META.dataMaxTsMs).toISOString().slice(0,10) : '—';
  const ownN = META.ownPostCount;
  const totalN = META.postCount;
  const costAED = META.estimatedScrapeCostAED;
  const costUSD = META.estimatedScrapeCostUSD;
  el.innerHTML = `
    <div class="col"><strong>Data freshness</strong>: latest post ${freshness}${ageDays!=null?` <span class="${isStale?'stale':''}">(${ageDays}d ago)</span>`:''}</div>
    <div class="col"><strong>Posts indexed</strong>: ${fmt(totalN)} total · ${fmt(ownN)} own</div>
    <div class="col"><strong>Tracked accounts</strong>: ${ACCOUNTS.length} (${ACCOUNTS.filter(a=>a.segment==='Founder').length} founder · ${ACCOUNTS.filter(a=>a.segment==='Enterprise').length} enterprise)</div>
    <div class="col"><strong>Estimated scrape cost</strong>: AED ${costAED.toFixed(2)} <span style="opacity:.6">(~$${costUSD.toFixed(2)} · ${totalN} items × AED ${META.apifyCostPerPostAED.toFixed(4)})</span></div>
    <div class="col" style="margin-left:auto;font-size:11px;opacity:.7">Generated ${new Date(META.generatedAtMs).toLocaleString('en-GB',{timeZone:'Asia/Dubai',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})} <span style="opacity:.7">GST (Dubai)</span></div>
  `;
}

// ---- Wire PDF print button ----
(function(){
  const btn = document.getElementById('btn-print');
  if(btn) btn.addEventListener('click', ()=>{
    // Force-expand any open <details> so they print
    document.querySelectorAll('details').forEach(d=>d.setAttribute('open',''));
    window.print();
  });
})();

// ---- Hook drawAll so new panels render on every view ----
(function(){
  const _origDrawAll = drawAll;
  drawAll = function(accs){
    _origDrawAll(accs);
    archetypeHeatmap(accs);
    hookLeaderboard(accs);
    ctaPanel(accs);
    voiceSignalPanel(accs);
    likelyBoostedPanel(accs);
    momentum90dPanel(accs);
  };
  const _origDrawComparison = drawComparison;
  drawComparison = function(accs){
    _origDrawComparison(accs);
    archetypeHeatmap(accs);
    hookLeaderboard(accs);
    ctaPanel(accs);
    voiceSignalPanel(accs);
    likelyBoostedPanel(accs);
    momentum90dPanel(accs);
    contentGapMatrix(accs);
    inboundCredibilityScoreboard(accs);
    founderBrandFlywheel();
    soWhatPanel(accs);
  };
})();

// ---- Splice new panel containers into renderComparison and the drill-down layout ----
(function(){
  const _origRenderComparison = renderComparison;
  renderComparison = function(accs){
    let html = _origRenderComparison(accs);
    // Append new sections before the final closing
    const extras = `
      <div class="section-title">"So what" — Recommendations <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— rule-based, focal account vs peers</span></div>
      <div class="card span-12"><div id="panel_sowhat"></div></div>

      <div class="section-title">90-day momentum <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— who's accelerating</span></div>
      <div class="card span-12"><div id="panel_momentum"></div></div>

      <div class="section-title">Content gap matrix <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— themes × accounts heatmap</span></div>
      <div class="card span-12"><div id="panel_gap"></div></div>

      <div class="section-title">Founder ↔ Brand flywheel <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— unrealized amplification</span></div>
      <div class="card span-12"><div id="panel_flywheel"></div></div>

      <div class="section-title">Post archetype × performance <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— caption length × hashtag count → median ER</span></div>
      <div class="card span-7"><h3>Archetype heatmap</h3><div id="panel_archetype"></div></div>
      <div class="card span-5"><h3>Founder-voice signal</h3><div id="panel_voice"></div></div>

      <div class="section-title">Hook & CTA analysis <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— what stops the scroll, what converts</span></div>
      <div class="card span-7"><h3>Top hooks (first 3 words)</h3><div id="panel_hook"></div></div>
      <div class="card span-5"><h3>CTA correlation</h3><div id="panel_cta"></div></div>

      <div class="section-title">Inbound credibility scoreboard <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— earned media weighted by tier × engagement</span></div>
      <div class="card span-12"><div id="panel_credibility"></div></div>

      <div class="section-title">Likely-boosted estimate <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— heuristic only · real paid/organic split needs account access</span></div>
      <div class="card span-12"><div id="panel_boosted"></div></div>
    `;
    return html + extras;
  };

  // Drill-down: append a subset of new panels into the per-account view
  const _origBuildLayout = buildLayout;
  buildLayout = function(accs){
    let html = _origBuildLayout(accs);
    const extras = `
      <div class="section-title">90-day momentum</div>
      <div class="card span-12"><div id="panel_momentum"></div></div>
      <div class="section-title">Post archetype × performance</div>
      <div class="card span-7"><h3>Archetype heatmap</h3><div id="panel_archetype"></div></div>
      <div class="card span-5"><h3>Founder-voice signal</h3><div id="panel_voice"></div></div>
      <div class="section-title">Hook & CTA analysis</div>
      <div class="card span-7"><h3>Top hooks (first 3 words)</h3><div id="panel_hook"></div></div>
      <div class="card span-5"><h3>CTA correlation</h3><div id="panel_cta"></div></div>
      <div class="section-title">Likely-boosted estimate</div>
      <div class="card span-12"><div id="panel_boosted"></div></div>
    `;
    return html + extras;
  };

  // Wrap render() to also refresh the footer
  const _origRender = render;
  render = function(){
    _origRender();
    renderDashFooter();
  };
})();

// Initial footer render
renderDashFooter();

// =============================================================================
// THEME LEADERBOARD — SEGMENT COMPARATIVE VIEW (Founder vs Enterprise)
// Aggregates theme/content-pillar performance at the SEGMENT level.
// Surfaces which themes drive engagement for Founders vs Enterprises.
// =============================================================================

function themeBySegmentStats(segment){
  // Returns map: theme -> {count, sumEng, sumViews, avgEng, accCount, topPost}
  const segPosts = DATA.filter(p=>p.segment===segment && p.isOwn);
  const m = {};
  for(const p of segPosts){
    const t = p.theme||'Uncategorized';
    if(!m[t]) m[t]={count:0, sumEng:0, sumViews:0, accs:new Set(), topPost:null};
    m[t].count++;
    m[t].sumEng += (p.engagement||0);
    m[t].sumViews += (p.views||0);
    m[t].accs.add(p.account);
    if(!m[t].topPost || (p.engagement||0)>(m[t].topPost.engagement||0)) m[t].topPost = p;
  }
  for(const t in m){
    m[t].avgEng = m[t].count ? m[t].sumEng / m[t].count : 0;
    m[t].accCount = m[t].accs.size;
  }
  return m;
}

function themeLeaderboardSegmentTable(){
  const el = document.getElementById('panel_theme_segment'); if(!el) return;
  const founderM = themeBySegmentStats('Founder');
  const entM = themeBySegmentStats('Enterprise');
  const founderTotal = Object.values(founderM).reduce((s,x)=>s+x.count,0);
  const entTotal = Object.values(entM).reduce((s,x)=>s+x.count,0);
  const allThemes = [...new Set([...Object.keys(founderM), ...Object.keys(entM)])];
  // Sort by combined post volume
  allThemes.sort((a,b)=>(((entM[b]?.count)||0)+((founderM[b]?.count)||0)) - (((entM[a]?.count)||0)+((founderM[a]?.count)||0)));

  let html = `<div style="font-size:11.5px;color:var(--mut);margin-bottom:10px;line-height:1.5">Segment-level rollup: <strong style="color:var(--ink)">${founderTotal}</strong> own posts across Founders, <strong style="color:var(--ink)">${entTotal}</strong> across Enterprises. Shows where each segment concentrates content and which themes earn the strongest engagement per segment.</div>`;
  html += `<table><thead><tr>
    <th>Theme / Content pillar</th>
    <th class="num" colspan="3" style="background:rgba(91,156,255,.12);border-bottom:2px solid #5b9cff">👤 Founders</th>
    <th class="num" colspan="3" style="background:rgba(255,122,182,.12);border-bottom:2px solid #ff7ab6">🏢 Enterprises</th>
    <th>Eng winner</th>
  </tr><tr>
    <th></th>
    <th class="num" style="background:rgba(91,156,255,.06)">Posts</th><th class="num" style="background:rgba(91,156,255,.06)">Share</th><th class="num" style="background:rgba(91,156,255,.06)">Avg eng</th>
    <th class="num" style="background:rgba(255,122,182,.06)">Posts</th><th class="num" style="background:rgba(255,122,182,.06)">Share</th><th class="num" style="background:rgba(255,122,182,.06)">Avg eng</th>
    <th></th>
  </tr></thead><tbody>`;
  for(const t of allThemes){
    const f = founderM[t] || {count:0,sumEng:0,avgEng:0,accCount:0};
    const e = entM[t] || {count:0,sumEng:0,avgEng:0,accCount:0};
    if(!f.count && !e.count) continue;
    const fShare = founderTotal ? f.count/founderTotal : 0;
    const eShare = entTotal ? e.count/entTotal : 0;
    const color = THEME_PALETTE[t] || '#888';
    // Engagement winner
    let winnerCell = '<span class="muted">—</span>';
    if(f.avgEng>0 && e.avgEng>0){
      if(f.avgEng > e.avgEng*1.2){
        const mult = (f.avgEng/e.avgEng).toFixed(1);
        winnerCell = `<span class="pill" style="background:rgba(91,156,255,.2);color:#5b9cff">👤 Founders ${mult}×</span>`;
      } else if(e.avgEng > f.avgEng*1.2){
        const mult = (e.avgEng/f.avgEng).toFixed(1);
        winnerCell = `<span class="pill" style="background:rgba(255,122,182,.2);color:#ff7ab6">🏢 Enterprises ${mult}×</span>`;
      } else {
        winnerCell = `<span class="pill" style="background:rgba(136,149,173,.15);color:var(--mut)">≈ Tied</span>`;
      }
    } else if(f.avgEng>0){
      winnerCell = `<span class="pill" style="background:rgba(91,156,255,.2);color:#5b9cff">👤 Founder only</span>`;
    } else if(e.avgEng>0){
      winnerCell = `<span class="pill" style="background:rgba(255,122,182,.2);color:#ff7ab6">🏢 Enterprise only</span>`;
    }
    html += `<tr>
      <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle"></span>${escHtml(t)}</td>
      <td class="num" style="background:rgba(91,156,255,.04)">${f.count}</td>
      <td class="num" style="background:rgba(91,156,255,.04)">${(fShare*100).toFixed(1)}%</td>
      <td class="num" style="background:rgba(91,156,255,.04)"><strong>${fmt(f.avgEng)}</strong></td>
      <td class="num" style="background:rgba(255,122,182,.04)">${e.count}</td>
      <td class="num" style="background:rgba(255,122,182,.04)">${(eShare*100).toFixed(1)}%</td>
      <td class="num" style="background:rgba(255,122,182,.04)"><strong>${fmt(e.avgEng)}</strong></td>
      <td>${winnerCell}</td>
    </tr>`;
  }
  html += `</tbody></table>`;
  el.innerHTML = html;
}

function themeMixSegmentChart(){
  const el = document.getElementById('panel_theme_segment_mix'); if(!el) return;
  const fM = themeBySegmentStats('Founder');
  const eM = themeBySegmentStats('Enterprise');
  const themes = [...new Set([...Object.keys(fM), ...Object.keys(eM)])];
  // Sort by total share
  themes.sort((a,b)=>((eM[b]?.count||0)+(fM[b]?.count||0)) - ((eM[a]?.count||0)+(fM[a]?.count||0)));
  const fTotal = Object.values(fM).reduce((s,x)=>s+x.count,0) || 1;
  const eTotal = Object.values(eM).reduce((s,x)=>s+x.count,0) || 1;
  // Render as paired horizontal bars: % share per segment per theme
  let html = `<div style="font-size:11px;color:var(--mut);margin-bottom:10px">Content pillar distribution — how each segment allocates its content mix.</div>`;
  for(const t of themes){
    const fShare = ((fM[t]?.count||0)/fTotal)*100;
    const eShare = ((eM[t]?.count||0)/eTotal)*100;
    if(fShare<0.5 && eShare<0.5) continue;
    const color = THEME_PALETTE[t] || '#888';
    const maxBar = Math.max(fShare, eShare, 1);
    const barFw = (fShare/Math.max(maxBar,30))*100;
    const barEw = (eShare/Math.max(maxBar,30))*100;
    html += `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;font-size:12px">
        <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle"></span>${escHtml(t)}</span>
        <span style="font-size:11px;color:var(--mut)">👤 ${fShare.toFixed(1)}% · 🏢 ${eShare.toFixed(1)}%</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:var(--bd);border-radius:4px;overflow:hidden;height:14px"><div style="background:#5b9cff;height:100%;width:${barFw}%;transition:width .3s" title="Founders: ${fShare.toFixed(1)}%"></div></div>
        <div style="background:var(--bd);border-radius:4px;overflow:hidden;height:14px"><div style="background:#ff7ab6;height:100%;width:${barEw}%;transition:width .3s" title="Enterprises: ${eShare.toFixed(1)}%"></div></div>
      </div>
    </div>`;
  }
  html += `<div style="display:flex;gap:18px;font-size:11px;color:var(--mut);margin-top:8px;border-top:1px solid var(--bd);padding-top:8px">
    <span><span style="display:inline-block;width:10px;height:10px;background:#5b9cff;margin-right:6px;vertical-align:middle"></span>👤 Founder share</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#ff7ab6;margin-right:6px;vertical-align:middle"></span>🏢 Enterprise share</span>
  </div>`;
  el.innerHTML = html;
}

function themeEngagementSegmentChart(){
  const el = document.getElementById('panel_theme_segment_eng'); if(!el) return;
  const fM = themeBySegmentStats('Founder');
  const eM = themeBySegmentStats('Enterprise');
  const themes = [...new Set([...Object.keys(fM), ...Object.keys(eM)])]
    .filter(t=>((fM[t]?.count||0)>=3 || (eM[t]?.count||0)>=3));  // require min sample
  // Sort by best segment's avg eng
  themes.sort((a,b)=>Math.max(eM[b]?.avgEng||0, fM[b]?.avgEng||0) - Math.max(eM[a]?.avgEng||0, fM[a]?.avgEng||0));
  if(!themes.length){ el.innerHTML='<div class="muted">Not enough data per theme</div>'; return; }
  // Find max for scaling
  const maxEng = Math.max(...themes.flatMap(t=>[fM[t]?.avgEng||0, eM[t]?.avgEng||0]));
  let html = `<div style="font-size:11px;color:var(--mut);margin-bottom:10px">Avg engagement per post by theme · per segment (themes with n≥3 posts in at least one segment).</div>`;
  for(const t of themes){
    const fE = fM[t]?.avgEng || 0;
    const eE = eM[t]?.avgEng || 0;
    const color = THEME_PALETTE[t] || '#888';
    const fBar = maxEng ? (fE/maxEng)*100 : 0;
    const eBar = maxEng ? (eE/maxEng)*100 : 0;
    html += `<div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;font-size:12px">
        <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:8px;vertical-align:middle"></span>${escHtml(t)}</span>
        <span style="font-size:11px;color:var(--mut)">👤 ${fmt(fE)} · 🏢 ${fmt(eE)}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:var(--bd);border-radius:4px;overflow:hidden;height:14px"><div style="background:#5b9cff;height:100%;width:${fBar}%" title="Founders avg ${fmt(fE)}"></div></div>
        <div style="background:var(--bd);border-radius:4px;overflow:hidden;height:14px"><div style="background:#ff7ab6;height:100%;width:${eBar}%" title="Enterprises avg ${fmt(eE)}"></div></div>
      </div>
    </div>`;
  }
  el.innerHTML = html;
}

// Splice the segment-comparative theme section into Comparison view
(function(){
  const _origRC = renderComparison;
  renderComparison = function(accs){
    let h = _origRC(accs);
    h += `
      <div class="section-title">Theme Leaderboard — Segment comparison <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— Founders vs Enterprises content pillar strategy</span></div>
      <div class="card span-12"><h3>By segment · post share, avg engagement, head-to-head winner per theme</h3><div id="panel_theme_segment" style="overflow-x:auto"></div></div>
      <div class="card span-6"><h3>Content pillar distribution <span class="tag">% share by segment</span></h3><div id="panel_theme_segment_mix"></div></div>
      <div class="card span-6"><h3>Avg engagement per theme <span class="tag">by segment</span></h3><div id="panel_theme_segment_eng"></div></div>`;
    return h;
  };
  const _origDC = drawComparison;
  drawComparison = function(accs){
    _origDC(accs);
    themeLeaderboardSegmentTable();
    themeMixSegmentChart();
    themeEngagementSegmentChart();
  };
})();

// =============================================================================
// COLLABORATION ANALYSIS
// Strongest signal: IG-native Collab posts (coauthorProducers) — both accounts
// co-own the post. Second: bidirectional tags (A tags B AND B tags A). Third:
// one-way tags. Each row exposes the handle AND the IG numeric account ID.
// =============================================================================

function buildCollabIndex(){
  // Returns { inbound: {accH -> [{partnerU, partnerId, postCount, engSum, coAuthor, verified, fullName, topPost, isBidirectional}]},
  //           outbound: {accH -> [...same shape...]} }
  const inbound = {};
  const outbound = {};
  const accountHandles = new Set(ACCOUNTS.map(a=>a.handle));

  // Build outbound from each tracked account's OWN posts
  for(const a of ACCOUNTS){
    const own = DATA.filter(p=>p.account===a.handle && p.isOwn);
    const map = {};  // partnerU -> stats
    for(const p of own){
      const partners = new Map();  // u -> {id, verified, name, coAuthor}
      for(const t of (p.taggedFull||[])){
        if(!t.u || t.u===a.handle) continue;
        partners.set(t.u, {id:t.id, verified:t.verified, name:t.name, coAuthor:false});
      }
      for(const c of (p.coauthors||[])){
        if(!c.u || c.u===a.handle) continue;
        const ex = partners.get(c.u) || {id:c.id, verified:false, name:'', coAuthor:false};
        ex.id = ex.id || c.id; ex.coAuthor = true;
        partners.set(c.u, ex);
      }
      for(const [u,meta] of partners){
        if(!map[u]) map[u] = {partnerU:u, partnerId:meta.id||'', verified:meta.verified, fullName:meta.name||'',
                              postCount:0, engSum:0, reachSum:0, coAuthorCount:0, topPost:null};
        const s = map[u];
        s.postCount++; s.engSum += p.engagement||0; s.reachSum += p.views||0;
        if(meta.coAuthor) s.coAuthorCount++;
        if(meta.id && !s.partnerId) s.partnerId = meta.id;
        if(meta.verified) s.verified = true;
        if(meta.name && !s.fullName) s.fullName = meta.name;
        if(!s.topPost || (p.engagement||0)>(s.topPost.engagement||0)) s.topPost = p;
      }
    }
    outbound[a.handle] = Object.values(map);
  }

  // Build inbound: posts where this account appears as OWNER on a non-isOwn record,
  // OR appears tagged in another tracked account's own posts.
  for(const a of ACCOUNTS){
    const map = {};  // taggerU -> stats
    // (1) Tracked-account own posts that tag/coauthor this account
    for(const peer of ACCOUNTS){
      if(peer.handle===a.handle) continue;
      const peerOwn = DATA.filter(p=>p.account===peer.handle && p.isOwn);
      for(const p of peerOwn){
        const taggedUs = new Map();
        for(const t of (p.taggedFull||[])){
          if(t.u===a.handle) taggedUs.set(peer.handle, {id:peer.handle, verified:false, name:peer.fullName, coAuthor:false});
        }
        for(const c of (p.coauthors||[])){
          if(c.u===a.handle){
            const ex = taggedUs.get(peer.handle) || {id:peer.handle, verified:false, name:peer.fullName, coAuthor:false};
            ex.coAuthor = true; taggedUs.set(peer.handle, ex);
          }
        }
        if(!taggedUs.size) continue;
        const meta = taggedUs.get(peer.handle);
        const u = peer.handle;
        if(!map[u]) map[u]={partnerU:u, partnerId:p.ownerId||'', verified:!!ACCOUNTS.find(x=>x.handle===u)?.verified, fullName:peer.fullName||'',
                            postCount:0, engSum:0, reachSum:0, coAuthorCount:0, topPost:null};
        const s = map[u];
        s.postCount++; s.engSum += p.engagement||0; s.reachSum += p.views||0;
        if(meta.coAuthor) s.coAuthorCount++;
        if(p.ownerId && !s.partnerId) s.partnerId = p.ownerId;
        if(!s.topPost || (p.engagement||0)>(s.topPost.engagement||0)) s.topPost = p;
      }
    }
    // (2) Non-tracked accounts that posted ABOUT this account (untracked inbound — show by ownerUsername)
    const inboundPosts = DATA.filter(p=>p.account===a.handle && !p.isOwn);
    for(const p of inboundPosts){
      const u = (p.owner||'').toLowerCase();
      if(!u || accountHandles.has(u)) continue;  // skip tracked (already handled above)
      if(!map[u]) map[u]={partnerU:u, partnerId:p.ownerId||'', verified:false, fullName:'',
                          postCount:0, engSum:0, reachSum:0, coAuthorCount:0, topPost:null};
      const s = map[u];
      s.postCount++; s.engSum += p.engagement||0; s.reachSum += p.views||0;
      if(p.ownerId && !s.partnerId) s.partnerId = p.ownerId;
      if(!s.topPost || (p.engagement||0)>(s.topPost.engagement||0)) s.topPost = p;
    }
    inbound[a.handle] = Object.values(map);
  }

  // Flag bidirectional partnerships
  for(const a of ACCOUNTS){
    const outSet = new Set((outbound[a.handle]||[]).map(x=>x.partnerU));
    for(const row of (inbound[a.handle]||[])){
      row.isBidirectional = outSet.has(row.partnerU);
    }
    const inSet = new Set((inbound[a.handle]||[]).map(x=>x.partnerU));
    for(const row of (outbound[a.handle]||[])){
      row.isBidirectional = inSet.has(row.partnerU);
    }
  }
  return {inbound, outbound};
}

function _renderCollabRow(r, perspective){
  // perspective: 'inbound' | 'outbound'
  const verifiedBadge = r.verified ? ' <span style="color:#5b9cff;font-size:11px">✓</span>' : '';
  const coBadge = r.coAuthorCount>0
    ? `<span class="pill" style="background:rgba(70,211,160,.2);color:var(--ok);font-size:10px" title="IG Collab post — both accounts co-own">🤝 Collab × ${r.coAuthorCount}</span>` : '';
  const biBadge = r.isBidirectional
    ? `<span class="pill" style="background:rgba(91,156,255,.2);color:#5b9cff;font-size:10px" title="Both accounts tag each other">↔ Bidirectional</span>` : '';
  const tp = r.topPost;
  const tpLink = tp && tp.url ? `<a href="${escHtml(tp.url)}" target="_blank">${fmt(tp.engagement)} eng ↗</a>` : '—';
  const idTxt = r.partnerId ? `<code style="font-size:10px;color:var(--mut)">ID ${escHtml(r.partnerId)}</code>` : '<span class="muted">—</span>';
  return `<tr>
    <td><a target="_blank" href="https://www.instagram.com/${escHtml(r.partnerU)}/">@${escHtml(r.partnerU)}</a>${verifiedBadge}${r.fullName?`<div style="font-size:11px;color:var(--mut)">${escHtml(r.fullName)}</div>`:''}</td>
    <td>${idTxt}</td>
    <td class="num">${r.postCount}</td>
    <td class="num">${fmt(r.engSum)}</td>
    <td class="num">${r.reachSum?fmt(r.reachSum):'—'}</td>
    <td>${coBadge}${coBadge&&biBadge?' ':''}${biBadge}</td>
    <td>${tpLink}</td>
  </tr>`;
}

function collaborationPanel(accs){
  const out = document.getElementById('panel_collab_out');
  const ins = document.getElementById('panel_collab_in');
  const sum = document.getElementById('panel_collab_summary');
  if(!out || !ins) return;
  const {inbound, outbound} = buildCollabIndex();

  // Summary KPIs (one card per selected account)
  if(sum){
    let sumHtml = `<div style="display:grid;grid-template-columns:repeat(${Math.min(accs.length,4)},1fr);gap:12px">`;
    for(const a of accs){
      const ob = outbound[a.handle]||[]; const ib = inbound[a.handle]||[];
      const trueCollabs = ob.filter(r=>r.coAuthorCount>0).length + ib.filter(r=>r.coAuthorCount>0).length;
      const bi = ob.filter(r=>r.isBidirectional).length;
      const verified = [...ob, ...ib].filter(r=>r.verified).length;
      sumHtml += `<div style="border:1px solid ${rgba(a.color,.4)};border-radius:10px;padding:12px;background:${rgba(a.color,.06)}">
        <div style="font-weight:700;font-size:13px;margin-bottom:8px">@${escHtml(a.handle)}</div>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;font-size:11px">
          <div><div style="color:var(--mut);text-transform:uppercase;letter-spacing:.05em;font-size:10px">Outbound partners</div><div style="font-size:18px;font-weight:700">${ob.length}</div></div>
          <div><div style="color:var(--mut);text-transform:uppercase;letter-spacing:.05em;font-size:10px">Inbound partners</div><div style="font-size:18px;font-weight:700">${ib.length}</div></div>
          <div><div style="color:var(--mut);text-transform:uppercase;letter-spacing:.05em;font-size:10px">IG Collabs 🤝</div><div style="font-size:18px;font-weight:700;color:var(--ok)">${trueCollabs}</div></div>
          <div><div style="color:var(--mut);text-transform:uppercase;letter-spacing:.05em;font-size:10px">Bidirectional ↔</div><div style="font-size:18px;font-weight:700;color:#5b9cff">${bi}</div></div>
        </div>
      </div>`;
    }
    sumHtml += `</div>`;
    sum.innerHTML = sumHtml;
  }

  // Outbound table — who this account collaborates WITH
  function buildTable(forAcc, side){
    const rows = (side==='out' ? outbound[forAcc.handle] : inbound[forAcc.handle])||[];
    rows.sort((a,b)=>{
      // Sort: coauthor count → bidirectional → engagement
      if(b.coAuthorCount !== a.coAuthorCount) return b.coAuthorCount - a.coAuthorCount;
      if((b.isBidirectional?1:0) !== (a.isBidirectional?1:0)) return (b.isBidirectional?1:0)-(a.isBidirectional?1:0);
      return b.engSum - a.engSum;
    });
    const top = rows.slice(0,25);
    if(!top.length) return `<div class="muted" style="padding:8px">No ${side==='out'?'outbound':'inbound'} collaborators for @${escHtml(forAcc.handle)}</div>`;
    return `<table><thead><tr>
      <th>Partner</th><th>IG account ID</th><th class="num">Posts</th><th class="num">Σ engagement</th><th class="num">Σ reach</th><th>Signal</th><th>Top post</th>
    </tr></thead><tbody>${top.map(r=>_renderCollabRow(r, side)).join('')}</tbody></table>`;
  }
  let outHtml = '', inHtml = '';
  for(const a of accs){
    const accHeader = `<div style="display:flex;align-items:center;gap:10px;margin:18px 0 8px 0">${avatarHTML(a)}<div><div style="font-weight:700">@${escHtml(a.handle)}</div><div style="font-size:11px;color:var(--mut)">${a.segment}</div></div></div>`;
    outHtml += accHeader + buildTable(a,'out');
    inHtml  += accHeader + buildTable(a,'in');
  }
  out.innerHTML = outHtml + `<div style="font-size:11px;color:var(--mut);margin-top:10px;line-height:1.5">🤝 = IG-native Collab post (both accounts co-own — strongest signal). ↔ = bidirectional (both tag each other). Sorted by Collabs → bidirectional → total engagement. <strong>IG account ID</strong> is captured from Instagram\'s internal user ID.</div>`;
  ins.innerHTML = inHtml + `<div style="font-size:11px;color:var(--mut);margin-top:10px;line-height:1.5">Inbound = who tagged or co-authored content featuring this account. Includes both tracked peers and untracked external accounts.</div>`;
}

// Add Collaboration panel containers to renderComparison and drill-down
(function(){
  const _origRC = renderComparison;
  renderComparison = function(accs){
    let h = _origRC(accs);
    h += `
      <div class="section-title">Collaboration Analysis <span style="color:var(--mut);text-transform:none;font-weight:400;letter-spacing:0">— IG Collabs · bidirectional partnerships · account IDs captured</span></div>
      <div class="card span-12"><div id="panel_collab_summary"></div></div>
      <div class="card span-6"><h3>Outbound collaborations <span class="tag">accounts this brand collabs with</span></h3><div id="panel_collab_out" style="overflow-x:auto"></div></div>
      <div class="card span-6"><h3>Inbound collaborations <span class="tag">accounts that tag/coauthor this brand</span></h3><div id="panel_collab_in" style="overflow-x:auto"></div></div>`;
    return h;
  };
  const _origBL = buildLayout;
  buildLayout = function(accs){
    let h = _origBL(accs);
    h += `
      <div class="section-title">Collaboration Analysis</div>
      <div class="card span-12"><div id="panel_collab_summary"></div></div>
      <div class="card span-6"><h3>Outbound collaborations</h3><div id="panel_collab_out" style="overflow-x:auto"></div></div>
      <div class="card span-6"><h3>Inbound collaborations</h3><div id="panel_collab_in" style="overflow-x:auto"></div></div>`;
    return h;
  };
  const _origDA = drawAll;
  drawAll = function(accs){ _origDA(accs); collaborationPanel(accs); };
  const _origDC = drawComparison;
  drawComparison = function(accs){ _origDC(accs); collaborationPanel(accs); };
})();
</script>
</body>
</html>
"""

out_path = os.path.join(BASE, "dashboard.html")
HTML = HTML.replace("__GEN__", datetime.now().strftime("%Y-%m-%d %H:%M"))
HTML = HTML.replace("__DATA__", json.dumps(records))
HTML = HTML.replace("__ACCOUNTS__", json.dumps(accounts_catalog))
HTML = HTML.replace("__PALETTE__", json.dumps(PALETTE))

# ---------- META: freshness, cost, founder→brand pairs, credibility tier hints ----------
APIFY_COST_PER_POST = 0.0017  # ~$0.0017 USD per scraped item (rough Apify pricing)
USD_TO_AED = 3.6725             # fixed UAE peg
_ts_ms_list = [r["ts_ms"] for r in records if r.get("ts_ms")]
data_max_ts = max(_ts_ms_list) if _ts_ms_list else None
data_min_ts = min(_ts_ms_list) if _ts_ms_list else None
gen_ts_ms = int(datetime.now().timestamp() * 1000)
META = {
    "generatedAtMs": gen_ts_ms,
    "dataMaxTsMs": data_max_ts,
    "dataMinTsMs": data_min_ts,
    "postCount": len(records),
    "ownPostCount": sum(1 for r in records if r.get("isOwn")),
    "apifyCostPerPostUSD": APIFY_COST_PER_POST,
    "apifyCostPerPostAED": round(APIFY_COST_PER_POST * USD_TO_AED, 4),
    "estimatedScrapeCostUSD": round(len(records) * APIFY_COST_PER_POST, 2),
    "estimatedScrapeCostAED": round(len(records) * APIFY_COST_PER_POST * USD_TO_AED, 2),
    "usdToAed": USD_TO_AED,
    "founderBrandPairs": [
        # (founder handle, brand handle) — these must exist in ACCOUNTS to render
        ["kalpesh.kinariwala",  "pantheon_development"],
        ["ankur.aggarwal01",    "bnw.developments"],
        ["imranfarooqsamana",   "samana.developers"],
    ],
    # Curated credibility tiers for known inbound taggers — used by inboundCredibilityScoreboard
    # Tier 3 = top (major media / verified celeb / massive following); Tier 2 = mid; Tier 1 = niche/peer
    "credibilityTiers": {
        # Major media
        "forbesmiddleeast": 3, "entrepreneur_me": 3, "entrepreneurtvme": 3,
        "gulfnews": 3, "khaleejtimes": 3, "thenationalnews": 3, "arabianbusiness": 3,
        "filmfare": 3, "gulfbusiness": 3, "mashable.me": 3,
        # Celebrities / power partners
        "hrithikroshan": 3, "arijitsingh": 3, "arrahman": 3, "iambageshvardham": 3,
        "yuvis": 3, "rannvijaysingha": 3, "annamalai": 3,
        # Peer brands / industry
        "imtiazdevelopments": 2, "bnw.developments": 2, "samana.developers": 2,
        "danubeproperties": 2, "ellingtonproperties": 2, "emaardubai": 2,
        # Niche/peer creators
        "richkey_properties": 2, "musicunites": 2,
    },
}
HTML = HTML.replace("__META__", json.dumps(META))
with open(out_path, "w", encoding="utf-8") as fh:
    fh.write(HTML)
print(f"Wrote {out_path}")
