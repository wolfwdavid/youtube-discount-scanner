# Web Dashboard (Zo Space routes)

The scanner ships with a public web dashboard built as [Zo Space](https://zo.computer) routes.

## Live

- **Dashboard:** `https://c0dezero.zo.space/deals`
- **Codes API:** `GET /api/youtube-codes` — public, returns active codes as JSON
- **Channels API:** `/api/youtube-channels`
  - `GET` — public, lists followed channels
  - `POST` `{ "handle": "@mkbhd" }` — add a channel (requires admin key)
  - `DELETE` `{ "id": "UC..." }` — remove a channel (requires admin key)

## Features

- **Search** — filter codes by code, channel, or video title
- **Sort** — Newest / Channel / Expiring soon
- **Manage channels** — add/remove tracked channels from the UI, gated by an admin key
- **QR code** — scan-to-share modal
- **Expiry badges** — color-coded countdown per code
- **Auto-refresh** from the codes datastore after each daily scan

## Auth

Write operations on `/api/youtube-channels` require a bearer token:

```
Authorization: Bearer <ADMIN_KEY>
```

The admin key is generated locally and stored as `.admin_key` (gitignored). It is entered once in the
Manage Channels panel and cached in the browser's localStorage on the user's device. It is never
committed to this repo.
