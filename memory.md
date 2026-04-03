# TridenB Autoforwarder V2 — Memory

## What This Project Does
Local CLI tool that forwards Telegram messages from source channels to destination channels using a personal user account (MTProto via Telethon). No bot token. V2 adds SQLite message tracking, edit/delete sync, AI rewrite, reply threading, and image auto-cleanup.

## Credentials
- Stored in `.env` (never committed)
- API_ID=29363636, API_HASH=dd4f18f6956a38dc18087c7495181258
- Phone: +918544130087

## Session
- Telethon saves session to `tridenb_autoforwarder.session` after first auth
- Subsequent runs skip OTP

## Task Storage
- `tasks.json` — runtime file, excluded from git
- Schema: list of task objects with source/dest channel IDs, enabled flag, filters

## Database
- `autoforwarder.db` — SQLite database (via `database.py`)
- Tracks every forwarded message: source/dest IDs, task ID, timestamps, reply threading, image flag
- Enables edit sync, delete sync, reply threading, statistics, and image auto-cleanup

## Filter Behavior
- `blacklist_words`: drop entire message if any word matches (case-insensitive)
- `clean_words`: remove specific strings from text
- `clean_urls`: strip `https?://\S+` patterns
- `clean_usernames`: strip `@word` patterns
- `skip_images/audio/videos`: drop media messages entirely
- `image_delete_days`: auto-delete forwarded images older than N days
- `rewrite_enabled`: AI rewrite via OpenRouter before forwarding
- No text mod -> `forward_messages()` (preserves media + formatting)
- Text modified -> `send_message()` (text only)

## AI Rewrite
- `openrouter_client.py` — sends text to OpenRouter API for AI rewriting
- Triggered per-task when `rewrite_enabled` filter is set
- API key configured in `.env`

## Current Status (2026-04-04)
V2 fully implemented. All 14 menu options working. SQLite DB tracks all forwarded messages. Edit/delete sync, reply threading, loop protection, image cleanup, AI rewrite, duplicate task, statistics, and finance report all functional.

## Menu Options
1.  Get Channel ID — lists all channels/groups
2.  Create Forwarding Task — source + multiple destinations + filters
3.  List Tasks — shows enabled/paused status
4.  Toggle Task — enable/disable (persisted to tasks.json)
5.  Edit Task — modify source, destinations, and filters
6.  Delete Task
7.  Start Forwarder — background, non-blocking, returns to menu
8.  Stop Forwarder — removes event handlers cleanly
9.  Pause / Resume Task — session-only pause, resets loop counter on resume
10. View Logs — last 50 timestamped entries
11. Duplicate Task — clone an existing task with new ID
12. View Statistics — per-task message counts, image counts, last active time
13. View Message Threads — shows reply chains tracked in DB
14. Generate AI Finance Report
0.  Exit — prompts to stop forwarder if running

## Key Files
- `main.py` — all CLI logic, menu, forwarder handlers
- `database.py` — SQLite handler, message logging/querying
- `openrouter_client.py` — AI rewrite client
- `tasks.json` — auto-created, runtime task persistence
- `.env` — credentials
- `tasks/progress.md` — feature verification checklist
