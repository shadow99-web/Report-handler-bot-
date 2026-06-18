import discord
from discord.ext import commands
import os
import json
import re
import asyncio
import base64
from datetime import datetime
from huggingface_hub import HfApi, upload_file, hf_hub_download
import requests

# ============================================================
# 🔐 TOKENS & CONFIG
# ============================================================
BOT_TOKEN = os.getenv("REPORT_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PREFIX = "_"

# Cooldown tracking
command_cooldowns = {}
COOLDOWN_SECONDS = 5  # seconds
DEVELOPER_IDS = [1378954077462986772]  # your main dev ID, same as ADMIN_IDS

HF_TOKEN = os.getenv("HF_TOKEN", "YOUR_HF_TOKEN_HERE")
HF_DATASET_REPO = "DiscordBOTNHIHUN/P2AURA-FARMER"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "YOUR_GITHUB_TOKEN_HERE")
SPAWN_RATES_REPO = "shadow99-web/Report-handler-bot-"
SPAWN_RATES_FILE = "pokemon_chances.txt"

SERVER_CONFIG_FILE = "report_server_configs.json"
USER_REPORTS_FILE = "user_reports.json"

# ============================================================
# 🎨 CUSTOM EMOJIS
# ============================================================
EMOJI_REPORT = "<a:report:123456789012345678>"
EMOJI_SUCCESS = "<:success:123456789012345678>"
EMOJI_WARNING = "<:warning:123456789012345678>"
EMOJI_MUTE = "<:mute:123456789012345678>"
EMOJI_PUNISH = "<:punish:123456789012345678>"
EMOJI_TRADE = "<:trade:123456789012345678>"
EMOJI_CHECK = "✅"
EMOJI_WARN = "⚠️"
EMOJI_LOCK = "🔒"

# ============================================================
# 📂 HUGGING FACE HELPERS
# ============================================================
hf_api = HfApi()

def load_hf_file(filename, default=None):
    try:
        path = hf_hub_download(repo_id=HF_DATASET_REPO, filename=filename, repo_type="dataset", token=HF_TOKEN)
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_hf_file(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    try:
        upload_file(path_or_fileobj=filename, path_in_repo=filename, repo_id=HF_DATASET_REPO, repo_type="dataset", token=HF_TOKEN)
        print(f"☁️ [HF] Synced {filename}")
    except Exception as e:
        print(f"❌ HF upload failed for {filename}: {e}")

# ============================================================
# 📦 FETCH SPAWN RATES FROM GITHUB
# ============================================================
SPAWN_RATES = {}

def fetch_spawn_rates_from_github():
    global SPAWN_RATES
    url = f"https://api.github.com/repos/{SPAWN_RATES_REPO}/contents/{SPAWN_RATES_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode('utf-8')
            lines = content.strip().split('\n')
            for line in lines[1:]:
                if not line.strip():
                    continue
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    pokemon = parts[1].strip()
                    chance = parts[2].strip()
                    match = re.search(r'1/(\d+)', chance)
                    if match:
                        rate = int(match.group(1))
                        clean_name = re.sub(r'[♀♂️]', '', pokemon).strip().lower()
                        if clean_name:
                            SPAWN_RATES[clean_name] = rate
            print(f"{EMOJI_CHECK} Fetched {len(SPAWN_RATES)} spawn rates")
            return True
    except Exception as e:
        print(f"{EMOJI_WARN} Error: {e}")
    return False

fetch_spawn_rates_from_github()

# ============================================================
# ⚖️ COMPENSATION & PUNISHMENT LOGIC
# ============================================================
def get_compensation(pokemon_name):
    rate = SPAWN_RATES.get(pokemon_name.lower(), 100)
    if rate >= 15196:
        return 40000
    elif rate >= 5394:
        return 35000
    elif rate >= 3596:
        return 30000
    elif rate >= 1349:
        return 20000
    elif rate >= 899:
        return 15000
    elif rate >= 674:
        return 10000
    elif rate >= 337:
        return 5000
    else:
        return 4000

def get_punishment_duration(pokemon_name):
    rate = SPAWN_RATES.get(pokemon_name.lower(), 100)
    if rate >= 69043:
        return 60
    elif rate >= 28768:
        return 45
    elif rate >= 14384:
        return 30
    elif rate >= 3596:
        return 20
    else:
        return 10

def parse_time(value):
    value = str(value).lower().strip()
    if value.endswith('h'):
        return int(value[:-1]) * 60
    elif value.endswith('m'):
        return int(value[:-1])
    else:
        return int(value)

async def apply_punishment(stealer, pokemon_name, config):
    if not config["punishment_enabled"]:
        return f"{EMOJI_WARN} Punishment disabled."
    ptype = config["punishment_type"]
    pvalue = config["punishment_value"]
    role_id = config["punishment_role_id"]
    if ptype == "timeout":
        minutes = parse_time(pvalue)
        try:
            await stealer.timeout(discord.utils.utcnow() + discord.timedelta(minutes=minutes),
                                  reason=f"Stole {pokemon_name}")
            return f"{EMOJI_CHECK} {stealer.mention} timed out for {minutes} minutes."
        except:
            return f"{EMOJI_WARN} Could not timeout {stealer.mention}."
    elif ptype == "ban":
        try:
            await stealer.ban(reason=f"Stole {pokemon_name}")
            return f"{EMOJI_CHECK} {stealer.mention} banned."
        except:
            return f"{EMOJI_WARN} Could not ban {stealer.mention}."
    elif ptype == "role":
        role = stealer.guild.get_role(role_id)
        if not role:
            return f"{EMOJI_WARN} Role not found."
        try:
            await stealer.remove_roles(role, reason=f"Stole {pokemon_name}")
            return f"{EMOJI_CHECK} Removed {role.mention} from {stealer.mention}."
        except:
            return f"{EMOJI_WARN} Could not remove role."
    elif ptype == "warn":
        minutes = parse_time(pvalue)
        try:
            await stealer.timeout(discord.utils.utcnow() + discord.timedelta(minutes=minutes),
                                  reason=f"Warned for stealing {pokemon_name}")
            return f"{EMOJI_CHECK} {stealer.mention} warned and muted for {minutes} min."
        except:
            return f"{EMOJI_WARN} Could not warn {stealer.mention}."
    return f"{EMOJI_WARN} Unknown punishment type."

# ============================================================
# 🤖 DISCORD BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
active_reports = {}

# ============================================================
# ⚙️ PER‑SERVER CONFIG
# ============================================================
server_configs = load_hf_file(SERVER_CONFIG_FILE, {})

def get_server_config(guild_id):
    guild_id_str = str(guild_id)
    if guild_id_str not in server_configs:
        server_configs[guild_id_str] = {
            "handler_role_id": 0,
            "log_channel_id": 0,
            "punishment_enabled": True,
            "punishment_type": "timeout",
            "punishment_value": "1h",
            "punishment_role_id": 0,
            "panel_sent": False
        }
        save_hf_file(SERVER_CONFIG_FILE, server_configs)
    return server_configs[guild_id_str]

def save_server_config(guild_id, config):
    guild_id_str = str(guild_id)
    server_configs[guild_id_str] = config
    save_hf_file(SERVER_CONFIG_FILE, server_configs)

# ============================================================
# 📊 USER REPORTS
# ============================================================
user_reports = load_hf_file(USER_REPORTS_FILE, {})

def get_user_stats(user_id):
    user_id_str = str(user_id)
    return user_reports.get(user_id_str, {
        "username": "",
        "total_reports": 0,
        "successful_reports": 0,
        "unsuccessful_reports": 0,
        "last_report": None,
        "pokemons_reported": []
    })

def update_user_stats(user_id, username, pokemon, success=True):
    user_id_str = str(user_id)
    if user_id_str not in user_reports:
        user_reports[user_id_str] = {
            "username": username,
            "total_reports": 0,
            "successful_reports": 0,
            "unsuccessful_reports": 0,
            "last_report": None,
            "pokemons_reported": []
        }
    entry = user_reports[user_id_str]
    entry["total_reports"] += 1
    if success:
        entry["successful_reports"] += 1
    else:
        entry["unsuccessful_reports"] += 1
    entry["last_report"] = datetime.now().isoformat()
    if pokemon.lower() not in [p.lower() for p in entry["pokemons_reported"]]:
        entry["pokemons_reported"].append(pokemon)
    save_hf_file(USER_REPORTS_FILE, user_reports)

# ============================================================
# 🧠 HELPER: Extract Stealer from Message Link
# ============================================================
async def extract_stealer_from_link(guild, link_or_id):
    """Extract stealer from either the catch command or Pokétwo's response."""
    match = re.search(r'discord\.com/channels/\d+/(\d+)/(\d+)', link_or_id)
    if match:
        channel_id = int(match.group(1))
        message_id = int(match.group(2))
    elif link_or_id.isdigit():
        return None
    else:
        return None

    try:
        channel = guild.get_channel(channel_id)
        if not channel:
            channel = await guild.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)

        # Scenario 1: Message is from the stealer (catch command)
        if msg.author.id != 716390085896962058:
            stealer = guild.get_member(msg.author.id)
            if stealer:
                return stealer

        # Scenario 2: Message is from Pokétwo (response)
        if msg.author.id == 716390085896962058:
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.description:
                        match = re.search(r'<@!?(\d+)>', embed.description)
                        if match:
                            user_id = int(match.group(1))
                            return guild.get_member(user_id)
                    for field in embed.fields:
                        match = re.search(r'<@!?(\d+)>', field.value)
                        if match:
                            user_id = int(match.group(1))
                            return guild.get_member(user_id)
            if msg.content:
                match = re.search(r'<@!?(\d+)>', msg.content)
                if match:
                    user_id = int(match.group(1))
                    return guild.get_member(user_id)
        return None
    except Exception as e:
        print(f"Error fetching message: {e}")
        return None

# ============================================================
# 📨 REPORT CREATION
# ============================================================
async def create_report(source, reporter, stealer, pokemon_name, message_link=None):
    if isinstance(source, discord.Interaction):
        guild = source.guild
        channel = source.channel
        followup = source.followup
    else:
        guild = source.guild
        channel = source.channel
        followup = None

    if pokemon_name.lower() not in SPAWN_RATES:
        msg = f"{EMOJI_WARN} Pokémon `{pokemon_name}` not found."
        if followup:
            await followup.send(msg, ephemeral=True)
        else:
            await source.send(msg)
        return

    config = get_server_config(guild.id)

    thread = await channel.create_thread(
        name=f"report-{stealer.name}-{pokemon_name}",
        type=discord.ChannelType.public_thread
    )
    report_data = {
        "reporter": reporter,
        "stealer": stealer,
        "pokemon": pokemon_name,
        "thread": thread,
        "status": "pending",
        "paid": False,
        "start_time": datetime.now(),
        "guild_id": guild.id,
        "message_link": message_link,
        "proof_link": None
    }
    active_reports[thread.id] = report_data

    handler_role = guild.get_role(config["handler_role_id"])
    handler_ping = handler_role.mention if handler_role else "No handler role."

    # --- Send initial mention message with payment amount ---
    mute_duration_minutes = get_punishment_duration(pokemon_name)
    duration_text = f"{mute_duration_minutes} minutes"
    if mute_duration_minutes >= 60:
        hours = mute_duration_minutes // 60
        duration_text = f"{hours} hour{'s' if hours > 1 else ''}"
    elif mute_duration_minutes < 1:
        duration_text = "a few seconds"

    required_pc = get_compensation(pokemon_name)
    if pokemon_name.lower() == "missingno":
        payment_text = f"{required_pc:,} PC (redeems not accepted)"
    else:
        payment_text = f"{required_pc:,} PC OR 1 Redeem"

    initial_message = (
        f"{stealer.mention} you have stolen the catch of {reporter.mention}, "
        f"pokemon you have stolen **{pokemon_name}**.\n\n"
        f"**Compensation Required:** {payment_text}\n"
        f"**Punishment if not paid:** {duration_text} mute"
    )
    await thread.send(initial_message)

    # --- Embed ---
    embed = discord.Embed(
        title=f"{EMOJI_REPORT} Report #{thread.id}",
        description=f"**Pokémon:** {pokemon_name}\n**Stealer:** {stealer.mention}\n**Reporter:** {reporter.mention}",
        color=0x2C2C2C
    )
    embed.add_field(name="Spawn Rate", value=f"1/{SPAWN_RATES.get(pokemon_name.lower(), 100)}", inline=True)
    embed.add_field(name="Compensation", value=payment_text, inline=True)
    embed.add_field(name="Punishment", value=f"{duration_text}", inline=True)
    if message_link:
        embed.add_field(name="Evidence", value=f"[Click here]({message_link})", inline=False)
    embed.set_footer(text="Resolve this report.")

    await thread.send(f"{handler_ping} {stealer.mention} {reporter.mention}")
    await thread.send(embed=embed, view=ReportActions(thread.id))

    if followup:
        await followup.send(f"{EMOJI_CHECK} Report created in {thread.mention}", ephemeral=True)
    else:
        await source.send(f"{EMOJI_CHECK} Report created in {thread.mention}")

# ============================================================
# 🔘 REPORT ACTIONS VIEW
# ============================================================
class ReportActions(discord.ui.View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Paid", style=discord.ButtonStyle.success, emoji=EMOJI_SUCCESS)
    async def paid_button(self, interaction, button):
        report = active_reports.get(self.thread_id)
        if not report:
            return await interaction.response.send_message(f"{EMOJI_WARN} Report not found.", ephemeral=True)
        if interaction.user.id != report["reporter"].id:
            return await interaction.response.send_message(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)

        report["paid"] = True
        report["status"] = "resolved"
        update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)

        modal = PaymentConfirmationModal(report["pokemon"], report["stealer"].name, self.thread_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Not Paid", style=discord.ButtonStyle.danger, emoji=EMOJI_WARNING)
    async def not_paid_button(self, interaction, button):
        report = active_reports.get(self.thread_id)
        if not report:
            return await interaction.response.send_message(f"{EMOJI_WARN} Report not found.", ephemeral=True)
        if interaction.user.id != report["reporter"].id:
            return await interaction.response.send_message(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)

        thread = interaction.channel
        proof_link = None
        async for msg in thread.history(limit=50):
            if msg.author.id == 716390085896962058 and "Completed trade between" in msg.content:
                proof_link = msg.jump_url
                break

        if proof_link:
            report["paid"] = True
            report["status"] = "resolved"
            report["proof_link"] = proof_link
            await interaction.response.send_message(
                f"{EMOJI_CHECK} Trade found! Report resolved. Payment confirmed.\n**Proof:** {proof_link}"
            )
            update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
            await thread.edit(archived=True, locked=True)
            active_reports.pop(self.thread_id, None)
            # Log the closure with proof
            config = get_server_config(interaction.guild.id)
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            if log_channel:
                embed = discord.Embed(
                    title="📋 Report Closed (Auto via Trade Proof)",
                    description=f"**Pokémon:** {report['pokemon']}\n**Stealer:** {report['stealer'].mention}\n**Reporter:** {report['reporter'].mention}\n**Status:** Paid ✅",
                    color=0x2C2C2C
                )
                embed.add_field(name="📎 Trade Proof", value=f"[Click here]({proof_link})", inline=False)
                if report.get("message_link"):
                    embed.add_field(name="📎 Evidence", value=f"[Click here]({report['message_link']})", inline=False)
                await log_channel.send(embed=embed)
            return

        # No trade found – apply punishment
        await interaction.response.send_message(f"{EMOJI_PUNISH} Applying punishment...")
        config = get_server_config(interaction.guild.id)
        result = await apply_punishment(report["stealer"], report["pokemon"], config)
        await interaction.followup.send(result)
        update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=False)
        report["status"] = "resolved"
        await self.close_report(interaction, success=False)

    async def close_report(self, interaction, success=False):
        report = active_reports.pop(self.thread_id, None)
        if report:
            config = get_server_config(interaction.guild.id)
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            if log_channel:
                embed = discord.Embed(
                    title="📋 Report Closed",
                    description=f"**Pokémon:** {report['pokemon']}\n**Stealer:** {report['stealer'].mention}\n**Reporter:** {report['reporter'].mention}\n**Status:** {'Paid ✅' if success else 'Punished 🔨'}",
                    color=0x2C2C2C
                )
                if report.get("proof_link"):
                    embed.add_field(name="📎 Trade Proof", value=f"[Click here]({report['proof_link']})", inline=False)
                if report.get("message_link"):
                    embed.add_field(name="📎 Evidence", value=f"[Click here]({report['message_link']})", inline=False)
                await log_channel.send(embed=embed)
        try:
            await interaction.channel.edit(archived=True, locked=True)
        except:
            pass
        await interaction.followup.send(f"{EMOJI_LOCK} Report archived.")

# ============================================================
# 💬 PAYMENT CONFIRMATION MODAL
# ============================================================
class PaymentConfirmationModal(discord.ui.Modal, title="Payment Confirmation"):
    amount = discord.ui.TextInput(
        label="Amount Received",
        placeholder="e.g., 40000 PC or 1 Redeem (optional)",
        required=False
    )
    feedback = discord.ui.TextInput(
        label="Feedback about Stealer",
        placeholder="Any comments? (optional)",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(self, pokemon_name, stealer_name, thread_id):
        super().__init__()
        self.pokemon_name = pokemon_name
        self.stealer_name = stealer_name
        self.thread_id = thread_id

    async def on_submit(self, interaction: discord.Interaction):
        amount = self.amount.value or "Not specified"
        feedback = self.feedback.value or "No feedback"

        report = active_reports.pop(self.thread_id, None)
        if report:
            embed = discord.Embed(
                title="📋 Payment Confirmation Log",
                description=f"**Reporter:** {interaction.user.mention}\n**Pokémon:** {self.pokemon_name}\n**Stealer:** {self.stealer_name}",
                color=0x2C2C2C
            )
            embed.add_field(name="Amount Received", value=amount, inline=False)
            embed.add_field(name="Feedback about Stealer", value=feedback, inline=False)
            if report.get("proof_link"):
                embed.add_field(name="📎 Trade Proof", value=f"[Click here]({report['proof_link']})", inline=False)
            if report.get("message_link"):
                embed.add_field(name="📎 Evidence", value=f"[Click here]({report['message_link']})", inline=False)
            embed.set_footer(text=f"Report resolved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            await interaction.response.send_message(embed=embed, ephemeral=False)

            config = get_server_config(interaction.guild.id)
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)

            thread = interaction.channel
            await thread.send(f"{EMOJI_LOCK} Report resolved and archived.")
            await thread.edit(archived=True, locked=True)
        else:
            await interaction.response.send_message("Report already resolved.", ephemeral=True)

# ============================================================
# 🔘 REPORT BUTTON & MODAL
# ============================================================
class ReportButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Report", style=discord.ButtonStyle.danger, emoji=EMOJI_REPORT)
    async def callback(self, interaction):
        await interaction.response.send_modal(ReportModal())

class ReportModal(discord.ui.Modal, title="Report Theft"):
    stealer = discord.ui.TextInput(
        label="Stealer (Optional)",
        placeholder="Mention @user or enter their ID (leave blank to auto-detect)",
        required=False
    )
    pokemon = discord.ui.TextInput(
        label="Stolen Pokémon",
        placeholder="e.g., Pikachu",
        required=True
    )
    message_link = discord.ui.TextInput(
        label="Message Link or ID",
        placeholder="Paste the catch command or Pokétwo's response link",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        stealer_input = self.stealer.value.strip()
        pokemon_name = self.pokemon.value.strip().capitalize()
        msg_ref = self.message_link.value.strip()

        stealer = None

        # Try to find stealer from input
        if stealer_input:
            match = re.search(r'<@!?(\d+)>', stealer_input)
            if match:
                stealer_id = int(match.group(1))
                stealer = interaction.guild.get_member(stealer_id)
            elif stealer_input.isdigit():
                stealer = interaction.guild.get_member(int(stealer_input))
            else:
                for member in interaction.guild.members:
                    if stealer_input.lower() in member.name.lower() or stealer_input.lower() in member.display_name.lower():
                        stealer = member
                        break

        # If not found, try extracting from message link
        if not stealer and msg_ref:
            extracted = await extract_stealer_from_link(interaction.guild, msg_ref)
            if extracted:
                stealer = extracted

        if not stealer:
            return await interaction.followup.send(
                f"{EMOJI_WARN} Could not identify the stealer. Please mention them or provide a valid catch command or Pokétwo response link.",
                ephemeral=True
            )

        if stealer.id == interaction.user.id:
            return await interaction.followup.send(f"{EMOJI_WARN} You cannot report yourself.", ephemeral=True)

        await create_report(interaction, interaction.user, stealer, pokemon_name, msg_ref)

# ============================================================
# 📋 COMMANDS
# ============================================================
@bot.command(name="reportpanel")
async def report_panel(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    if config.get("panel_sent", False):
        return await ctx.send(f"{EMOJI_WARN} A report panel already exists in this server.")
    embed = discord.Embed(
        title=f"{EMOJI_REPORT} Report Panel",
        description="Click the **Report** button below to report a Pokémon theft.",
        color=0x2C2C2C
    )
    embed.set_footer(text="Report Handler • Admin-only panel")
    view = discord.ui.View()
    view.add_item(ReportButton())
    await ctx.send(embed=embed, view=view)
    config["panel_sent"] = True
    save_server_config(ctx.guild.id, config)

@bot.command(name="paid")
async def confirm_paid(ctx):
    for thread_id, report in list(active_reports.items()):
        if report["reporter"].id == ctx.author.id and report["status"] == "pending":
            report["paid"] = True
            report["status"] = "resolved"
            await ctx.send(f"{EMOJI_CHECK} Payment confirmed! Closing report...")
            update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
            thread = ctx.guild.get_thread(thread_id)
            if thread:
                await thread.send(f"{EMOJI_CHECK} {ctx.author.mention} confirmed payment. Closing...")
                await thread.edit(archived=True, locked=True)
            active_reports.pop(thread_id, None)
            return
    await ctx.send(f"{EMOJI_WARN} No pending report found for you.")

@bot.command(name="reports")
async def show_reports(ctx, *, user_input: str = None):
    """Show report statistics for a user. Usage: _reports @user or _reports <user_id>."""
    # Cooldown check (skip for developers)
    if ctx.author.id not in DEVELOPER_IDS:
        now = datetime.now().timestamp()
        key = f"{ctx.author.id}:reports"
        last_used = command_cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - (now - last_used))
            await ctx.send(f"{EMOJI_WARN} Please wait {remaining} seconds before using `_reports` again.")
            return
        command_cooldowns[key] = now

    # Determine target user
    target_user = None
    if user_input:
        # Try to parse as mention or ID
        match = re.search(r'<@!?(\d+)>', user_input)
        if match:
            user_id = int(match.group(1))
            target_user = ctx.guild.get_member(user_id)
        elif user_input.isdigit():
            target_user = ctx.guild.get_member(int(user_input))
        else:
            # Try to find by name
            for member in ctx.guild.members:
                if user_input.lower() in member.name.lower() or user_input.lower() in member.display_name.lower():
                    target_user = member
                    break
    else:
        target_user = ctx.author

    if not target_user:
        await ctx.send(f"{EMOJI_WARN} Could not find that user.")
        return

    # Fetch stats
    stats = get_user_stats(target_user.id)
    embed = discord.Embed(
        title=f"📊 Report Statistics for {target_user.display_name}",
        color=0x2C2C2C
    )
    embed.add_field(name="Total Reports", value=stats["total_reports"], inline=True)
    embed.add_field(name="Successful", value=stats["successful_reports"], inline=True)
    embed.add_field(name="Unsuccessful", value=stats["unsuccessful_reports"], inline=True)
    embed.add_field(name="Pokémons Reported", value=", ".join(stats["pokemons_reported"][:10]) or "None", inline=False)
    embed.add_field(name="Last Report", value=stats["last_report"] or "Never", inline=False)
    embed.set_footer(text="Report Handler • Data from HF dataset")

    await ctx.send(embed=embed)

# ============================================================
# 🔄 TRADE MONITORING (on_message)
# ============================================================
@bot.event
async def on_message(message):
    if message.author.id == 716390085896962058:  # Pokétwo
        # Trade Completion Detection (auto-resolve)
        if "Completed trade between" in message.content:
            match = re.search(r'Completed trade between (.+?) and (.+?)\.', message.content)
            if match:
                user1 = match.group(1).strip()
                user2 = match.group(2).strip()
                for thread_id, report in list(active_reports.items()):
                    if report["status"] != "pending":
                        continue
                    stealer = report["stealer"]
                    reporter = report["reporter"]
                    if (stealer.name.lower() in user1.lower() or stealer.name.lower() in user2.lower()) and \
                       (reporter.name.lower() in user1.lower() or reporter.name.lower() in user2.lower()):
                        report["paid"] = True
                        report["status"] = "resolved"
                        report["proof_link"] = message.jump_url  # store proof
                        update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
                        thread = message.guild.get_thread(thread_id)
                        if thread:
                            await thread.send(
                                f"{EMOJI_CHECK} Trade detected between {stealer.mention} and {reporter.mention}!\n"
                                f"**Proof:** {message.jump_url}\n"
                                f"{reporter.mention}, please confirm payment details:"
                            )
                            view = discord.ui.View()
                            view.add_item(ConfirmPaymentButton(thread_id))
                            await thread.send(view=view)
                        break

    # Detect trade add commands (PC / Redeems)
    if "t a" in message.content.lower() or "t add" in message.content.lower():
        for thread_id, report in list(active_reports.items()):
            if report["status"] != "pending":
                continue
            if message.author.id != report["stealer"].id:
                continue
            thread = message.guild.get_thread(thread_id)
            if not thread:
                continue

            # PC amount detection
            pc_match = re.search(r'pc\s*(\d+)', message.content.lower())
            if pc_match:
                amount = int(pc_match.group(1))
                required = get_compensation(report["pokemon"])
                if amount >= required:
                    await thread.send(f"{EMOJI_CHECK} {message.author.mention} added **{amount} PC** (required: {required} PC). Payment complete!")
                    report["paid"] = True
                    report["status"] = "resolved"
                    update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
                    view = discord.ui.View()
                    view.add_item(ConfirmPaymentButton(thread_id))
                    await thread.send(f"{reporter.mention}, please confirm payment details:", view=view)
                else:
                    await thread.send(
                        f"{EMOJI_WARN} {message.author.mention} added **{amount} PC**, but required is **{required} PC**.\n"
                        f"Need **{required - amount} more PC** to complete payment."
                    )
                break

            # Redeem detection
            if "redeems" in message.content.lower():
                if report["pokemon"].lower() == "missingno":
                    await thread.send(f"{EMOJI_WARN} {message.author.mention} added redeems, but **MissingNo** cannot be paid with redeems!")
                else:
                    await thread.send(f"{EMOJI_CHECK} {message.author.mention} added **redeems**! Payment accepted.")
                    report["paid"] = True
                    report["status"] = "resolved"
                    update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
                    view = discord.ui.View()
                    view.add_item(ConfirmPaymentButton(thread_id))
                    await thread.send(f"{reporter.mention}, please confirm payment details:", view=view)
                break

    # Trade confirm detection (logging only)
    if "t c" in message.content.lower() or "trade confirm" in message.content.lower():
        for thread_id, report in list(active_reports.items()):
            if report["status"] != "pending":
                continue
            if message.author.id == report["stealer"].id or message.author.id == report["reporter"].id:
                thread = message.guild.get_thread(thread_id)
                if thread:
                    await thread.send(f"{EMOJI_TRADE} {message.author.mention} confirmed the trade.")
                break

    await bot.process_commands(message)

# ============================================================
# 🔘 CONFIRM PAYMENT BUTTON (for auto-detected trades)
# ============================================================
class ConfirmPaymentButton(discord.ui.Button):
    def __init__(self, thread_id):
        super().__init__(label="Confirm Payment", style=discord.ButtonStyle.success, emoji=EMOJI_CHECK)
        self.thread_id = thread_id

    async def callback(self, interaction: discord.Interaction):
        report = active_reports.get(self.thread_id)
        if not report:
            return await interaction.response.send_message(f"{EMOJI_WARN} Report not found.", ephemeral=True)
        if interaction.user.id != report["reporter"].id:
            return await interaction.response.send_message(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)

        modal = PaymentConfirmationModal(report["pokemon"], report["stealer"].name, self.thread_id)
        await interaction.response.send_modal(modal)

# ============================================================
# 🚀 KEEP-ALIVE
# ============================================================
from flask import Flask
from threading import Thread
app = Flask('')
@app.route('/')
def home():
    return "Report Bot is alive!"
def run():
    port = int(os.environ.get("PORT", 7860))
    app.run(host='0.0.0.0', port=port)
Thread(target=run, daemon=True).start()

# ============================================================
# 🏁 START
# ============================================================
if __name__ == "__main__":
    if BOT_TOKEN and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        bot.run(BOT_TOKEN)
    else:
        print("❌ Set REPORT_BOT_TOKEN.")
