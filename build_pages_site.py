"""Build a slim `_site/` folder for Cloudflare Pages deployment.

Only the files actually served by the dashboard are copied. The 40+ MB of
scraped CSVs, Python source, profile.json files, and analyst markdown stay
in the repo but never reach the public site.

Run automatically by Cloudflare Pages via the build command in pages config.
Locally: `python build_pages_site.py` then open `_site/index.html`.

Output structure (~5 MB):
  _site/
    .nojekyll
    index.html              # redirect splash
    dashboard.html          # built dashboard (regenerable via build_dashboard.py)
    Founder/<handle>/avatar.{jpg,png,webp,svg}
    Enterprise/<handle>/avatar.{jpg,png,webp,svg}
"""
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "_site")

# Files that MUST exist for the dashboard to render
REQUIRED_ROOT_FILES = ["index.html", "dashboard.html", ".nojekyll"]

# Per-account folder structure under Founder/<handle>/ and Enterprise/<handle>/
SEGMENT_DIRS = ["Founder", "Enterprise"]

# Avatar file extensions we'll copy (matches whatever the dashboard uses)
AVATAR_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif")


def main() -> int:
    # Clean previous build
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE, exist_ok=True)

    missing = []
    for fname in REQUIRED_ROOT_FILES:
        src = os.path.join(BASE, fname)
        if not os.path.exists(src):
            missing.append(fname)
            continue
        shutil.copy2(src, os.path.join(SITE, fname))

    if missing:
        print(f"[ERROR] Required files missing: {missing}")
        print("  Run `python build_dashboard.py` first to generate dashboard.html.")
        return 1

    # Copy avatars from every tracked account
    avatar_count = 0
    for seg in SEGMENT_DIRS:
        seg_dir = os.path.join(BASE, seg)
        if not os.path.isdir(seg_dir):
            continue
        for handle in sorted(os.listdir(seg_dir)):
            account_dir = os.path.join(seg_dir, handle)
            if not os.path.isdir(account_dir):
                continue
            dst_dir = os.path.join(SITE, seg, handle)
            for ext in AVATAR_EXTS:
                for fname in os.listdir(account_dir):
                    if fname.lower() == f"avatar{ext}":
                        os.makedirs(dst_dir, exist_ok=True)
                        shutil.copy2(
                            os.path.join(account_dir, fname),
                            os.path.join(dst_dir, fname),
                        )
                        avatar_count += 1

    # Compute the size of what we'll ship
    total_bytes = 0
    file_count = 0
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            total_bytes += os.path.getsize(os.path.join(root, f))
            file_count += 1

    print(f"[OK] Built {SITE}")
    print(f"     {file_count} files · {total_bytes / 1024 / 1024:.2f} MB · {avatar_count} avatars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
