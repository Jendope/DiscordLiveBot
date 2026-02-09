import os
import json
import time
import requests
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Core config
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
REMINDER_CHANNEL_ID = int(os.environ.get("REMINDER_CHANNEL_ID", DISCORD_CHANNEL_ID))
# Comma-separated admin IDs in .env, e.g. "433607960493555722,404287153213014038"
REMINDER_ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("REMINDER_ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")
TWITCH_CHANNEL = os.environ.get("TWITCH_CHANNEL", "shanntidotes")

# Paths
STATE_FILE = Path("reminder_state.json")

# Default state
DEFAULT_STATE = {
    "enabled": True,
    "interval_days": 3,
    # epoch seconds of last sent reminder; initialize to 0 so first send happens after interval
    "last_sent": 0
}

# Load or create persistent state
def load_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure keys exist
                for k, v in DEFAULT_STATE.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            print(f"Failed to read state file, using defaults: {e}")
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

# Reminder message
REMINDER_MESSAGE = (
    "@everyone\n"
    "📝 Verification Form (Required):\n"
    "👉 https://forms.gle/dwSa5H8R8UCjcdCV7\n\n"
    "No verification = no access. Don’t get left behind.\n"
    "Send screenshot of submitted form here: 1414920625000288317"
)

# Discord client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Twitch variables
last_live_status = False
TWITCH_TOKEN = None
DISCORD_CHANNEL = None
REMINDER_CHANNEL = None

def get_twitch_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, params=params)
    resp.raise_for_status()
    return resp.json()["access_token"]

def check_twitch_live():
    global TWITCH_TOKEN
    if not TWITCH_TOKEN:
        TWITCH_TOKEN = get_twitch_token()

    url = f"https://api.twitch.tv/helix/streams?user_login={TWITCH_CHANNEL}"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_TOKEN}"
    }
    resp = requests.get(url, headers=headers)

    if resp.status_code == 401:
        TWITCH_TOKEN = get_twitch_token()
        headers["Authorization"] = f"Bearer {TWITCH_TOKEN}"
        resp = requests.get(url, headers=headers)

    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None

@tasks.loop(minutes=2)
async def twitch_check():
    global last_live_status
    try:
        stream = check_twitch_live()
    except Exception as e:
        print(f"Error checking Twitch: {e}")
        return

    if not DISCORD_CHANNEL:
        print("Discord channel not ready yet")
        return

    if stream and not last_live_status:
        last_live_status = True
        title = stream.get("title", "Untitled")
        game = stream.get("game_name", "Unknown")
        url = f"https://twitch.tv/{TWITCH_CHANNEL}"
        thumbnail = stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")

        embed = discord.Embed(
            title=f"{TWITCH_CHANNEL} is now LIVE!",
            description=f"**{title}**\nPlaying: {game}",
            url=url,
            color=discord.Color.purple()
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Watch here:", value=url, inline=False)

        try:
            await DISCORD_CHANNEL.send(content=f"{TWITCH_CHANNEL} is LIVE! @everyone 🎮", embed=embed)
            print(f"Announced live stream: {title}")
        except Exception as e:
            print(f"Failed to send live announcement: {e}")

    elif not stream and last_live_status:
        last_live_status = False
        try:
            await DISCORD_CHANNEL.send(f"{TWITCH_CHANNEL} has ended the stream.")
            print("Announced stream ended")
        except Exception as e:
            print(f"Failed to send stream ended message: {e}")

# Reminder checker runs periodically and decides whether to send based on last_sent and interval
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
        # If never sent (0), schedule first send after interval_seconds from container start.
        # If you want immediate send on first run, set last_sent = now - interval_seconds
        if now - last_sent >= interval_seconds:
            await REMINDER_CHANNEL.send(REMINDER_MESSAGE)
            state["last_sent"] = now
            save_state(state)
            print(f"Sent verification reminder to channel {REMINDER_CHANNEL.id} at {now}")
    except Exception as e:
        print(f"Failed to run reminder checker: {e}")

@client.event
async def on_ready():
    global DISCORD_CHANNEL, REMINDER_CHANNEL
    print(f"Logged in as {client.user}")

    # Resolve channels
    try:
        DISCORD_CHANNEL = client.get_channel(DISCORD_CHANNEL_ID) if DISCORD_CHANNEL_ID else None
        if DISCORD_CHANNEL is None and DISCORD_CHANNEL_ID:
            print(f"Warning: DISCORD_CHANNEL_ID {DISCORD_CHANNEL_ID} not found or bot lacks access.")
    except Exception:
        DISCORD_CHANNEL = None

    try:
        REMINDER_CHANNEL = client.get_channel(REMINDER_CHANNEL_ID) if REMINDER_CHANNEL_ID else None
        if REMINDER_CHANNEL is None and REMINDER_CHANNEL_ID:
            print(f"Warning: REMINDER_CHANNEL_ID {REMINDER_CHANNEL_ID} not found or bot lacks access.")
    except Exception:
        REMINDER_CHANNEL = None

    if not twitch_check.is_running():
        twitch_check.start()

    if not reminder_checker.is_running():
        reminder_checker.start()

    print("Background tasks started: twitch_check, reminder_checker")

@client.event
async def on_message(message):
    # Ignore bot messages
    if message.author == client.user:
        return

    # Only process commands that start with "!"
    if not message.content.startswith("!"):
        return

    parts = message.content.strip().split()
    cmd = parts[0].lower()

    is_admin = message.author.id in REMINDER_ADMIN_IDS

    # Admin commands
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
        if state["enabled"]:
            await message.channel.send("Reminders enabled.")
        else:
            await message.channel.send("Reminders disabled.")
        return

    if cmd == "!send_reminder_now":
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
        # Anyone can check status
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

# Run the bot
if not DISCORD_TOKEN:
    print("DISCORD_TOKEN not set. Exiting.")
else:
    client.run(DISCORD_TOKEN)