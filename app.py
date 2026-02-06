import os
import discord
import requests
from discord.ext import tasks
from dotenv import load_dotenv
load_dotenv()

# --- Secrets (set these in Replit Secrets panel) ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID"))
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")
TWITCH_CHANNEL = "shanntidotes"  # Twitch usernamexX
#TWITCH_CHANNEL = "MxnkeyLoL"  # Twitch usernamexX

# --- Discord setup ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)

last_live_status = False
TWITCH_TOKEN = None
DISCORD_CHANNEL = None

# --- Twitch helpers ---
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

    # Refresh token if expired
    if resp.status_code == 401:
        TWITCH_TOKEN = get_twitch_token()
        headers["Authorization"] = f"Bearer {TWITCH_TOKEN}"
        resp = requests.get(url, headers=headers)

    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None

# --- Background task ---
@tasks.loop(minutes=2)
async def twitch_check():
    global last_live_status
    stream = check_twitch_live()

    if not DISCORD_CHANNEL:
        print("Discord channel not ready yet")
        return

    if stream and not last_live_status:
        last_live_status = True
        print(f"{TWITCH_CHANNEL} is live!")
        ...
    elif not stream and last_live_status:
        last_live_status = False
        print(f"{TWITCH_CHANNEL} went offline")

    if stream and not last_live_status:
        last_live_status = True
        title = stream["title"]
        game = stream["game_name"]
        url = f"https://twitch.tv/{TWITCH_CHANNEL}"
        thumbnail = stream["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720")

        embed = discord.Embed(
            title=f"{TWITCH_CHANNEL} is now LIVE!",
            description=f"**{title}**\nPlaying: {game}",
            url=url,
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="Watch here:", value=url, inline=False)

        await DISCORD_CHANNEL.send(content="Tara LIVE! @everyone", embed=embed)

    elif not stream and last_live_status:
        last_live_status = False
        # Optional: announce stream ended
        # await DISCORD_CHANNEL.send(f"{TWITCH_CHANNEL} has ended the stream.")

@client.event
async def on_ready():
    global DISCORD_CHANNEL
    print(f"Logged in as {client.user}")
    DISCORD_CHANNEL = client.get_channel(DISCORD_CHANNEL_ID)
    twitch_check.start()

client.run(DISCORD_TOKEN)