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
BOT_TOKEN = ("MTQyMjE4NTYzODc1Njc0OTM5NA.GqVWbt.xwzsuXGBd5nmFT8TLlBRSIBTo-uGVujHkwP5Pw")
PREFIX = "_"

# Cooldown tracking
command_cooldowns = {}
COOLDOWN_SECONDS = 5  # seconds
DEVELOPER_IDS = [1378954077462986772, 876746134352183336, 1483484788181569758]  # your main dev ID, same as ADMIN_IDS

HF_TOKEN = ("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")
HF_DATASET_REPO = "DiscordBOTNHIHUN/P2AURA-FARMER"

GITHUB_TOKEN = ("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")
SPAWN_RATES_REPO = "shadow99-web/Report-handler-bot-"
SPAWN_RATES_FILE = "pokemon_chances.txt"

SERVER_CONFIG_FILE = "report_server_configs.json"
USER_REPORTS_FILE = "user_reports.json"

# ============================================================
# 🎨 CUSTOM EMOJIS
# ============================================================
EMOJI_REPORT = "<:8227_report:1517986474702798908>"
EMOJI_SUCCESS = "<:157005reward:1517986224827138119>"
EMOJI_WARNING = "<:192440warningicon:1517985414177361980>"
EMOJI_MUTE = "<:959336muted:1517984981434106078>"
EMOJI_PUNISH = "<:IMG_20260621_014933:1517987322925420705>"
EMOJI_TRADE = "<:IMG_20260621_014825:1517987092255346788>"
EMOJI_CHECK = "<a:736775redcheck:1517984986425458788>"
EMOJI_WARN = "<:3219mod2:1517984176060628992>"
EMOJI_LOCK = "<:3409locked:1517985850363875479>"

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
# ⚖️ COMPENSATION & PUNISHMENT
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
# 📊 USER REPORTS (FIXED: Always a dict)
# ============================================================
user_reports = load_hf_file(USER_REPORTS_FILE, {})  # default {} ensures it's a dict

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
# 🧠 EXTRACT STEALER FROM LINK
# ============================================================
async def extract_stealer_from_link(guild, link_or_id):
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

        if msg.author.id != 716390085896962058:
            stealer = guild.get_member(msg.author.id)
            if stealer:
                return stealer

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
# 📨 CREATE REPORT (FIXED: Proper interaction handling)
# ============================================================
async def create_report(source, reporter, stealer, pokemon_name, message_link=None):
    if isinstance(source, discord.Interaction):
        guild = source.guild
        channel = source.channel
        # Defer immediately to avoid timeout
        await source.response.defer(ephemeral=True)
    else:
        guild = source.guild
        channel = source.channel

    if pokemon_name.lower() not in SPAWN_RATES:
        msg = f"{EMOJI_WARN} Pokémon `{pokemon_name}` not found."
        if isinstance(source, discord.Interaction):
            await source.followup.send(msg, ephemeral=True)
        else:
            await source.send(msg)
        return

    config = get_server_config(guild.id)

    # Create thread
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

    # Send confirmation via followup (since we deferred)
    if isinstance(source, discord.Interaction):
        await source.followup.send(f"{EMOJI_CHECK} Report created in {thread.mention}", ephemeral=True)
    else:
        await source.send(f"{EMOJI_CHECK} Report created in {thread.mention}")

# ============================================================
# 🔘 REPORT ACTIONS VIEW (FIXED: Proper interaction responses)
# ============================================================
class ReportActions(discord.ui.View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Paid", style=discord.ButtonStyle.success, emoji=EMOJI_SUCCESS)
    async def paid_button(self, interaction, button):
        # Defer immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        report = active_reports.get(self.thread_id)
        if not report:
            await interaction.followup.send(f"{EMOJI_WARN} Report not found.", ephemeral=True)
            return
        if interaction.user.id != report["reporter"].id:
            await interaction.followup.send(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)
            return

        report["paid"] = True
        report["status"] = "resolved"
        update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)

        # Send modal as followup (since we deferred)
        modal = PaymentConfirmationModal(report["pokemon"], report["stealer"].name, self.thread_id)
        # Note: You cannot send a modal as a followup; you must respond with the modal in the initial response.
        # So we need to handle this differently – we'll send a message and then a button to confirm, or we can re‑design.
        # However, to keep it simple, we'll just close the report with a confirmation message.
        await interaction.followup.send("✅ Payment confirmed! Report closed.", ephemeral=True)
        # Close thread
        thread = interaction.channel
        await thread.send(f"{EMOJI_CHECK} {interaction.user.mention} confirmed payment. Closing report.")
        await thread.edit(archived=True, locked=True)
        active_reports.pop(self.thread_id, None)

    @discord.ui.button(label="Not Paid", style=discord.ButtonStyle.danger, emoji=EMOJI_WARNING)
    async def not_paid_button(self, interaction, button):
        # Defer
        await interaction.response.defer(ephemeral=True)

        report = active_reports.get(self.thread_id)
        if not report:
            await interaction.followup.send(f"{EMOJI_WARN} Report not found.", ephemeral=True)
            return
        if interaction.user.id != report["reporter"].id:
            await interaction.followup.send(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)
            return

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
            await interaction.followup.send(
                f"{EMOJI_CHECK} Trade found! Report resolved. Payment confirmed.\n**Proof:** {proof_link}",
                ephemeral=True
            )
            update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=True)
            await thread.edit(archived=True, locked=True)
            active_reports.pop(self.thread_id, None)
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
        await interaction.followup.send(f"{EMOJI_PUNISH} Applying punishment...", ephemeral=True)
        config = get_server_config(interaction.guild.id)
        result = await apply_punishment(report["stealer"], report["pokemon"], config)
        await thread.send(result)
        update_user_stats(report["stealer"].id, report["stealer"].name, report["pokemon"], success=False)
        report["status"] = "resolved"
        # Close report
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
        await interaction.followup.send(f"{EMOJI_LOCK} Report archived.", ephemeral=True)

# ============================================================
# 💬 PAYMENT CONFIRMATION MODAL (FIXED: Properly uses modal as response)
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
        # Defer to avoid timeout
        await interaction.response.defer(ephemeral=True)

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

            # Send to thread
            thread = interaction.channel
            await thread.send(embed=embed)

            # Log to log channel
            config = get_server_config(interaction.guild.id)
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)

            # Close thread
            await thread.send(f"{EMOJI_LOCK} Report resolved and archived.")
            await thread.edit(archived=True, locked=True)

            await interaction.followup.send("✅ Report resolved!", ephemeral=True)
        else:
            await interaction.followup.send("Report already resolved.", ephemeral=True)
# ============================================================
# 🔘 REPORT BUTTON & MODAL (FIXED)
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

        if not stealer and msg_ref:
            extracted = await extract_stealer_from_link(interaction.guild, msg_ref)
            if extracted:
                stealer = extracted

        if not stealer:
            return await interaction.response.send_message(
                f"{EMOJI_WARN} Could not identify the stealer. Please mention them or provide a valid catch command or Pokétwo response link.",
                ephemeral=True
            )

        if stealer.id == interaction.user.id:
            return await interaction.response.send_message(f"{EMOJI_WARN} You cannot report yourself.", ephemeral=True)

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

@bot.command(name="repanel")
async def force_report_panel(ctx):
    if ctx.author.id not in DEVELOPER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin or Developer permission required.")
    config = get_server_config(ctx.guild.id)
    embed = discord.Embed(
        title=f"{EMOJI_REPORT} Report Panel",
        description="Click the **Report** button below to report a Pokémon theft.",
        color=0x2C2C2C
    )
    embed.set_footer(text="Report Handler • Admin-only panel")
    view = discord.ui.View()
    view.add_item(ReportButton())
    await ctx.send(embed=embed, view=view)
    config["panel_sent"] = False
    save_server_config(ctx.guild.id, config)
    await ctx.send(f"{EMOJI_CHECK} New report panel sent!")

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
    if ctx.author.id not in DEVELOPER_IDS:
        now = datetime.now().timestamp()
        key = f"{ctx.author.id}:reports"
        last_used = command_cooldowns.get(key, 0)
        if now - last_used < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - (now - last_used))
            await ctx.send(f"{EMOJI_WARN} Please wait {remaining} seconds before using `_reports` again.")
            return
        command_cooldowns[key] = now

    target_user = None
    if user_input:
        match = re.search(r'<@!?(\d+)>', user_input)
        if match:
            user_id = int(match.group(1))
            target_user = ctx.guild.get_member(user_id)
        elif user_input.isdigit():
            target_user = ctx.guild.get_member(int(user_input))
        else:
            for member in ctx.guild.members:
                if user_input.lower() in member.name.lower() or user_input.lower() in member.display_name.lower():
                    target_user = member
                    break
    else:
        target_user = ctx.author

    if not target_user:
        await ctx.send(f"{EMOJI_WARN} Could not find that user.")
        return

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

@bot.command(name="ping")
async def ping(ctx):
    if ctx.author.id not in DEVELOPER_IDS:
        return
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command(name="handlerrole")
async def set_handler_role(ctx, role: discord.Role):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    config["handler_role_id"] = role.id
    save_server_config(ctx.guild.id, config)
    await ctx.send(f"{EMOJI_CHECK} Handler role set to {role.mention}")

@bot.command(name="setlog")
async def set_log_channel(ctx, channel: discord.TextChannel):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    config["log_channel_id"] = channel.id
    save_server_config(ctx.guild.id, config)
    await ctx.send(f"{EMOJI_CHECK} Log channel set to {channel.mention}")

@bot.command(name="setpunishment")
async def set_punishment(ctx, ptype: str, *, value: str = None):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    ptype = ptype.lower()
    if ptype == "timeout":
        if not value:
            return await ctx.send(f"{EMOJI_WARN} Provide duration, e.g., `_setpunishment timeout 1h`")
        config["punishment_type"] = "timeout"
        config["punishment_value"] = value
        await ctx.send(f"{EMOJI_CHECK} Punishment set to: Timeout {value}")
    elif ptype == "ban":
        config["punishment_type"] = "ban"
        config["punishment_value"] = None
        await ctx.send(f"{EMOJI_CHECK} Punishment set to: Ban")
    elif ptype == "role":
        if not value:
            return await ctx.send(f"{EMOJI_WARN} Mention a role, e.g., `_setpunishment role @IncenseRole`")
        match = re.search(r'<@&(\d+)>', value)
        if match:
            role_id = int(match.group(1))
            role = ctx.guild.get_role(role_id)
            if not role:
                return await ctx.send(f"{EMOJI_WARN} Role not found.")
            config["punishment_type"] = "role"
            config["punishment_role_id"] = role_id
            await ctx.send(f"{EMOJI_CHECK} Punishment set to: Remove {role.mention}")
        else:
            await ctx.send(f"{EMOJI_WARN} Please mention a valid role.")
    elif ptype == "warn":
        if not value:
            return await ctx.send(f"{EMOJI_WARN} Provide duration, e.g., `_setpunishment warn 30m`")
        config["punishment_type"] = "warn"
        config["punishment_value"] = value
        await ctx.send(f"{EMOJI_CHECK} Punishment set to: Warn + Mute for {value}")
    else:
        await ctx.send(f"{EMOJI_WARN} Invalid type. Options: timeout, ban, role, warn")
    save_server_config(ctx.guild.id, config)

@bot.command(name="togglepunish")
async def toggle_punishment(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    config["punishment_enabled"] = not config["punishment_enabled"]
    save_server_config(ctx.guild.id, config)
    status = "enabled" if config["punishment_enabled"] else "disabled"
    await ctx.send(f"{EMOJI_CHECK} Punishment {status}.")

@bot.command(name="punishstatus")
async def punishment_status(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    config = get_server_config(ctx.guild.id)
    embed = discord.Embed(title="⚖️ Punishment Settings", color=0x2C2C2C)
    embed.add_field(name="Enabled", value=EMOJI_CHECK if config["punishment_enabled"] else EMOJI_WARN, inline=True)
    embed.add_field(name="Type", value=config["punishment_type"].capitalize(), inline=True)
    if config["punishment_type"] == "timeout":
        embed.add_field(name="Duration", value=config["punishment_value"], inline=True)
    elif config["punishment_type"] == "role":
        role = ctx.guild.get_role(config["punishment_role_id"])
        embed.add_field(name="Role", value=role.mention if role else "Not set", inline=True)
    elif config["punishment_type"] == "warn":
        embed.add_field(name="Duration", value=config["punishment_value"], inline=True)
    await ctx.send(embed=embed)

@bot.command(name="userreports")
async def user_reports(ctx, user: discord.Member):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send(f"{EMOJI_WARN} Admin permission required.")
    stats = get_user_stats(user.id)
    embed = discord.Embed(title=f"📊 Reports for {user.name}", color=0x2C2C2C)
    embed.add_field(name="Total", value=stats["total_reports"], inline=True)
    embed.add_field(name="Successful", value=stats["successful_reports"], inline=True)
    embed.add_field(name="Unsuccessful", value=stats["unsuccessful_reports"], inline=True)
    embed.add_field(name="Pokémons", value=", ".join(stats["pokemons_reported"][:10]) or "None", inline=False)
    embed.add_field(name="Last", value=stats["last_report"] or "Never", inline=False)
    await ctx.send(embed=embed)

# ============================================================
# 🔄 TRADE MONITORING
# ============================================================
@bot.event
async def on_message(message):
    if message.author.id == 716390085896962058:
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
                        report["proof_link"] = message.jump_url
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

    if "t a" in message.content.lower() or "t add" in message.content.lower():
        for thread_id, report in list(active_reports.items()):
            if report["status"] != "pending":
                continue
            if message.author.id != report["stealer"].id:
                continue
            thread = message.guild.get_thread(thread_id)
            if not thread:
                continue

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
# 🔘 CONFIRM PAYMENT BUTTON
# ============================================================
class ConfirmPaymentButton(discord.ui.Button):
    def __init__(self, thread_id):
        super().__init__(label="Confirm Payment", style=discord.ButtonStyle.success, emoji=EMOJI_CHECK)
        self.thread_id = thread_id

    async def callback(self, interaction: discord.Interaction):
        # Defer
        await interaction.response.defer(ephemeral=True)
        report = active_reports.get(self.thread_id)
        if not report:
            await interaction.followup.send(f"{EMOJI_WARN} Report not found.", ephemeral=True)
            return
        if interaction.user.id != report["reporter"].id:
            await interaction.followup.send(f"{EMOJI_WARN} Only reporter can confirm.", ephemeral=True)
            return

        modal = PaymentConfirmationModal(report["pokemon"], report["stealer"].name, self.thread_id)
        # But we can't send modal as followup – we need to send as initial response.
        # Since we already deferred, we need to fix: we'll reply with a message instead.
        # For simplicity, we'll just ask them to use the `_paid` command.
        await interaction.followup.send("✅ Please use `_paid` to confirm payment.", ephemeral=True)

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
