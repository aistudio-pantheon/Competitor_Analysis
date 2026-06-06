# Plan — Paid vs Organic Reach Analysis + Inactive Follower Analysis

## Reality check first — what's NOT possible from public scraping

These two questions sit at the boundary of what scraped Instagram data can answer. Critical limitations:

### 1. True paid vs organic reach split: **NOT POSSIBLE** from public data

- Instagram **does not** expose a "this post was boosted" flag in any public field. Apify can't retrieve it. Neither can any scraping tool.
- The paid/organic breakdown is **only visible to the account owner** inside Meta Business Suite / Ads Manager.
- The `videoViewCount` and `playCount` we have are **total views** (paid + organic combined).
- Workarounds that **don't actually work**:
  - "High like-to-view ratio means paid" — no, varies wildly with content quality
  - "Look for sponsor disclosure" — only applies to paid partnerships with creators, not the brand's own ad spend on its own posts

### 2. True inactive-follower analysis: **NOT POSSIBLE** from public data

- We don't have the **follower list** for any tracked account. Apify can scrape followers but: (a) it's expensive, (b) Instagram aggressively rate-limits it, (c) for Ankur with 5.9M followers it would cost $$$ and likely fail mid-way.
- Even with the follower list, we'd need to track every follower's engagement history — also requires scraping each follower's actions across all accounts.
- This is precisely what HypeAuditor / Modash / Phyllo pay engineering teams to build. They sample millions of comments + likes across Instagram and model out which followers are active.
- The account owner sees their own engagement-by-follower data via Meta Business Suite, but they can't see it for competitors.

---

## What we CAN build — proxies and heuristics

We can build *partial* versions of both — clearly labeled as **estimates** — using only the data we already scrape.

### A. "Likely Boosted" detector (proxy for paid reach)

A post is **likely boosted** when its reach is anomalously high relative to the account's normal reach. Detectable heuristics:

1. **Reach outlier flag**: a post's `views` is >3σ (or >5×) above the account's median reels-view count.
2. **View-to-engagement gap**: a post has many views but low engagement rate vs the account's norm. Boosted posts hit non-followers who view but don't engage.
3. **Audience location skew**: if comment authors' locations are wildly outside the account's normal audience — IG ads tend to spread reach geographically. (Hard to detect from our data since we have limited geo on commenters.)
4. **Explicit paid-partnership tag**: where Apify returns `isPaidPartnership` or `partner_ad` field — surface as confirmed paid.

What we'd show:
- **Per-account split**: "Likely organic 87% · likely boosted 13%" (based on view-anomaly rule)
- **Likely-boosted posts list**: ranked by anomaly score, with their views, ER, and a flag
- **Big disclaimer**: "Heuristic estimate. Real paid/organic split is only visible to the account owner."

### B. Active vs Inactive Audience proxy

We can't measure follower-level inactivity, but we CAN measure the **engaged-audience footprint** vs the **total follower base**.

Compute these from `latestComments` (we have top ~10 comments per scraped post — that's commenter identities) and account followers:

1. **Unique commenters in last 90 days** — distinct `latestComments[].ownerUsername` across all posts in the 90-day window.
2. **Active-audience coverage** = `unique_commenters / total_followers × 100`. Industry baseline: 0.5-3% is normal commenter share; <0.2% = highly inactive audience.
3. **Comment recurrence** = average comments-per-engaged-user. High recurrence = small core fan base; low = broad audience.
4. **Engagement breadth** = ratio of unique commenters to total comments. 1.0 = every comment is unique person; lower = small core.
5. **Repeat-engager segment**: identify users who commented on **3+ posts in 90d** — these are the "loyal core".

What we'd show:
- **Active-audience size**: e.g. "@bnw.developments: 1,247 unique active commenters in last 90d (1.9% of 64.9K followers)"
- **Inactive-audience estimate** = `100% - active%`, labeled "estimated inactive (proxy)"
- **Loyal core size**: count of repeat commenters
- **Per-segment comparison**: founders vs brands typically differ here

**Crucial caveats:**
- We only see TOP comments (Apify caps at ~10/post) — total commenter base is **larger** than what we see, so active% is an undercount.
- A follower who likes but never comments is invisible to us — they look "inactive" but aren't.
- For accounts that disabled comments (a few BNW posts) or where comments are hidden, we miss engagement entirely.

---

## Implementation steps

### Step 1 — Capture more comment data (optional but improves accuracy)

The existing CSVs already have `latestComments/N/ownerUsername` columns up to N=9 (~10 comments per post). For this analysis we should:
- Re-process existing CSVs to extract all `latestComments/*/ownerUsername` columns into a `commenters: []` field per record (currently we don't store this).
- No re-scraping needed — just re-parse what we already have.

### Step 2 — Add the two analyses to build_dashboard.py

In Python:
- Per-account compute `commenterStats` once: unique commenters in 90d, total commenter mentions, repeat-engager count.
- Per-post compute `likelyBoosted` flag: median + std-dev of `views` per account; flag posts with views ≥ median + 3·MAD (median absolute deviation, robust to outliers).
- Surface both onto each record / account-catalog entry.

### Step 3 — Two new dashboard sections (drill-down view)

**Section A — "Audience activity (90d proxy)"**
- KPI tile row: Active commenters · Active % of followers · Loyal core (3+ posts) · Avg comments per engaged user
- Bar chart: unique commenters per week over last 90d (trend)
- Table: top 20 repeat-engagers and how many of this account's posts they engaged with

**Section B — "Likely boosted vs organic posts"**
- KPI tile row: Total posts · Likely-organic count · Likely-boosted count · % boosted
- Scatter chart: views vs ER, with boosted posts highlighted in a different color (boosted posts cluster as "high views + low ER")
- Table: top 10 likely-boosted posts, sorted by anomaly score, with views / ER / link

Both sections get a prominent **methodology note** explaining the heuristic and what it can/can't tell.

### Step 4 — Compare view extensions

In the Comparison battlecards, add two new rows:
- **Active audience %** — engaged-audience coverage estimate
- **Likely-boost %** — share of posts flagged as anomalously high-reach

### Step 5 — Documentation

Update `competitor-intel-project.md` (memory) with:
- Method definitions for both metrics
- Limitations / what they don't measure
- Reminder that for real data, user should subscribe to HypeAuditor / Modash for accounts they care most about

---

## What you'd need to add to get the REAL numbers

If proxies aren't enough:

| Capability | Cost / Tool |
|---|---|
| Real paid vs organic for **your own** accounts | Free — Meta Business Suite if you own the account |
| Real paid vs organic for **competitors** | Impossible. No legal scraping path exists. |
| Real follower-list + activity analysis (competitor) | **HypeAuditor** ($200-$2000/mo) — they sample comments at scale and model out real audience-quality scores including "ghost followers", credibility, demographics |
| Real follower-list + activity analysis (your own) | Free via Meta Business Suite, plus paid tools like **Iconosquare** ($40-$170/mo) |
| Sample-based audience analysis (cheaper) | **Modash** ($200-$1500/mo), **Heepsy** ($50-$300/mo) |

---

## Recommendation

Build the two proxy sections (Steps 1-5 above) with **honest labels and methodology notes**. They'll be directionally useful for:
- Spotting which competitors lean heavily on paid amplification
- Comparing "active audience footprint" relative to follower size (a more honest engagement signal than vanity follower count)
- Identifying loyal core fans of each competitor (potential outreach targets)

For accounts where the answer matters financially (your own brand decisions), recommend a HypeAuditor subscription for the 2-3 most strategically important competitors — that gets you the real numbers without us building infrastructure we can't fully validate.

---

## Files that will change

- `build_dashboard.py` — Python: add `commenters` field extraction + boosted-flag computation. JS: two new dashboard sections + compare-view rows.
- `memory/competitor-intel-project.md` — document the new metrics with explicit limitations.
- New section "Methodology" added to dashboard sidebar/footer so the heuristic caveats are always visible.

No new Apify runs needed — works off existing CSV data.
