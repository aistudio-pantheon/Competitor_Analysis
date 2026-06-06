import os
import csv
import json
import urllib.request
import urllib.parse
from datetime import datetime

# ---------------------------------------------------------
# SETUP INSTRUCTIONS:
# 1. Set environment variables before running:
#    set META_ACCESS_TOKEN=your_long_lived_token
#    set YOUR_IG_ACCOUNT_ID=your_instagram_business_account_id
#
# 2. Run the script:
#    python meta_graph_scraper.py <handle> <Founder|Enterprise>
# ---------------------------------------------------------

META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
YOUR_IG_ACCOUNT_ID = os.environ.get("YOUR_IG_ACCOUNT_ID", "").strip()
API_VERSION = "v19.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def fetch_competitor_data(target_handle):
    if not META_ACCESS_TOKEN or not YOUR_IG_ACCOUNT_ID:
        raise ValueError("META_ACCESS_TOKEN and YOUR_IG_ACCOUNT_ID must be set as environment variables.")

    # We ask for profile info and up to 100 recent media items
    fields = (
        f"business_discovery.username({target_handle}){{"
        f"followers_count,media_count,biography,name,profile_picture_url,"
        f"media.limit(100){{id,caption,comments_count,like_count,media_type,media_url,permalink,timestamp}}"
        f"}}"
    )
    
    url = f"https://graph.facebook.com/{API_VERSION}/{YOUR_IG_ACCOUNT_ID}?fields={urllib.parse.quote(fields)}&access_token={META_ACCESS_TOKEN}"
    
    print(f"Fetching data for @{target_handle} via Meta Graph API...")
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("business_discovery", {})
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode('utf-8')
        print(f"API Error: {error_msg}")
        raise

def save_profile_json(data, target_handle, segment_dir):
    profile_path = os.path.join(segment_dir, "profile.json")
    meta = {
        "handle": target_handle,
        "fullName": data.get("name") or target_handle,
        "biography": data.get("biography") or "",
        "followers": data.get("followers_count") or 0,
        "postsCount": data.get("media_count") or 0,
        "profilePicUrl": data.get("profile_picture_url") or "",
        "verified": False, # Graph API doesn't expose verified status easily here
        "category": "",
    }
    with open(profile_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print("Saved profile.json")

def save_posts_csv(media_data, target_handle, segment_dir):
    if not media_data:
        print("No media found.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    csv_path = os.path.join(segment_dir, f"meta_graph_{target_handle}_{today}.csv")
    
    rows = []
    for item in media_data:
        # Standardize Graph API output to match Apify's CSV structure 
        # so build_dashboard.py can read it seamlessly.
        
        # Meta returns 'IMAGE', 'VIDEO', 'CAROUSEL_ALBUM'
        m_type = item.get("media_type", "")
        mapped_type = "Image"
        if m_type == "VIDEO": mapped_type = "Video"
        elif m_type == "CAROUSEL_ALBUM": mapped_type = "Sidecar"

        rows.append({
            "shortCode": item.get("permalink", "").strip("/").split("/")[-1] if item.get("permalink") else item.get("id"),
            "url": item.get("permalink", ""),
            "ownerUsername": target_handle,
            "timestamp": item.get("timestamp", ""),
            "type": mapped_type,
            "likesCount": item.get("like_count", 0),
            "commentsCount": item.get("comments_count", 0),
            "videoViewCount": 0, # Meta Graph API rarely provides view counts for competitors
            "caption": item.get("caption", ""),
            "displayUrl": item.get("media_url", "")
        })

    fields = ["shortCode", "url", "ownerUsername", "timestamp", "type", "likesCount", "commentsCount", "videoViewCount", "caption", "displayUrl"]
    
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} posts to {csv_path}")

def main():
    import sys
    if len(sys.argv) < 3:
        print("Usage: python meta_graph_scraper.py <handle> <Founder|Enterprise>")
        sys.exit(1)

    handle = sys.argv[1].replace("@", "").strip()
    segment = sys.argv[2].capitalize()

    if segment not in ["Founder", "Enterprise"]:
        print("Segment must be 'Founder' or 'Enterprise'.")
        sys.exit(1)

    target_dir = os.path.join(BASE_DIR, segment, handle)
    os.makedirs(target_dir, exist_ok=True)

    try:
        data = fetch_competitor_data(handle)
        save_profile_json(data, handle, target_dir)
        
        media_items = data.get("media", {}).get("data", [])
        save_posts_csv(media_items, handle, target_dir)
        
        print("\nSuccess! Run 'python build_dashboard.py' to update the dashboard.")
    except Exception as e:
        print(f"Failed to scrape: {e}")

if __name__ == "__main__":
    main()
