#!/usr/bin/env python3
"""YouTube discount-code scanner.

Tracks a list of "followed" YouTube channels, checks their RSS feeds for new
uploads, and detects discount / promo codes in video descriptions.

Description fetching is intentionally NOT done here: YouTube bot-blocks this
server's IP for watch-page scraping. The Zo automation fetches descriptions
through Zo's proxy (read_webpage) and pipes the text to `detect`.

Commands:
  channels                 List followed channels
  add <url|@handle|id> [name]
                           Follow a channel (resolves handle -> channel_id)
  remove <channel_id>      Unfollow a channel
  check [--days N] [--no-mark]
                           Fetch RSS for all channels, print NEW videos as JSON.
                           Marks them seen unless --no-mark. --days limits how
                           far back a first-run is allowed to look (default 3).
  detect [--title T]       Read description text from stdin, print detected
                           discount codes / offers as JSON.
  seen-add <video_id>      Manually mark a video as already processed.

State lives in ../state.json (channels + seen video ids).
"""
import sys, os, re, json, time, html, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE, "state.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# ---------------- state ----------------
def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"channels": [], "seen": []}


def save_state(s):
    # cap seen list so it doesn't grow forever
    s["seen"] = s.get("seen", [])[-2000:]
    with open(STATE_PATH, "w") as f:
        json.dump(s, f, indent=2)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


# ---------------- channel resolution ----------------
def resolve_channel(token):
    """Return (channel_id, name) from a channel URL, @handle, UC… id, or bare handle."""
    token = token.strip()
    # already a channel id
    m = re.search(r"(UC[0-9A-Za-z_-]{22})", token)
    if m:
        cid = m.group(1)
        return cid, channel_name(cid)
    # build a URL to fetch
    if token.startswith("http"):
        url = token
    elif token.startswith("@"):
        url = f"https://www.youtube.com/{token}"
    else:
        url = f"https://www.youtube.com/@{token}"
    page = http_get(url)
    m = (re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"', page)
         or re.search(r'"externalId":"(UC[0-9A-Za-z_-]{22})"', page)
         or re.search(r'<meta property="og:url" content="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"', page)
         or re.search(r'"channelId":"(UC[0-9A-Za-z_-]{22})"', page)
         or re.search(r'channel/(UC[0-9A-Za-z_-]{22})', page))
    if not m:
        raise SystemExit(f"Could not resolve channel id from: {token}")
    cid = m.group(1)
    nm = None
    mn = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    if mn:
        nm = html.unescape(mn.group(1))
    return cid, nm or channel_name(cid)


def channel_name(cid):
    try:
        feed = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
        m = re.search(r"<title>([^<]+)</title>", feed)
        if m:
            return html.unescape(m.group(1))
    except Exception:
        pass
    return cid


# ---------------- RSS ----------------
def parse_feed(cid):
    """Return list of {video_id, title, published, channel} newest-first."""
    feed = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    chan = re.search(r"<title>([^<]+)</title>", feed)
    chan = html.unescape(chan.group(1)) if chan else cid
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", feed, re.DOTALL):
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry)
        title = re.search(r"<title>([^<]+)</title>", entry)
        pub = re.search(r"<published>([^<]+)</published>", entry)
        if vid:
            out.append({
                "video_id": vid.group(1),
                "title": html.unescape(title.group(1)) if title else "",
                "published": pub.group(1) if pub else "",
                "channel": chan,
                "url": f"https://www.youtube.com/watch?v={vid.group(1)}",
            })
    return out


# ---------------- code detection ----------------
# Sponsor/affiliate phrasing that signals a deal even without a literal code.
OFFER_PAT = re.compile(
    r"(?:\b\d{1,2}\s?%\s?(?:off|discount)\b"
    r"|\$\d{1,4}\s?(?:off|discount)\b"
    r"|\bfree (?:trial|month|shipping)\b"
    r"|\buse (?:code|coupon|promo)\b"
    r"|\b(?:coupon|promo)\s?code\b"
    r"|\bdiscount code\b)", re.IGNORECASE)

# "code XALPHA", "promo code: XALPHA", "use code SAVE20 at"
CODE_PAT = re.compile(
    r"(?i:(?:use\s+)?(?:the\s+)?(?:promo\s*|coupon\s*|discount\s*|offer\s*|referral\s*)?code)"
    r"[:\s\"'’]*([A-Z][A-Z0-9._-]{2,24})\b")

# A token that is itself codey: SAVE20, MKBHD10, GET50OFF (must contain a digit)
TOKEN_PAT = re.compile(r"\b([A-Z][A-Z0-9]{2,}\d[A-Z0-9]*|\b[A-Z0-9]{3,}\d{1,3})\b")

STOP = {"HTTP", "HTTPS", "HTML", "JSON", "YOUTUBE", "VISIONOS",
        "FACETIMES", "PERSONAS", "2024", "2025", "2026", "USB", "HDMI",
        "GPU", "CPU", "OLED", "LCD", "RTX", "AMD", "NBA", "RPG", "ECC",
        "CES", "USA", "THE", "FOR", "AND", "NOW", "OFF", "GET"}


def detect_codes(text, title=""):
    text = text or ""
    found = {}
    expires_iso, expires_text = detect_expiry(text)
    for m in CODE_PAT.finditer(text):
        tok = m.group(1)
        # token must look like a code: uppercase, optional trailing digits
        if tok in STOP:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9._-]{2,24}", tok):
            continue
        s = max(0, m.start() - 50)
        e = min(len(text), m.end() + 60)
        # look for an expiry phrase near this specific code first
        local_iso, local_txt = detect_expiry(text[max(0, m.start()-120):min(len(text), m.end()+160)])
        found[tok] = {"code": tok, "confidence": "high",
                      "context": " ".join(text[s:e].split()),
                      "expires": local_iso or expires_iso,
                      "expires_text": local_txt or expires_text}
    # offer phrases without an explicit "code X" capture
    offers = []
    for m in OFFER_PAT.finditer(text):
        s = max(0, m.start() - 40)
        e = min(len(text), m.end() + 60)
        offers.append(" ".join(text[s:e].split()))
    return {
        "has_code": bool(found),
        "has_offer": bool(found) or bool(offers),
        "codes": list(found.values()),
        "offers": offers[:5],
        "expires": expires_iso,
        "expires_text": expires_text,
        "title": title,
    }


# ---------------- expiry detection ----------------
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
     "sep", "oct", "nov", "dec"], start=1)}

# "expires June 30", "valid until July 1st, 2026", "offer ends 6/30/2026",
# "ends June 30th", "valid through Aug 1"
_EXP_TRIGGER = r"(?:expir\w*|valid\s+(?:until|through|thru)|offer\s+ends?|ends?|good\s+(?:until|through)|deadline)"
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?"
_NUM_RE = r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?"
_REL_RE = r"(?:valid\s+for|exp.{0,12}?in|for\s+the\s+next)\s+(\d{1,3})\s+(day|week|month)s?"

EXP_MONTH = re.compile(_EXP_TRIGGER + r"[^.\n]{0,25}?" + _MONTH_RE, re.IGNORECASE)
EXP_NUM = re.compile(_EXP_TRIGGER + r"[^.\n]{0,20}?" + _NUM_RE, re.IGNORECASE)
EXP_REL = re.compile(_REL_RE, re.IGNORECASE)
EXP_EOM = re.compile(r"(?:through|until|til|by)\s+the\s+end\s+of\s+(?:this\s+|the\s+)?month", re.IGNORECASE)


def _iso(y, mo, d):
    try:
        return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc).date().isoformat()
    except Exception:
        return None


def detect_expiry(text):
    """Return (iso_date_or_None, raw_phrase_or_None) for a discount expiry."""
    text = text or ""
    now = datetime.now(timezone.utc)

    m = EXP_MONTH.search(text)
    if m:
        mon = MONTHS.get(m.group(1).lower()[:3])
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if mon:
            iso = _iso(year, mon, day)
            # if no year given and the date already passed, assume next year
            if iso and not m.group(3) and iso < now.date().isoformat():
                iso = _iso(year + 1, mon, day)
            if iso:
                return iso, " ".join(m.group(0).split())

    m = EXP_NUM.search(text)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(c) if c else now.year
        if year < 100:
            year += 2000
        iso = _iso(year, a, b)  # US M/D
        if iso:
            if not c and iso < now.date().isoformat():
                iso = _iso(year + 1, a, b)
            return iso, " ".join(m.group(0).split())

    m = EXP_REL.search(text)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        from datetime import timedelta
        return (now + timedelta(days=days)).date().isoformat(), " ".join(m.group(0).split())

    m = EXP_EOM.search(text)
    if m:
        # last day of current month
        if now.month == 12:
            nxt = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            nxt = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        from datetime import timedelta
        return (nxt - timedelta(days=1)).date().isoformat(), " ".join(m.group(0).split())

    return None, None


# ---------------- commands ----------------
def cmd_channels(args):
    s = load_state()
    if not s["channels"]:
        print("No channels followed yet. Add one: scan.py add <url|@handle|id> [name]")
        return
    for c in s["channels"]:
        print(f"{c['id']}  {c.get('name','')}")


def cmd_add(args):
    if not args:
        raise SystemExit("usage: add <url|@handle|channel_id> [name]")
    token = args[0]
    cid, name = resolve_channel(token)
    if len(args) > 1:
        name = " ".join(args[1:])
    s = load_state()
    if any(c["id"] == cid for c in s["channels"]):
        print(f"Already following {name} ({cid})")
        return
    s["channels"].append({"id": cid, "name": name})
    save_state(s)
    print(f"Now following {name} ({cid})")


def cmd_remove(args):
    if not args:
        raise SystemExit("usage: remove <channel_id>")
    cid = args[0]
    s = load_state()
    before = len(s["channels"])
    s["channels"] = [c for c in s["channels"] if c["id"] != cid and c.get("name") != cid]
    save_state(s)
    print("Removed." if len(s["channels"]) < before else "Nothing matched.")


def cmd_check(args):
    days = 3
    mark = True
    if "--no-mark" in args:
        mark = False
        args = [a for a in args if a != "--no-mark"]
    if "--days" in args:
        i = args.index("--days")
        days = int(args[i + 1])
    s = load_state()
    seen = set(s.get("seen", []))
    first_run = len(seen) == 0
    cutoff = time.time() - days * 86400
    new = []
    for c in s["channels"]:
        try:
            entries = parse_feed(c["id"])
        except Exception as e:
            sys.stderr.write(f"feed error {c.get('name', c['id'])}: {e}\n")
            continue
        for e in entries:
            if e["video_id"] in seen:
                continue
            # on the very first run, only consider recent videos
            if first_run and e["published"]:
                try:
                    pub = datetime.fromisoformat(e["published"].replace("Z", "+00:00")).timestamp()
                    if pub < cutoff:
                        seen.add(e["video_id"])
                        continue
                except Exception:
                    pass
            new.append(e)
            seen.add(e["video_id"])
    if mark:
        s["seen"] = list(seen)
        save_state(s)
    print(json.dumps({"new_videos": new, "count": len(new),
                      "checked_channels": len(s["channels"])}, indent=2))


def cmd_detect(args):
    title = ""
    if "--title" in args:
        i = args.index("--title")
        title = args[i + 1]
    text = sys.stdin.read()
    print(json.dumps(detect_codes(text, title), indent=2))


def extract_description(html_text):
    """Pull the full video description out of a watch-page HTML blob."""
    m = re.search(r'"shortDescription":"(.*?)","isCrawlable"', html_text, re.DOTALL)
    if m:
        try:
            return json.loads('"' + m.group(1) + '"')
        except Exception:
            return m.group(1)
    m = re.search(r'"attributedDescription":\{"content":"(.*?)"', html_text, re.DOTALL)
    if m:
        try:
            return json.loads('"' + m.group(1) + '"')
        except Exception:
            return m.group(1)
    return ""


def cmd_parse_html(args):
    title = ""
    if "--title" in args:
        i = args.index("--title")
        title = args[i + 1]
        args = [a for j, a in enumerate(args) if j not in (i, i + 1)]
    if not args:
        raise SystemExit("usage: parse-html <watch_page.html> [--title T]")
    with open(args[0], encoding="utf-8", errors="ignore") as f:
        html_text = f.read()
    desc = extract_description(html_text)
    res = detect_codes(desc, title)
    res["description_len"] = len(desc)
    print(json.dumps(res, indent=2))


def cmd_seen_add(args):
    if not args:
        raise SystemExit("usage: seen-add <video_id>")
    s = load_state()
    seen = set(s.get("seen", []))
    seen.add(args[0])
    s["seen"] = list(seen)
    save_state(s)
    print("ok")


# ---------------- codes datastore ----------------
CODES_PATH = os.path.join(BASE, "codes.json")


def load_codes():
    if os.path.exists(CODES_PATH):
        with open(CODES_PATH) as f:
            return json.load(f)
    return {"codes": []}


def save_codes(d):
    with open(CODES_PATH, "w") as f:
        json.dump(d, f, indent=2)


def _arg(args, name, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1]
    return default


def cmd_record(args):
    """Record one or more found codes into codes.json.

    Either pipe a detect/parse-html JSON object on stdin (plus --video-id,
    --channel, --title, --url to attach metadata), or pass a single code via
    flags: record --code LTT --channel "LTT" --video-id X --title T --url U
    [--expires YYYY-MM-DD] [--context "..."].
    """
    video_id = _arg(args, "--video-id", "")
    channel = _arg(args, "--channel", "")
    title = _arg(args, "--title", "")
    url = _arg(args, "--url", "")
    store = load_codes()
    existing = {(c.get("code"), c.get("video_id")): c for c in store["codes"]}

    incoming = []
    single = _arg(args, "--code")
    if single:
        incoming.append({
            "code": single,
            "expires": _arg(args, "--expires"),
            "expires_text": _arg(args, "--expires-text"),
            "context": _arg(args, "--context", ""),
        })
    else:
        raw = sys.stdin.read().strip()
        if raw:
            data = json.loads(raw)
            incoming = data.get("codes", [])

    added = 0
    now = datetime.now(timezone.utc).isoformat()
    for c in incoming:
        key = (c.get("code"), video_id)
        rec = existing.get(key, {})
        rec.update({
            "code": c.get("code"),
            "channel": channel or rec.get("channel", ""),
            "video_id": video_id or rec.get("video_id", ""),
            "title": title or rec.get("title", ""),
            "url": url or rec.get("url", ""),
            "context": c.get("context", rec.get("context", "")),
            "expires": c.get("expires", rec.get("expires")),
            "expires_text": c.get("expires_text", rec.get("expires_text")),
            "found_at": rec.get("found_at", now),
            "reminded": rec.get("reminded", False),
        })
        if key not in existing:
            store["codes"].append(rec)
            added += 1
        existing[key] = rec
    save_codes(store)
    print(json.dumps({"recorded": added, "total": len(store["codes"])}))


def cmd_list_codes(args):
    print(json.dumps(load_codes(), indent=2))


def cmd_expiring(args):
    """Print codes expiring within N days (default 7) not yet reminded."""
    days = int(_arg(args, "--days", "7"))
    mark = "--mark" in args
    store = load_codes()
    today = datetime.now(timezone.utc).date()
    out = []
    for c in store["codes"]:
        exp = c.get("expires")
        if not exp or c.get("reminded"):
            continue
        try:
            ed = datetime.fromisoformat(exp).date()
        except Exception:
            continue
        delta = (ed - today).days
        if 0 <= delta <= days:
            c2 = dict(c)
            c2["days_left"] = delta
            out.append(c2)
    out.sort(key=lambda x: x["days_left"])
    if mark:
        keys = {(c["code"], c["video_id"]) for c in out}
        for c in store["codes"]:
            if (c.get("code"), c.get("video_id")) in keys:
                c["reminded"] = True
        save_codes(store)
    print(json.dumps({"expiring": out, "count": len(out)}, indent=2))


CMDS = {
    "channels": cmd_channels, "add": cmd_add, "remove": cmd_remove,
    "check": cmd_check, "detect": cmd_detect, "parse-html": cmd_parse_html,
    "seen-add": cmd_seen_add, "record": cmd_record,
    "list-codes": cmd_list_codes, "expiring": cmd_expiring,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd not in CMDS:
        raise SystemExit(f"unknown command: {cmd}\n{__doc__}")
    CMDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
