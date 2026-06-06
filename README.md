# Pantheon Competitor Intelligence — Instagram Dashboard

A self-hosted analytics dashboard that benchmarks Pantheon's Instagram presence against a curated set of UAE real-estate peers (brands + founders). Built for Pantheon's Brand & Comms team.

## What it tracks

**5 Founder accounts**

| Handle | Notes |
|---|---|
| [@kalpesh.kinariwala](https://www.instagram.com/kalpesh.kinariwala/) | Pantheon Chairman |
| [@ankur.aggarwal01](https://www.instagram.com/ankur.aggarwal01/) | BNW Developments Chairman |
| [@rizwan.sajan](https://www.instagram.com/rizwan.sajan/) | Danube Properties Chairman |
| [@masihimtiaz_official](https://www.instagram.com/masihimtiaz_official/) | Imtiaz Developments CEO |
| [@vivekoberoi](https://www.instagram.com/vivekoberoi/) | Brand-partner / actrepreneur |

**5 Enterprise accounts**

| Handle | Notes |
|---|---|
| [@pantheon_development](https://www.instagram.com/pantheon_development/) | Pantheon (focal account) |
| [@bnw.developments](https://www.instagram.com/bnw.developments/) | BNW Developments |
| [@imtiazdevelopments](https://www.instagram.com/imtiazdevelopments/) | Imtiaz Developments |
| [@samana.developers](https://www.instagram.com/samana.developers/) | SAMANA Developers |
| [@danubeproperties](https://www.instagram.com/danubeproperties/) | Danube Properties |

Tracking window: **May 2025 → May 2026** (12 months, standardised across all accounts).

## What's in the dashboard

For every tracked account: posting cadence, follower growth, engagement health, content theme/pillar mix, hook & CTA analysis, founder-voice signal, inbound + outbound tag/collaboration matrix, post archetype heatmap, likely-boosted view-anomaly flagging, 90-day momentum delta, top hooks leaderboard, founder ↔ brand flywheel paired view.

For the **Comparison** segment: head-to-head battlecards across any selected accounts, content gap matrix, peer-tier benchmarks, prescriptive "So what" recommendation engine, win-loss tally across 7 strategic metrics, Founder vs Enterprise segment-comparative Theme Leaderboard.

## Folder layout

```
.
├── build_dashboard.py            # main builder — reads CSVs + JSON, emits dashboard.html
├── dashboard.html                # built artifact (regenerable)
├── dashboard_server.py           # local HTTP server with /api/scrape endpoint
├── classify_uncategorized.py     # LLM theme classifier (Claude API)
├── seed_theme_overrides.py       # helper to bootstrap theme_overrides.json
├── flatten_to_csv.py             # legacy Apify-JSON flattener
├── meta_graph_scraper.py         # alt path: Meta Graph API scraper
├── theme_overrides.json          # manual theme overrides (highest priority)
├── theme_cache.json              # LLM-classified themes (mid priority)
├── Founder/                      # per-handle scraped posts + reels + profile + avatar
│   ├── ankur.aggarwal01/
│   │   ├── apify_posts_*.csv
│   │   ├── apify_reels_*.csv
│   │   ├── profile.json
│   │   └── avatar.jpg
│   └── ...
├── Enterprise/                   # same structure
│   ├── pantheon_development/
│   └── ...
├── .claude/agents/
│   └── ig-intel-fetcher.md       # Claude Code agent definition for new-account scraping
└── memory/                       # project memory for Claude Code
```

## Running it

### Build the dashboard from current CSVs

```bash
python build_dashboard.py
```

Opens nothing — just regenerates `dashboard.html` in place. Open that file in any browser.

### Local server (with on-demand scrape endpoint)

```bash
set APIFY_TOKEN=apify_api_...
python dashboard_server.py
# Visit http://localhost:8765
```

The server adds a `+` floating button → modal form → POST `/api/scrape` that calls Apify directly for new accounts.

### Re-classify uncategorised posts via Claude

```bash
set ANTHROPIC_API_KEY=sk-ant-...
python classify_uncategorized.py
# writes theme_cache.json
python build_dashboard.py
```

## Data sources

- **Apify** — `apify/instagram-post-scraper`, `apify/instagram-reel-scraper`, `apify/instagram-profile-scraper` (paid)
- **Claude API** (Sonnet 4.5) — for theme classification of residual `Uncategorized` posts (~$0.30 one-off)
- All data scraped fresh per run; nothing pulled from third-party paid analytics tools (HypeAuditor / Modash etc.)

## Localisation

- **Currency**: AED (with USD shown as secondary)
- **Timezone**: GST (Asia/Dubai, UTC+4) for posting heatmaps, calendar, footer timestamps
- **Date format**: en-GB (DD MMM YYYY)

## Notable design decisions

1. **Median ER, not mean** — viral posts (e.g. one Masih Imtiaz reel reached 30× his follower count) inflate the mean dramatically. Median represents the typical post.
2. **Pinned posts excluded from "Standout Posts"** — long-running pinned content unfairly amplifies metrics.
3. **Likely-boosted view-anomaly flag** — heuristic only, labeled honestly. Real paid/organic split needs account-owner access.
4. **Theme classification cascade**: manual overrides → LLM cache → keyword rules → "Uncategorized" fallback.
5. **No silent caps** — every truncation (top-N tables, sample sizes) is disclosed in the UI.

## Cost / freshness

Each rebuild surfaces:
- Estimated Apify spend to reproduce the dataset (AED)
- Data freshness (days since latest post per account)
- Posts indexed (total + own)

## License

Internal / proprietary — Pantheon Development.
