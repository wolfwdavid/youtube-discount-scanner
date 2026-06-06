# YouTube Discount Scanner

Scans the YouTube channels you follow for new uploads and detects discount / promo / coupon codes in their video descriptions — so you get alerted to deals before you even watch.

Built as a [Zo Computer](https://zo.computer) Skill + scheduled automation.

## What it does

1. **Checks RSS feeds** of followed channels for new uploads (no API key needed).
2. **Fetches each new video's description** (via a proxy, since YouTube bot-blocks datacenter IPs).
3. **Detects codes** — promo/coupon/discount codes, offer phrases, and expiry dates.
4. **Alerts you** with the channel, title, link, code, and when it expires.
5. **Publishes a live web dashboard** of currently-active codes.

## Commands

```bash
python3 scripts/scan.py channels              # list followed channels
python3 scripts/scan.py add @LinusTechTips    # follow a channel
python3 scripts/scan.py remove <channel_id>   # unfollow
python3 scripts/scan.py check [--days N]      # find new videos (JSON)
python3 scripts/scan.py parse-html <file>     # extract + detect codes from a saved watch page
python3 scripts/scan.py detect --title T      # detect codes from stdin description text
python3 scripts/scan.py record                # append a found code to codes.json
python3 scripts/scan.py list-codes            # show stored codes
python3 scripts/scan.py expiring [--days N]   # codes expiring within N days
```

## Files

- `scripts/scan.py` — the scanner CLI (zero dependencies, stdlib only)
- `SKILL.md` — Zo Skill manifest + usage
- `state.json` — followed channels + seen video IDs (gitignored; see `state.example.json`)
- `codes.json` — detected codes datastore powering the dashboard (gitignored)

## Code detection

Catches explicit codes (`code LTT`, `promo code SAVE20`), offer phrases (`20% off`, `free trial`), and parses expiry dates in many formats (`expires June 30`, `valid until 7/1/2026`, `valid for 30 days`, `end of the month`).

## License

MIT
