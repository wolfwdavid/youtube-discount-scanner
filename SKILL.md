---
name: youtube-discount-scanner
description: Scans the YouTube channels the user follows for new uploads and detects discount / promo / coupon codes in video descriptions, so the user can be alerted to deals ahead of watching. Use when the user wants to track creators for sponsor codes, check a specific video or channel for a discount code, or manage the followed-channels list. Triggered automatically by the "YouTube discount code scan" automation.
compatibility: Created for Zo Computer
metadata:
  author: c0dezero.zo.computer
---

# YouTube Discount Code Scanner

Watches YouTube creators the user follows and flags **discount / promo / coupon
codes** in new videos' descriptions — before the user watches.

## Why it's built this way

- **New-upload detection** uses YouTube's public RSS feeds
  (`/feeds/videos.xml?channel_id=…`). No API key, works server-side.
- **Description fetching** does NOT work from a plain script on this server —
  YouTube bot-blocks the datacenter IP (watch pages return a consent/"confirm
  you're not a bot" wall). So the **Zo agent fetches each new video's page with
  `read_webpage`** (which routes through a proxy that isn't blocked), and the
  script parses the saved HTML. This split is intentional.
- **Code detection** is a tuned regex: it catches both literal codes
  (`code WAN`, `promo code SAVE20`, `MKBHD10`) and offer phrasing
  (`20% off`, `free trial`) while ignoring false positives like "code red" or
  "code.org".

## State

`state.json` (next to this file) holds the followed `channels` and the set of
already-`seen` video ids. Edit via the `add` / `remove` commands.

## How the agent runs a scan (the automation flow)

1. `python3 scripts/scan.py check --days 3` → JSON list of NEW videos
   (this marks them seen). Use `--no-mark` while testing.
2. For each new video, the **agent** calls `read_webpage(video_url)`. That
   saves the page HTML into the conversation workspace `read_webpage/` folder.
3. `python3 scripts/scan.py parse-html <saved_html> --title "<title>"` →
   JSON with `has_code`, `codes[]`, `offers[]`.
4. If any video has `has_code` (or notable `has_offer`), message the user with
   the creator, video title, link, the code(s), and the surrounding context.
   If nothing has a code, send nothing (or a quiet "no codes" only if asked).

> Alternative without the agent: `scan.py detect` reads description text from
> stdin and runs the same detection — useful if you already have the text.

## Managing followed channels

```bash
python3 scripts/scan.py add @MKBHD                 # by handle
python3 scripts/scan.py add https://youtube.com/@LinusTechTips
python3 scripts/scan.py add UCXuqSBlHAE6Xw-yeJA0Tunw
python3 scripts/scan.py channels                   # list
python3 scripts/scan.py remove <channel_id>        # unfollow
```

## Commands

- `channels` — list followed channels
- `add <url|@handle|channel_id> [name]` — follow (resolves to canonical id)
- `remove <channel_id>` — unfollow
- `check [--days N] [--no-mark]` — new videos as JSON (marks seen unless `--no-mark`)
- `parse-html <file> [--title T]` — extract description from a saved watch page + detect codes
- `detect [--title T]` — detect codes from description text on stdin
- `seen-add <video_id>` — manually mark a video processed

State lives in `state.json`.
