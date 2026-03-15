import asyncio
import json
import os
import re
import sys
import time
import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

TASKS_FILE = "tasks.json"
MESSAGE_MAP_FILE = "message_map.json"
SESSION_NAME = "tridenb_autoforwarder"
MAX_LOG = 500
LOOP_LIMIT = 10    # max forwards per task within LOOP_WINDOW seconds
LOOP_WINDOW = 10   # seconds

# ---------- Runtime state ----------
forwarder_active = False
paused_task_ids = set()   # task IDs paused this session
loop_counter = {}          # task_id -> [timestamps]
log_entries = []
active_handlers = []       # (func, event_class) for cleanup on stop


# ---------- Sync helpers ----------

def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return {"tasks": []}
    try:
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"tasks": []}


def save_tasks(data):
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_message_map():
    if not os.path.exists(MESSAGE_MAP_FILE):
        return {}
    try:
        with open(MESSAGE_MAP_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_message_map(mmap):
    with open(MESSAGE_MAP_FILE, "w") as f:
        json.dump(mmap, f)


def mmap_key(src_channel_id, src_msg_id):
    return f"{src_channel_id}:{src_msg_id}"


def next_task_id(data):
    tasks = data.get("tasks", [])
    if not tasks:
        return 1
    return max(t["id"] for t in tasks) + 1


def add_log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}"
    log_entries.append(entry)
    if len(log_entries) > MAX_LOG:
        log_entries.pop(0)
    print(entry)


def check_loop(task_id):
    """Returns True if task is firing too fast — loop detected."""
    now = time.time()
    times = loop_counter.get(task_id, [])
    times = [t for t in times if now - t < LOOP_WINDOW]
    times.append(now)
    loop_counter[task_id] = times
    return len(times) >= LOOP_LIMIT


def apply_filters(message, filters):
    if filters.get("skip_images") and message.photo:
        return (False, None)
    if filters.get("skip_audio") and (message.audio or message.voice):
        return (False, None)
    if filters.get("skip_videos") and message.video:
        return (False, None)

    text = message.text or ""

    blacklist = filters.get("blacklist_words", [])
    text_lower = text.lower()
    for word in blacklist:
        if word.lower() in text_lower:
            return (False, None)

    modified = False

    clean_words = filters.get("clean_words", [])
    for w in clean_words:
        if w in text:
            text = text.replace(w, "")
            modified = True

    if filters.get("clean_urls"):
        new_text = re.sub(r"https?://\S+", "", text)
        if new_text != text:
            modified = True
            text = new_text

    if filters.get("clean_usernames"):
        new_text = re.sub(r"@\w+", "", text)
        if new_text != text:
            modified = True
            text = new_text

    if modified:
        return (True, text.strip())
    return (True, None)


# ---------- Async helpers ----------

async def ainput(prompt=""):
    """Non-blocking input — lets asyncio process Telegram events while waiting."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


async def send_copy(client, dest_id, message, modified_text):
    """Send message as a fresh copy — no 'Forwarded from' header."""
    if modified_text is not None:
        return await client.send_message(dest_id, modified_text)
    if message.media:
        return await client.send_file(dest_id, file=message.media, caption=message.text or "")
    return await client.send_message(dest_id, message.text or "")


# ---------- Async CLI functions ----------

async def get_channel_id(client):
    print("\n--- All Channels / Groups ---")
    print(f"{'Name':<40} {'Channel ID':<20}")
    print("-" * 60)
    async for dialog in client.iter_dialogs():
        if dialog.is_channel or dialog.is_group:
            name = dialog.name or "(no name)"
            cid = dialog.entity.id
            if dialog.is_channel:
                full_id = int(f"-100{cid}")
            else:
                full_id = -cid if cid > 0 else cid
            print(f"{name:<40} {full_id:<20}")
    print()


async def create_task(client):
    data = load_tasks()
    print("\n--- Create Forwarding Task ---")
    name = (await ainput("Task name: ")).strip()

    src_raw = (await ainput("Source channel ID (e.g. -1001234567890): ")).strip()
    dst_raw = (await ainput("Destination channel IDs (comma-separated): ")).strip()

    try:
        source_id = int(src_raw)
        dest_ids = [int(x.strip()) for x in dst_raw.split(",") if x.strip()]
    except ValueError:
        print("Invalid channel IDs.")
        return

    if not dest_ids:
        print("At least one destination ID required.")
        return

    print("\nFilters (press Enter to skip / use defaults):")

    async def prompt_list(prompt):
        raw = (await ainput(f"  {prompt} (comma-separated, blank=none): ")).strip()
        return [x.strip() for x in raw.split(",") if x.strip()] if raw else []

    async def prompt_bool(prompt):
        val = (await ainput(f"  {prompt} [y/N]: ")).strip().lower()
        return val in ("y", "yes")

    blacklist = await prompt_list("Blacklist words")
    clean_words = await prompt_list("Clean words (remove from text)")
    clean_urls = await prompt_bool("Remove URLs?")
    clean_usernames = await prompt_bool("Remove @usernames?")
    skip_images = await prompt_bool("Skip image messages?")
    skip_audio = await prompt_bool("Skip audio/voice messages?")
    skip_videos = await prompt_bool("Skip video messages?")

    task = {
        "id": next_task_id(data),
        "name": name,
        "source_channel_id": source_id,
        "destination_channel_ids": dest_ids,
        "enabled": True,
        "filters": {
            "blacklist_words": blacklist,
            "clean_words": clean_words,
            "clean_urls": clean_urls,
            "clean_usernames": clean_usernames,
            "skip_images": skip_images,
            "skip_audio": skip_audio,
            "skip_videos": skip_videos,
        },
    }

    data["tasks"].append(task)
    save_tasks(data)
    print(f"\nTask '{name}' created with ID {task['id']}.")


async def list_tasks():
    data = load_tasks()
    tasks = data.get("tasks", [])
    if not tasks:
        print("No tasks found.")
        return

    print(f"\n{'ID':<5} {'Name':<20} {'Enabled':<8} {'Paused':<8} {'Source':<22} {'Destinations'}")
    print("-" * 100)
    for t in tasks:
        status = "Yes" if t.get("enabled") else "No"
        paused = "Yes" if t["id"] in paused_task_ids else "No"
        dests = ", ".join(str(d) for d in t.get("destination_channel_ids", [t.get("destination_channel_id", "?")]))
        print(f"{t['id']:<5} {t['name']:<20} {status:<8} {paused:<8} {t['source_channel_id']:<22} {dests}")


async def toggle_task():
    await list_tasks()
    try:
        tid = int((await ainput("\nEnter task ID to toggle: ")).strip())
    except ValueError:
        print("Invalid ID.")
        return

    data = load_tasks()
    for t in data["tasks"]:
        if t["id"] == tid:
            t["enabled"] = not t.get("enabled", True)
            save_tasks(data)
            state = "enabled" if t["enabled"] else "disabled"
            print(f"Task {tid} is now {state}.")
            return
    print(f"Task {tid} not found.")


async def edit_task_filters():
    await list_tasks()
    try:
        tid = int((await ainput("\nEnter task ID to edit filters: ")).strip())
    except ValueError:
        print("Invalid ID.")
        return

    data = load_tasks()
    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if not task:
        print(f"Task {tid} not found.")
        return

    filters = task["filters"]
    print(f"\nCurrent filters for task '{task['name']}':")
    for k, v in filters.items():
        print(f"  {k}: {v}")

    print("\nEdit filters (press Enter to keep current value):")

    async def edit_list(key, prompt):
        current = filters.get(key, [])
        raw = (await ainput(f"  {prompt} [{', '.join(current) or 'none'}]: ")).strip()
        if raw:
            filters[key] = [x.strip() for x in raw.split(",") if x.strip()]

    async def edit_bool(key, prompt):
        current = filters.get(key, False)
        raw = (await ainput(f"  {prompt} [{'Y' if current else 'N'}]: ")).strip().lower()
        if raw in ("y", "yes"):
            filters[key] = True
        elif raw in ("n", "no"):
            filters[key] = False

    await edit_list("blacklist_words", "Blacklist words")
    await edit_list("clean_words", "Clean words")
    await edit_bool("clean_urls", "Remove URLs?")
    await edit_bool("clean_usernames", "Remove @usernames?")
    await edit_bool("skip_images", "Skip images?")
    await edit_bool("skip_audio", "Skip audio?")
    await edit_bool("skip_videos", "Skip videos?")

    save_tasks(data)
    print("Filters updated.")


async def delete_task():
    await list_tasks()
    try:
        tid = int((await ainput("\nEnter task ID to delete: ")).strip())
    except ValueError:
        print("Invalid ID.")
        return

    data = load_tasks()
    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if not task:
        print(f"Task {tid} not found.")
        return

    confirm = (await ainput(f"Delete task '{task['name']}' (ID {tid})? [y/N]: ")).strip().lower()
    if confirm in ("y", "yes"):
        data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
        save_tasks(data)
        print(f"Task {tid} deleted.")
    else:
        print("Cancelled.")


async def start_forwarder(client):
    global forwarder_active, active_handlers

    if forwarder_active:
        print("Forwarder is already running.")
        return

    data = load_tasks()
    enabled = [t for t in data.get("tasks", []) if t.get("enabled")]
    tasks_by_id = {t["id"]: t for t in data.get("tasks", [])}

    if not enabled:
        print("No enabled tasks. Create and enable a task first.")
        return

    source_to_tasks = {}
    for t in enabled:
        sid = t["source_channel_id"]
        source_to_tasks.setdefault(sid, []).append(t)

    print("\nResolving source channels...")
    resolved_entities = []
    resolved_ids = {}
    for sid in list(source_to_tasks.keys()):
        try:
            entity = await client.get_entity(sid)
            resolved_entities.append(entity)
            resolved_ids[entity.id] = sid
            print(f"  OK: {getattr(entity, 'title', sid)} (id={sid})")
        except Exception as e:
            print(f"  FAIL to resolve {sid}: {e}")

    if not resolved_entities:
        print("No source channels could be resolved.")
        return

    def get_sid(chat_id):
        if chat_id is None:
            return None
        abs_id = abs(chat_id) % (10 ** 12)
        return resolved_ids.get(abs_id) or resolved_ids.get(chat_id)

    async def new_handler(event):
        if not forwarder_active:
            return
        sid = get_sid(event.chat_id)
        tasks_for_src = source_to_tasks.get(sid, [])
        text_preview = repr((event.message.text or "")[:60])
        add_log(f"MSG chat={event.chat_id} text={text_preview}")

        mmap = load_message_map()
        key = mmap_key(sid, event.message.id)
        mmap.setdefault(key, [])

        for task in tasks_for_src:
            if task["id"] in paused_task_ids:
                add_log(f"  [PAUSED] '{task['name']}' skipped")
                continue

            # Loop protection
            if check_loop(task["id"]):
                paused_task_ids.add(task["id"])
                add_log(f"  [LOOP] '{task['name']}' fired {LOOP_LIMIT}x in {LOOP_WINDOW}s — auto-paused!")
                continue

            should_forward, modified_text = apply_filters(event.message, task["filters"])
            if not should_forward:
                add_log(f"  [SKIP] '{task['name']}' — filtered")
                continue

            dest_ids = task.get("destination_channel_ids") or [task.get("destination_channel_id")]
            for dest_id in dest_ids:
                try:
                    sent = await send_copy(client, dest_id, event.message, modified_text)
                    mmap[key].append({"task_id": task["id"], "dest": dest_id, "msg_id": sent.id})
                    add_log(f"  [OK] '{task['name']}' → {dest_id} (msg {sent.id})")
                except FloodWaitError as e:
                    add_log(f"  [FLOOD] sleeping {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    add_log(f"  [ERR] '{task['name']}' → {dest_id}: {e}")

        save_message_map(mmap)

    async def edit_handler(event):
        if not forwarder_active:
            return
        sid = get_sid(event.chat_id)
        key = mmap_key(sid, event.message.id)
        mmap = load_message_map()
        entries = mmap.get(key, [])
        if not entries:
            return
        add_log(f"EDIT chat={event.chat_id} msg={event.message.id}")
        for entry in entries:
            task = tasks_by_id.get(entry["task_id"])
            if not task:
                continue
            if entry["task_id"] in paused_task_ids:
                continue
            should_forward, modified_text = apply_filters(event.message, task["filters"])
            if not should_forward:
                continue
            new_text = modified_text if modified_text is not None else (event.message.text or "")
            try:
                await client.edit_message(entry["dest"], entry["msg_id"], text=new_text)
                add_log(f"  [EDIT OK] → {entry['dest']} msg {entry['msg_id']}")
            except Exception as e:
                add_log(f"  [EDIT ERR] {entry['dest']}: {e}")

    async def delete_handler(event):
        if not forwarder_active:
            return
        sid = get_sid(event.chat_id)
        mmap = load_message_map()
        changed = False
        for deleted_id in event.deleted_ids:
            key = mmap_key(sid, deleted_id) if sid else None
            entries = mmap.get(key, []) if key else []
            if not entries:
                for k, v in mmap.items():
                    if k.endswith(f":{deleted_id}"):
                        entries = v
                        key = k
                        break
            if not entries:
                continue
            add_log(f"DEL msg={deleted_id}")
            for entry in entries:
                if entry["task_id"] in paused_task_ids:
                    continue
                try:
                    await client.delete_messages(entry["dest"], [entry["msg_id"]])
                    add_log(f"  [DEL OK] → {entry['dest']} msg {entry['msg_id']}")
                except Exception as e:
                    add_log(f"  [DEL ERR] {entry['dest']}: {e}")
            del mmap[key]
            changed = True
        if changed:
            save_message_map(mmap)

    # Register handlers
    client.add_event_handler(new_handler, events.NewMessage(chats=resolved_entities))
    client.add_event_handler(edit_handler, events.MessageEdited(chats=resolved_entities))
    client.add_event_handler(delete_handler, events.MessageDeleted(chats=resolved_entities))

    active_handlers.extend([
        (new_handler, events.NewMessage),
        (edit_handler, events.MessageEdited),
        (delete_handler, events.MessageDeleted),
    ])

    forwarder_active = True
    add_log(f"Forwarder STARTED — watching {len(resolved_entities)} source(s), {len(enabled)} task(s).")


async def stop_forwarder(client):
    global forwarder_active, active_handlers

    if not forwarder_active:
        print("Forwarder is not running.")
        return

    for func, event_type in active_handlers:
        client.remove_event_handler(func, event_type)
    active_handlers.clear()
    forwarder_active = False
    add_log("Forwarder STOPPED.")


async def pause_task_menu():
    await list_tasks()
    try:
        tid = int((await ainput("\nEnter task ID to pause/resume: ")).strip())
    except ValueError:
        print("Invalid ID.")
        return

    data = load_tasks()
    task = next((t for t in data["tasks"] if t["id"] == tid), None)
    if not task:
        print(f"Task {tid} not found.")
        return

    if tid in paused_task_ids:
        paused_task_ids.discard(tid)
        loop_counter.pop(tid, None)  # reset loop counter on resume
        print(f"Task '{task['name']}' resumed.")
    else:
        paused_task_ids.add(tid)
        print(f"Task '{task['name']}' paused (this session only).")


async def view_logs():
    if not log_entries:
        print("No logs yet.")
        return
    print(f"\n--- Logs (last {len(log_entries)} entries) ---")
    for entry in log_entries[-50:]:  # show last 50
        print(entry)
    print()


async def main_menu(client):
    while True:
        status = "RUNNING" if forwarder_active else "STOPPED"
        paused_info = f" | Paused tasks: {sorted(paused_task_ids)}" if paused_task_ids else ""
        print(f"\n=== TridenB Autoforwarder === [Forwarder: {status}{paused_info}]")
        print("1.  Get Channel ID")
        print("2.  Create Forwarding Task")
        print("3.  List Tasks")
        print("4.  Toggle Task (enable/disable)")
        print("5.  Edit Task Filters")
        print("6.  Delete Task")
        print("7.  Start Forwarder (background)")
        print("8.  Stop Forwarder")
        print("9.  Pause / Resume Task")
        print("10. View Logs")
        print("0.  Exit")

        choice = (await ainput("\nSelect option: ")).strip()

        if choice == "1":
            await get_channel_id(client)
        elif choice == "2":
            await create_task(client)
        elif choice == "3":
            await list_tasks()
        elif choice == "4":
            await toggle_task()
        elif choice == "5":
            await edit_task_filters()
        elif choice == "6":
            await delete_task()
        elif choice == "7":
            await start_forwarder(client)
        elif choice == "8":
            await stop_forwarder(client)
        elif choice == "9":
            await pause_task_menu()
        elif choice == "10":
            await view_logs()
        elif choice == "0":
            if forwarder_active:
                confirm = (await ainput("Forwarder is running. Stop and exit? [y/N]: ")).strip().lower()
                if confirm not in ("y", "yes"):
                    continue
                await stop_forwarder(client)
            print("Goodbye.")
            break
        else:
            print("Invalid option.")


async def main():
    load_dotenv()
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    phone = os.getenv("PHONE")

    if not api_id or not api_hash or not phone:
        print("Error: API_ID, API_HASH, and PHONE must be set in .env")
        sys.exit(1)

    client = TelegramClient(SESSION_NAME, int(api_id), api_hash)
    await client.start(phone=phone)
    print("Authenticated successfully.")

    try:
        await main_menu(client)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
