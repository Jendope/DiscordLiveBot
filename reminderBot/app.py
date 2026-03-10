import os
import json
import time
import re
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
REMINDER_CHANNEL_ID = int(os.environ.get("REMINDER_CHANNEL_ID", "0"))
REMINDER_ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("REMINDER_ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# --- ROLE CONFIGURATION ---
ROLE_ALIASES = {
    "whale": 1414914532144451635,
    "mexc": 1437068672568135710,
    "bingx": 1437068827602194553,
    "bitget": 1437069004895420547,
    "bitunix": 1455787770558681230,
    "checking": 1468579566594560021
}
REKT_ROLE_ID = 1414914863498788875

KICKREKT_ALLOWED_IDS = [
    404287153213014038, # Shann
    433607960493555722  # James
]
# --------------------------

STATE_FILE = Path("reminder_state.json")

DEFAULT_STATE = {
    "reminders": {
        "1": {
            "enabled": True,
            "interval_days": 3,
            "last_sent": 0,
            "last_sent_date": "",
            "target_time": None,
            "target_day": None,
            "message": (
                "@everyone\n"
                "📝 Verification Form (Required):\n"
                "👉 https://forms.gle/dwSa5H8R8UCjcdCV7\n\n"
                "No verification = no access. Don’t get left behind.\n"
                "Send screenshot of submitted form here: <#1414920625000288317>"
            )
        }
    },
    "next_id": 2
}

def load_state():
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if "reminders" in data:
                    for rem_id, rem_data in data["reminders"].items():
                        if "target_day" not in rem_data:
                            rem_data["target_day"] = None
                    return data
                return DEFAULT_STATE.copy()
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

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
client = discord.Client(intents=intents)

# The Command Tree for Slash Commands
tree = app_commands.CommandTree(client)

REMINDER_CHANNEL = None

@tasks.loop(minutes=1)
async def reminder_checker():
    if not REMINDER_CHANNEL: return
        
    now_dt = datetime.now()
    now_ts = int(now_dt.timestamp())
    current_hm = now_dt.strftime("%H:%M")
    current_date_str = now_dt.strftime("%Y-%m-%d")
    current_weekday = now_dt.strftime("%A").lower()
    
    state_changed = False
    reminders = state.get("reminders", {})
    
    for rem_id, rem_data in reminders.items():
        if not rem_data.get("enabled", True): continue
            
        interval_days = int(rem_data.get("interval_days", 3))
        target_time = rem_data.get("target_time")
        target_day = rem_data.get("target_day")
        last_sent = rem_data.get("last_sent", 0)
        last_sent_date = rem_data.get("last_sent_date", "")
        
        should_send = False

        if target_day:
            time_to_check = target_time if target_time else "00:00"
            if current_weekday == target_day and current_hm >= time_to_check:
                if last_sent_date != current_date_str:
                    should_send = True
        elif target_time:
            if last_sent_date != current_date_str and current_hm >= target_time:
                if last_sent == 0:
                    should_send = True
                else:
                    last_dt = datetime.fromtimestamp(last_sent)
                    days_passed = (now_dt.date() - last_dt.date()).days
                    if days_passed >= interval_days:
                        should_send = True
        else:
            interval_seconds = interval_days * 86400
            if now_ts - last_sent >= interval_seconds:
                should_send = True

        if should_send:
            try:
                await REMINDER_CHANNEL.send(rem_data["message"])
                rem_data["last_sent"] = now_ts
                rem_data["last_sent_date"] = current_date_str
                state_changed = True
                print(f"Sent reminder #{rem_id} at {current_hm} on {current_weekday}")
            except Exception as e:
                print(f"Reminder checker error for ID {rem_id}: {e}")
                
    if state_changed:
        save_state(state)

@client.event
async def on_ready():
    global REMINDER_CHANNEL
    print(f"Logged in as {client.user}")
    
    # Sync slash commands to Discord when the bot starts
    try:
        await tree.sync()
        print("✅ Slash commands synced successfully!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    try:
        REMINDER_CHANNEL = client.get_channel(REMINDER_CHANNEL_ID) if REMINDER_CHANNEL_ID else None
    except Exception:
        REMINDER_CHANNEL = None
        
    if not reminder_checker.is_running():
        reminder_checker.start()
    print("Reminder checker started (running every 1 minute)")


# ==========================================
# 🚀 SLASH COMMANDS
# ==========================================

def is_unauthorized(user_id):
    return user_id not in REMINDER_ADMIN_IDS

@tree.command(name="bottime", description="Check the bot's current timezone and time")
async def slash_bottime(interaction: discord.Interaction):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_day = datetime.now().strftime("%A")
    await interaction.response.send_message(f"🕒 **Bot's Local Time:** `{current_day}, {current_time}`", ephemeral=True)

@tree.command(name="addrole", description="Assign multiple roles to multiple users")
@app_commands.describe(roles="Comma-separated roles (e.g. whale,mexc) or @Role", users="@User1 @User2 or UserIDs")
async def slash_addrole(interaction: discord.Interaction, roles: str, users: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
    await interaction.response.defer(ephemeral=True) # Defer because adding roles takes time
    
    role_inputs = [r.strip().lower() for r in roles.split(",")]
    roles_to_add = []
    for r_in in role_inputs:
        role_id = ROLE_ALIASES.get(r_in)
        if not role_id:
            match = re.search(r'\d+', r_in)
            if match: role_id = int(match.group())
        if role_id:
            role_obj = interaction.guild.get_role(role_id)
            if role_obj: roles_to_add.append(role_obj)
                
    if not roles_to_add:
        return await interaction.followup.send("❌ None of the specified roles were found in the server.", ephemeral=True)

    user_ids = []
    for u_in in users.split():
        match = re.search(r'\d+', u_in)
        if match: user_ids.append(int(match.group()))

    if not user_ids:
        return await interaction.followup.send("❌ No valid user IDs or mentions found.", ephemeral=True)

    success_count = 0
    fail_count = 0
    
    for uid in user_ids:
        member = interaction.guild.get_member(uid)
        if not member:
            try: member = await interaction.guild.fetch_member(uid)
            except: pass
        if member:
            try:
                await member.add_roles(*roles_to_add)
                success_count += 1
            except: fail_count += 1
        else: fail_count += 1

    role_names = ", ".join([r.name for r in roles_to_add])
    await interaction.followup.send(f"✅ Added **{role_names}** to {success_count} user(s).\n❌ Failed for {fail_count} user(s).", ephemeral=True)


@tree.command(name="kickrekt", description="Kick everyone holding the Rekt Citizen role")
async def slash_kickrekt(interaction: discord.Interaction):
    if interaction.user.id not in KICKREKT_ALLOWED_IDS:
        return await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)

    rekt_role = interaction.guild.get_role(REKT_ROLE_ID)
    if not rekt_role:
        return await interaction.response.send_message("❌ The 'Rekt Citizen' role could not be found.", ephemeral=True)
        
    members_to_kick = rekt_role.members
    if not members_to_kick:
        return await interaction.response.send_message("✅ No users found with the 'Rekt Citizen' role. Server is clean!", ephemeral=True)
        
    await interaction.response.defer(ephemeral=True)
    
    success_count = 0
    fail_count = 0
    for member in members_to_kick:
        try:
            await member.kick(reason="Automated kick for holding the Rekt Citizen role via Slash Command.")
            success_count += 1
        except Exception:
            fail_count += 1
            
    await interaction.followup.send(f"✅ Done! Kicked **{success_count}** users.\n❌ Failed to kick **{fail_count}** users.", ephemeral=True)


@tree.command(name="listreminders", description="View all active reminders")
async def slash_listreminders(interaction: discord.Interaction):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
    reminders = state.get("reminders", {})
    if not reminders:
        return await interaction.response.send_message("There are currently no reminders set.", ephemeral=True)
        
    reply_text = "**📋 Active Reminders:**\n\n"
    for r_id, r_data in reminders.items():
        status = "🟢 Enabled" if r_data.get("enabled", True) else "🔴 Disabled"
        days = r_data.get("interval_days", 3)
        t_time = r_data.get("target_time")
        t_day = r_data.get("target_day")
        
        if t_day and t_time: schedule_str = f"Every {t_day.capitalize()} at {t_time}"
        elif t_day: schedule_str = f"Every {t_day.capitalize()}"
        elif t_time: schedule_str = f"Every {days} day(s) at {t_time}"
        else: schedule_str = f"Every {days} day(s)"

        preview = r_data.get("message", "").replace("\n", " ")[:60] + "..."
        reply_text += f"**ID: {r_id}** | {schedule_str} | {status}\n*Preview:* `{preview}`\n\n"
        
    await interaction.response.send_message(reply_text, ephemeral=True)


@tree.command(name="addreminder", description="Create a new reminder")
@app_commands.describe(days="Number of days interval", message="The reminder text")
async def slash_addreminder(interaction: discord.Interaction, days: int, message: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
    if days < 1:
        return await interaction.response.send_message("❌ Days must be 1 or higher.", ephemeral=True)
        
    rem_id = str(state.get("next_id", 1))
    state["reminders"][rem_id] = {
        "enabled": True,
        "interval_days": days,
        "last_sent": 0,
        "last_sent_date": "",
        "target_time": None,
        "target_day": None,
        "message": message
    }
    state["next_id"] += 1
    save_state(state)
    await interaction.response.send_message(f"✅ Created **Reminder #{rem_id}** (every {days} days)!", ephemeral=True)


@tree.command(name="editday", description="Set a specific day of the week for a reminder")
@app_commands.describe(ids="Comma-separated IDs (e.g. 1,2)", day="monday, tuesday, etc. (or 'clear')")
async def slash_editday(interaction: discord.Interaction, ids: str, day: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    target_d = day.lower()
    valid_days = ["none", "clear", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if target_d not in valid_days:
        return await interaction.response.send_message("❌ Invalid day! Use a full day name or 'clear'.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    
    for rem_id in rem_ids:
        if rem_id not in state.get("reminders", {}):
            results.append(f"❌ ID {rem_id} not found.")
            continue
        if target_d in ["none", "clear"]:
            state["reminders"][rem_id]["target_day"] = None
            results.append(f"✅ Day restriction removed for #{rem_id}.")
        else:
            state["reminders"][rem_id]["target_day"] = target_d
            results.append(f"✅ #{rem_id} scheduled for every {target_d.capitalize()}.")

    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="edittime", description="Set a specific time of day for a reminder")
@app_commands.describe(ids="Comma-separated IDs (e.g. 1,2)", time="24-hour format (e.g. 14:30) or 'clear'")
async def slash_edittime(interaction: discord.Interaction, ids: str, time: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    target_t = time.lower()
    if target_t not in ["none", "clear"]:
        try:
            datetime.strptime(target_t, "%H:%M")
        except ValueError:
            return await interaction.response.send_message("❌ Invalid time format! Use HH:MM (e.g. `14:30`).", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    
    for rem_id in rem_ids:
        if rem_id not in state.get("reminders", {}):
            results.append(f"❌ ID {rem_id} not found.")
            continue
        if target_t in ["none", "clear"]:
            state["reminders"][rem_id]["target_time"] = None
            results.append(f"✅ Time restriction removed for #{rem_id}.")
        else:
            state["reminders"][rem_id]["target_time"] = target_t
            results.append(f"✅ #{rem_id} scheduled for **{target_t}**.")

    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="viewmessage", description="Read the full text of a specific reminder")
@app_commands.describe(ids="Comma-separated IDs (e.g. 1,2)")
async def slash_viewmessage(interaction: discord.Interaction, ids: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            msg = state["reminders"][rem_id]["message"]
            results.append(f"**Message for #{rem_id}:**\n{msg}\n---")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="editmessage", description="Replace the text of a reminder")
@app_commands.describe(ids="Comma-separated IDs", new_message="The new reminder text")
async def slash_editmessage(interaction: discord.Interaction, ids: str, new_message: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            state["reminders"][rem_id]["message"] = new_message
            results.append(f"✅ Updated message for #{rem_id}.")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="editinterval", description="Change how many days between reminders")
@app_commands.describe(ids="Comma-separated IDs", days="Number of days")
async def slash_editinterval(interaction: discord.Interaction, ids: str, days: int):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    if days < 1: return await interaction.response.send_message("❌ Days must be 1 or higher.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            state["reminders"][rem_id]["interval_days"] = days
            state["reminders"][rem_id]["target_day"] = None # Remove day lock if interval changes
            results.append(f"✅ Changed #{rem_id} to trigger every {days} day(s).")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="toggle_reminder", description="Pause or unpause a reminder")
@app_commands.describe(ids="Comma-separated IDs")
async def slash_toggle(interaction: discord.Interaction, ids: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            current = state["reminders"][rem_id].get("enabled", True)
            state["reminders"][rem_id]["enabled"] = not current
            status_str = "Enabled" if not current else "Disabled"
            results.append(f"#{rem_id} is now **{status_str}**.")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="delreminder", description="Permanently delete a reminder")
@app_commands.describe(ids="Comma-separated IDs")
async def slash_delreminder(interaction: discord.Interaction, ids: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            del state["reminders"][rem_id]
            results.append(f"🗑️ Deleted #{rem_id}.")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    save_state(state)
    await interaction.response.send_message("\n".join(results), ephemeral=True)


@tree.command(name="notify", description="Force the bot to send a reminder immediately")
@app_commands.describe(ids="Comma-separated IDs")
async def slash_notify(interaction: discord.Interaction, ids: str):
    if is_unauthorized(interaction.user.id):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    if not REMINDER_CHANNEL:
        return await interaction.response.send_message("❌ Reminder channel not available.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    rem_ids = [r.strip("<> ") for r in ids.split(",") if r.strip("<> ")]
    results = []
    
    for rem_id in rem_ids:
        if rem_id in state.get("reminders", {}):
            rem_data = state["reminders"][rem_id]
            try:
                await REMINDER_CHANNEL.send(rem_data["message"])
                now_dt = datetime.now()
                rem_data["last_sent"] = int(now_dt.timestamp())
                rem_data["last_sent_date"] = now_dt.strftime("%Y-%m-%d")
                results.append(f"📢 Sent #{rem_id} successfully.")
            except Exception as e:
                results.append(f"❌ Failed to send #{rem_id}: {e}")
        else:
            results.append(f"❌ ID {rem_id} not found.")
            
    save_state(state)
    await interaction.followup.send("\n".join(results), ephemeral=True)


# ==========================================
# TEXT TRIGGERS (Auto-Replies)
# ==========================================

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.lower().strip()

    if "bleu" in content:
        await message.reply("ang pogi mo <@433607960493555722>", mention_author=True)
    elif "shann" in content or "shnncrypt" in content or "404287153213014038" in content:
        await message.reply("Bading na bading si shann", mention_author=True)
    elif content in ["tanginamo", "tangina mo", "inamo", "taena mo"]:
        await message.reply("tangina mo rin", mention_author=True)
    elif content in ["putanginamo", "putangina mo"]:
        await message.reply("putangina mo rin", mention_author=True)
    elif content in ["<@749211272008171601>"] in content:
        await message.reply("Ang ganda ni ren", mention_author=True)
    elif "princess" in content or "1081556256394842112" in content:
        await message.reply("GA Hunter, una pa sa first", mention_author=True)
    elif content in ["ulol", "ulol ka"]:
        await message.reply("ulol ka rin", mention_author=True)
    elif content == "gago":
        await message.reply("gago ka rin", mention_author=True)
    elif content in ["panget", "panget ka"]:
        await message.reply("panget ka rin", mention_author=True)
    elif content in ["bading", "gay", "g4y"]:
        await message.reply("puro ka kabadingan!!!>", mention_author=True)


if not DISCORD_TOKEN:
    print("DISCORD_TOKEN not set. Exiting.")
else:
    client.run(DISCORD_TOKEN)