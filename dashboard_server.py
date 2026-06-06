"""Local dashboard server with built-in Apify scrape endpoint.

Run:
    set APIFY_TOKEN=<your-token>       (Windows cmd)
    $env:APIFY_TOKEN="<your-token>"    (PowerShell)
    python dashboard_server.py

Then open http://localhost:8765 in your browser. The "+ Add account"
button on the dashboard will POST to /api/scrape, which runs both
Instagram actors + profile scraper for the given handle, writes CSVs
under <Segment>/<handle>/, downloads avatar, and rebuilds the dashboard.

Endpoints:
    GET  /                        serves dashboard.html
    GET  /<path>                  serves any project file
    POST /api/scrape              {handle, segment, posts?, reels?, profile?}
    GET  /api/jobs                lists active and recent jobs
    GET  /api/jobs/<job_id>       single job status
"""
import csv
import json
import os
import re
import shutil
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

PORT = int(os.environ.get("DASHBOARD_PORT", "8765"))
BASE = os.path.dirname(os.path.abspath(__file__))
APIFY_API = "https://api.apify.com/v2"
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()

POST_ACTOR    = "apify~instagram-post-scraper"
REEL_ACTOR    = "apify~instagram-reel-scraper"
PROFILE_ACTOR = "apify~instagram-profile-scraper"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

JOBS = {}        # job_id -> {handle, segment, status, message, log, started}
JOBS_LOCK = threading.Lock()

# ------------------------------- helpers -------------------------------

def apify(path, method="GET", body=None, timeout=120):
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN environment variable is not set")
    url = f"{APIFY_API}{path}{('&' if '?' in path else '?')}token={APIFY_TOKEN}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def flatten(obj, prefix="", out=None):
    if out is None: out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{prefix}/{k}" if prefix else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}/{i}", out)
    else:
        out[prefix] = obj
    return out

def write_csv(items, out_path):
    if not items:
        return 0
    rows = [flatten(it) for it in items]
    fields = sorted({k for r in rows for k in r.keys()})
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)

def log(job_id, msg):
    print(f"[{job_id[:6]}] {msg}", flush=True)
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j:
            j["log"].append(f"{datetime.now().strftime('%H:%M:%S')} — {msg}")
            j["message"] = msg

def set_job(job_id, **kwargs):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j: j.update(kwargs)

def wait_for_run(run_id, job_id, label):
    start = time.time()
    while time.time() - start < 600:
        r = apify(f"/actor-runs/{run_id}")
        st = r.get("data", {}).get("status")
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            log(job_id, f"{label} → {st}")
            return r["data"]
        time.sleep(4)
    raise RuntimeError(f"{label} run timed out")

def fetch_dataset_items(dataset_id, limit=500):
    out = []
    offset = 0
    while True:
        page = apify(f"/datasets/{dataset_id}/items?clean=true&offset={offset}&limit=100")
        if isinstance(page, list):
            items = page
        else:
            items = page.get("items", page) if isinstance(page, dict) else []
        if not items:
            break
        out.extend(items)
        if len(items) < 100 or len(out) >= limit:
            break
        offset += 100
    return out[:limit]

def download_avatar(url, out_path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=20) as resp:
            data = resp.read()
        with open(out_path, "wb") as fh:
            fh.write(data)
        return True
    except Exception as e:
        print(f"avatar download failed: {e}")
        return False

# ---------------------- main scrape orchestration ----------------------

def run_scrape_job(job_id, handle, segment, do_posts, do_reels, do_profile):
    try:
        set_job(job_id, status="running")
        handle = handle.strip().lstrip("@").lower()
        if not re.match(r"^[a-z0-9_.]{1,30}$", handle):
            raise ValueError(f"Invalid handle: {handle}")
        if segment not in ("Founder", "Enterprise"):
            raise ValueError(f"Invalid segment: {segment}")
        folder = os.path.join(BASE, segment, handle)
        os.makedirs(folder, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")

        runs = []
        if do_posts:
            log(job_id, "Starting Apify post scraper…")
            r = apify(f"/acts/{POST_ACTOR}/runs", "POST",
                      {"username": [handle], "resultsLimit": 50})
            runs.append(("posts", r["data"]["id"]))
        if do_reels:
            log(job_id, "Starting Apify reel scraper…")
            r = apify(f"/acts/{REEL_ACTOR}/runs", "POST",
                      {"username": [handle], "resultsLimit": 50})
            runs.append(("reels", r["data"]["id"]))
        if do_profile:
            log(job_id, "Starting Apify profile scraper…")
            r = apify(f"/acts/{PROFILE_ACTOR}/runs", "POST",
                      {"usernames": [handle]})
            runs.append(("profile", r["data"]["id"]))

        results = {}
        for kind, run_id in runs:
            data = wait_for_run(run_id, job_id, kind)
            if data.get("status") != "SUCCEEDED":
                raise RuntimeError(f"{kind} run failed: {data.get('status')}")
            ds = data.get("defaultDatasetId")
            items = fetch_dataset_items(ds)
            log(job_id, f"{kind}: fetched {len(items)} item(s)")
            results[kind] = items

        # write CSVs
        if "posts" in results:
            p = os.path.join(folder, f"apify_posts_{handle}_{today}.csv")
            n = write_csv(results["posts"], p)
            log(job_id, f"wrote {n} rows → {os.path.relpath(p, BASE)}")
        if "reels" in results:
            p = os.path.join(folder, f"apify_reels_{handle}_{today}.csv")
            n = write_csv(results["reels"], p)
            log(job_id, f"wrote {n} rows → {os.path.relpath(p, BASE)}")

        # profile.json + avatar
        if "profile" in results and results["profile"]:
            p = results["profile"][0]
            meta = {
                "handle": handle,
                "segment": segment,
                "fullName": p.get("fullName") or handle,
                "biography": p.get("biography") or "",
                "followers": p.get("followersCount") or 0,
                "following": p.get("followsCount") or 0,
                "postsCount": p.get("postsCount") or 0,
                "verified": bool(p.get("verified")),
                "category": p.get("businessCategoryName") or "",
                "externalUrl": p.get("externalUrl") or "",
                "profilePicUrl": p.get("profilePicUrlHD") or p.get("profilePicUrl") or "",
            }
            with open(os.path.join(folder, "profile.json"), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=2, ensure_ascii=False)
            log(job_id, "saved profile.json")
            if meta["profilePicUrl"]:
                ok = download_avatar(meta["profilePicUrl"], os.path.join(folder, "avatar.jpg"))
                log(job_id, "avatar downloaded" if ok else "avatar download failed (will fall back to remote URL)")

        # rebuild dashboard
        log(job_id, "Rebuilding dashboard…")
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(BASE, "build_dashboard.py")],
                           cwd=BASE, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"build_dashboard.py failed: {r.stderr[:400]}")
        log(job_id, "✓ dashboard rebuilt — refresh browser")
        set_job(job_id, status="done")
    except Exception as e:
        log(job_id, f"ERROR: {e}")
        set_job(job_id, status="failed")

# ------------------------------- HTTP server -------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass  # silence

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = list(JOBS.values())
            jobs.sort(key=lambda j: j["started"], reverse=True)
            return self._send(200, {"jobs": jobs[:30], "tokenSet": bool(APIFY_TOKEN)})
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
            if not j: return self._send(404, {"error": "not found"})
            return self._send(200, j)

        # static file
        if path == "/" or path == "":
            path = "/dashboard.html"
        local = os.path.normpath(os.path.join(BASE, path.lstrip("/")))
        if not local.startswith(BASE) or not os.path.isfile(local):
            return self._send(404, "not found", "text/plain")
        ext = local.lower().rsplit(".", 1)[-1]
        ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript",
                 "css": "text/css", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "png": "image/png", "webp": "image/webp", "gif": "image/gif",
                 "svg": "image/svg+xml",
                 "json": "application/json",
                 "csv": "text/csv", "md": "text/plain; charset=utf-8"}.get(ext, "application/octet-stream")
        with open(local, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            return self._send(400, {"error": "bad json"})

        if url.path == "/api/scrape":
            if not APIFY_TOKEN:
                return self._send(400, {"error": "APIFY_TOKEN env var not set. Set it before starting the server."})
            handle = payload.get("handle", "").strip().lstrip("@")
            segment = payload.get("segment", "")
            do_posts = bool(payload.get("posts", True))
            do_reels = bool(payload.get("reels", True))
            do_profile = bool(payload.get("profile", True))
            if not handle or segment not in ("Founder", "Enterprise"):
                return self._send(400, {"error": "handle and segment (Founder|Enterprise) required"})
            job_id = uuid.uuid4().hex
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "id": job_id, "handle": handle, "segment": segment,
                    "status": "queued", "message": "queued", "log": [],
                    "started": datetime.now().isoformat(timespec="seconds"),
                }
            threading.Thread(target=run_scrape_job,
                             args=(job_id, handle, segment, do_posts, do_reels, do_profile),
                             daemon=True).start()
            return self._send(200, {"jobId": job_id})

        return self._send(404, {"error": "not found"})

def main():
    if not APIFY_TOKEN:
        print("⚠ APIFY_TOKEN env var not set — the scrape button will return an error.")
        print("  Set it before launching:  set APIFY_TOKEN=apify_api_...")
        print()
    print(f"Dashboard server running on http://localhost:{PORT}")
    print(f"Serving from: {BASE}")
    print()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()

if __name__ == "__main__":
    main()
