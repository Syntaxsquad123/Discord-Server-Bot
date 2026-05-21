import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import sqlite3
import time
import asyncio
from datetime import datetime, timedelta
from collections import deque, defaultdict


load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    reason TEXT,
    moderator TEXT,
    time TEXT
)
""")

conn.commit()


joins = deque()
spam_tracker = defaultdict(list)

BAD_WORDS = ["kanker", "fuck", "shit"]  # aanpassen


async def log(guild, title, desc, color=discord.Color.blurple()):

    channel = discord.utils.get(guild.text_channels, name="mod-logs")
    if not channel:
        return

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )

    await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Online als {bot.user}")
    await bot.tree.sync()


@bot.event
async def on_member_join(member):

    channel = discord.utils.get(member.guild.text_channels, name="welkom")
    if channel:
        await channel.send(f"👋 Welkom {member.mention}")

    await log(member.guild, "📥 Join", str(member), discord.Color.green())

    now = datetime.utcnow()
    joins.append(now)

    while joins and now - joins[0] > timedelta(seconds=10):
        joins.popleft()

    if len(joins) >= 5:

        await log(member.guild, "🚨 RAID", "Server locked", discord.Color.red())

        for c in member.guild.text_channels:
            try:
                await c.set_permissions(member.guild.default_role, send_messages=False)
            except:
                pass



@bot.event
async def on_member_remove(member):
    await log(member.guild, "📤 Leave", str(member))


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    content = message.content.lower()

    for word in BAD_WORDS:
        if word in content:
            await message.delete()
            await message.channel.send(
                f"⚠️ {message.author.mention} geen slechte taal!",
                delete_after=3
            )
            await log(message.guild, "🚫 Bad Word", str(message.author))
            return

    user_id = message.author.id
    now = time.time()

    spam_tracker[user_id].append(now)
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if now - t < 5]

    if len(spam_tracker[user_id]) >= 5:
        await message.channel.send(f"⚠️ {message.author.mention} stop met spammen!")
        await log(message.guild, "🚨 Spam", str(message.author))

    await bot.process_commands(message)


@bot.tree.command(name="warn")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):

    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("❌ Geen permissie", ephemeral=True)

    cursor.execute("""
        INSERT INTO warnings (user_id, reason, moderator, time)
        VALUES (?, ?, ?, ?)
    """, (
        str(member.id),
        reason,
        str(interaction.user),
        str(datetime.utcnow())
    ))

    conn.commit()

    await interaction.response.send_message(f"⚠️ {member} warned")

    await log(interaction.guild, "⚠️ Warn", f"{member} | {reason}")


@bot.tree.command(name="warnings")
async def warnings(interaction: discord.Interaction, member: discord.Member):

    cursor.execute("SELECT reason, moderator, time FROM warnings WHERE user_id = ?", (str(member.id),))
    rows = cursor.fetchall()

    if not rows:
        return await interaction.response.send_message("Geen warnings")

    text = ""
    for r in rows:
        text += f"⚠️ {r[0]} | 👮 {r[1]} | 🕒 {r[2]}\n"

    embed = discord.Embed(title=f"Warnings {member}", description=text)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden"):

    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("❌ Geen permissie", ephemeral=True)

    await member.kick(reason=reason)

    await interaction.response.send_message(f"👢 {member} gekickt")
    await log(interaction.guild, "Kick", f"{member} | {reason}")

@bot.tree.command(name="ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Geen reden"):

    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("❌ Geen permissie", ephemeral=True)

    await member.ban(reason=reason)

    await interaction.response.send_message(f"🔨 {member} geband")
    await log(interaction.guild, "Ban", f"{member} | {reason}")



@bot.tree.command(name="mute")
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int):

    role = discord.utils.get(interaction.guild.roles, name="Muted")

    if not role:
        role = await interaction.guild.create_role(name="Muted")

        for c in interaction.guild.channels:
            await c.set_permissions(role, send_messages=False)

    await member.add_roles(role)

    await interaction.response.send_message(f"🔇 {member} gemute")

    await log(interaction.guild, "Mute", f"{member} | {minutes} min")

    asyncio.create_task(unmute_later(member, role, minutes * 60))

async def unmute_later(member, role, seconds):
    await asyncio.sleep(seconds)
    await member.remove_roles(role)


@bot.tree.command(name="ticket")
async def ticket(interaction: discord.Interaction):

    channel = await interaction.guild.create_text_channel(
        name=f"ticket-{interaction.user.name}"
    )

    await channel.send(f"🎫 Ticket van {interaction.user.mention}")

    await interaction.response.send_message(f"Ticket: {channel.mention}", ephemeral=True)


@bot.tree.command(name="close")
async def close(interaction: discord.Interaction):

    if not interaction.channel.name.startswith("ticket-"):
        return await interaction.response.send_message("Geen ticket", ephemeral=True)

    await interaction.channel.delete()


bot.run(TOKEN)