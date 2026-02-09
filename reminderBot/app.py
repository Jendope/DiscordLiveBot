import os
import json
import time
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
REMINDER_CHANNEL_ID = int(os.environ.get("REMINDER_CHANNEL_ID", "0"))
# Comma-separated admin IDs
REMINDER_ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("REMINDER_ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

STATE_FILE = Path("reminder_state.json")
DEFAULT_STATE = {"enabled": True, "interval_days": 3, "last_sent": 0}

def load_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_STATE.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return DEFAULT_STATE.copy()
    else:
        save_state(DEFAULT_STATE)
        return DEFAULT_STATE.copy()

def save_state(state):
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to save state: {e}")

state = load_state()

REMINDER_MESSAGE = (
    "@everyone\n"
    "📝 Verification Form (Required):\n"
    "👉 https://forms.gle/dwSa5H8R8UCjcdCV7\n\n"
    "No verification = no access. Don’t get left behind.\n"
    "Send screenshot of submitted form here: <#1414920625000288317>"
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
REMINDER_CHANNEL = None

@tasks.loop(minutes=60)
async def reminder_checker():
    if not state.get("enabled", True):
        return
    if not REMINDER_CHANNEL:
        print("Reminder channel not ready yet")
        return
    try:
        now = int(time.time())
        interval_seconds = int(state.get("interval_days", 3)) * 86400
        last_sent = int(state.get("last_sent", 0))
        if now - last_sent >= interval_seconds:
            await REMINDER_CHANNEL.send(REMINDER_MESSAGE)
            state["last_sent"] = now
            save_state(state)
            print(f"Sent verification reminder at {now}")
    except Exception as e:
        print(f"Reminder checker error: {e}")

@client.event
async def on_ready():
    global REMINDER_CHANNEL
    print(f"Logged in as {client.user}")
    try:
        REMINDER_CHANNEL = client.get_channel(REMINDER_CHANNEL_ID) if REMINDER_CHANNEL_ID else None
        if REMINDER_CHANNEL is None and REMINDER_CHANNEL_ID:
            print(f"Warning: REMINDER_CHANNEL_ID {REMINDER_CHANNEL_ID} not found or bot lacks access.")
    except Exception:
        REMINDER_CHANNEL = None
    if not reminder_checker.is_running():
        reminder_checker.start()
    print("Reminder checker started")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if not message.content.startswith("!"):
        return

    parts = message.content.strip().split()
    cmd = parts[0].lower()
    is_admin = message.author.id in REMINDER_ADMIN_IDS

    if cmd == "!setreminder":
        if not is_admin:
            await message.channel.send("You are not authorized to change reminder settings.")
            return
        if len(parts) < 2:
            await message.channel.send("Usage: `!setreminder <days>`")
            return
        try:
            days = int(parts[1])
            if days < 1:
                raise ValueError
        except ValueError:
            await message.channel.send("Please provide a valid integer number of days (>=1).")
            return
        state["interval_days"] = days
        save_state(state)
        await message.channel.send(f"Reminder interval set to {days} day(s).")
        return

    if cmd == "!toggle_reminder":
        if not is_admin:
            await message.channel.send("You are not authorized to change reminder settings.")
            return
        state["enabled"] = not state.get("enabled", True)
        save_state(state)
        await message.channel.send("Reminders enabled." if state["enabled"] else "Reminders disabled.")
        return

    if cmd == "!notify":
        if not is_admin:
            await message.channel.send("You are not authorized to send reminders.")
            return
        if not REMINDER_CHANNEL:
            await message.channel.send("Reminder channel not available.")
            return
        try:
            await REMINDER_CHANNEL.send(REMINDER_MESSAGE)
            state["last_sent"] = int(time.time())
            save_state(state)
            await message.channel.send("Reminder sent.")
        except Exception as e:
            await message.channel.send(f"Failed to send reminder: {e}")
        return

    if cmd == "!reminder_status":
        enabled = state.get("enabled", True)
        interval = state.get("interval_days", 3)
        last_sent = state.get("last_sent", 0)
        last_sent_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(last_sent)) if last_sent else "never"
        await message.channel.send(
            f"Reminders: {'enabled' if enabled else 'disabled'}\n"
            f"Interval: {interval} day(s)\n"
            f"Last sent: {last_sent_str}\n"
            f"Reminder channel ID: {REMINDER_CHANNEL_ID}"
        )
        return

if not DISCORD_TOKEN:
    print("DISCORD_TOKEN not set. Exiting.")
else:
    client.run(DISCORD_TOKEN)