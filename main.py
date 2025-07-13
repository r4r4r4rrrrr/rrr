import json
import discord
from discord.ext import commands
import asyncio
import random
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

OWNER_ID = 739048881651712010
ACTIVATION_FILE = "activated_servers.json"

# Load activated servers
try:
    with open(ACTIVATION_FILE, "r") as f:
        activated_servers = json.load(f)
except:
    activated_servers = []

giveaway_entries = {}
giveaway_messages = {}
giveaway_winners = {}
rerolled_history = {}
giveaway_ended_embeds = {}
active_setups = {}
active_countdowns = {}

reaction_emoji = "<a:3544giveaway:1393878076659728587>"
reaction_emoji_name = "3544giveaway"
arrow = "<:Screenshot_20250713_135426remove:1393870928068218940>"
light_blue = discord.Color.from_rgb(173, 216, 230)

def parse_duration(duration_str):
    units = {"d": 86400, "hr": 3600, "min": 60}
    total_seconds = 0
    for part in duration_str.lower().split():
        for key in units:
            if part.endswith(key):
                value = int(part[:-len(key)])
                total_seconds += value * units[key]
                break
    if total_seconds <= 0:
        raise commands.BadArgument("Duration must be greater than 0.")
    return total_seconds

def format_time(seconds):
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d}d {h}hr {m}min" if d else f"{h}hr {m}min" if h else f"{m}min" if m else "Less than a minute"

@bot.command()
@commands.has_permissions(administrator=True)
async def help(ctx):
    if str(ctx.guild.id) not in activated_servers:
        return
    embed = discord.Embed(title="📍 Giveaway Bot Commands", color=light_blue)
    embed.add_field(name="#1  **$giveaway**", value="- Trigger giveaway setup. Includes: Channel, Prize-pool, Winners-count, Time, Host.", inline=False)
    embed.add_field(name="#2  **$giveawaycancel [message_id]**", value="- Cancel an ongoing giveaway", inline=False)
    embed.add_field(name="#3  **$reroll [message_id] @winners**", value="- Reroll selected winners", inline=False)
    embed.add_field(name="#4  **$exit**", value="- Exit giveaway setup", inline=False)
   
    embed.set_footer(text="Admin-only commands.")
    await ctx.send(embed=embed)

@bot.command(name="giveaway")
@commands.has_permissions(administrator=True)
async def giveaway(ctx):
    if str(ctx.guild.id) not in activated_servers:
        return await ctx.send(embed=discord.Embed(description=" This bot is deactivated in this server.", color=discord.Color.red()))
    if ctx.message.content.strip() != "$giveaway":
        return  # Only allow exact "$giveaway"

    if ctx.guild.id in active_setups:
        return await ctx.send(embed=discord.Embed(description="A giveaway setup is already in progress.", color=discord.Color.orange()))

    setup_task = asyncio.current_task()
    active_setups[ctx.guild.id] = setup_task

    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    steps = [
        ("1 | Mention the channel to host the giveaway", "channel"),
        ("2 | Prize-pool of the giveaway?", lambda m: m.content),
        ("3 | No of winners?", "int"),
        ("4 | Duration of the giveaway? (Eg. 1d 2hr 30min)", "duration"),
        ("5 | Host? (mention/name)", lambda m: m.content)
    ]
    answers = []

    try:
        for question, parser in steps:
            while True:
                q_msg = await ctx.send(embed=discord.Embed(description=f"**{question}**", color=light_blue))
                try:
                    response = await bot.wait_for("message", timeout=120.0, check=check)
                except asyncio.TimeoutError:
                    await q_msg.delete()
                    active_setups.pop(ctx.guild.id, None)
                    return await ctx.send(embed=discord.Embed(description=" Timed out. Giveaway setup canceled.", color=discord.Color.red()))

                content = response.content.strip().lower()
                if content == "$exit":
                    await q_msg.delete()
                    await response.delete()
                    active_setups.pop(ctx.guild.id, None)
                    return await ctx.send(embed=discord.Embed(description=" Giveaway setup exited.", color=discord.Color.red()), delete_after=1)

                try:
                    if parser == "int":
                        value = int(response.content)
                    elif parser == "duration":
                        value = parse_duration(response.content)
                    elif parser == "channel":
                        value = response.channel_mentions[0] if response.channel_mentions else None
                        if not value:
                            await q_msg.delete()
                            await response.delete()
                            await ctx.send(embed=discord.Embed(description=" Please mention a valid channel.", color=discord.Color.red()), delete_after=3)
                            continue
                    elif callable(parser):
                        value = parser(response)

                    answers.append(value)
                    await q_msg.delete()
                    await response.delete()
                    break
                except:
                    await q_msg.delete()
                    await response.delete()
                    await ctx.send(embed=discord.Embed(description="Invalid input. Try again.", color=discord.Color.red()), delete_after=3)

        active_setups.pop(ctx.guild.id, None)
        channel, prize, winners, duration, host_tag = answers
        time_display = format_time(duration)
        emoji = "<a:outputonlinegiftools:1393594291452117113>"
        centered_title = f"{emoji} {prize} {emoji}"

        embed = discord.Embed(
            title=centered_title,
            description=f"{arrow} **Ends in:** {time_display}\n{arrow} **Winners:** {winners}\n{arrow} **Hosted by:** {host_tag}",
            color=light_blue
        )
        embed.set_footer(text="React with the emoji below to enter!")
        msg = await channel.send(embed=embed)
        await msg.add_reaction(discord.PartialEmoji(name="3544giveaway", animated=True, id=1393878076659728587))

        giveaway_entries[msg.id] = []
        giveaway_messages[msg.id] = msg

        async def countdown():
            last_time = ""
            for remaining in range(duration, 0, -1):
                await asyncio.sleep(1)
                t = format_time(remaining)
                if t != last_time:
                    last_time = t
                    updated_embed = discord.Embed(
                        title=centered_title,
                        description=f"{arrow} **Ends in:** {t}\n{arrow} **Winners:** {winners}\n{arrow} **Hosted by:** {host_tag}",
                        color=light_blue
                    )
                    updated_embed.set_footer(text="React with the emoji below to enter!")
                    await msg.edit(embed=updated_embed)

        countdown_task = asyncio.create_task(countdown())
        active_countdowns[ctx.guild.id] = countdown_task
        try:
            await countdown_task
        except asyncio.CancelledError:
            return
        finally:
            active_countdowns.pop(ctx.guild.id, None)

        now = datetime.now(pytz.timezone("Asia/Kolkata"))
        valid_entries = [ctx.guild.get_member(uid) for uid in giveaway_entries[msg.id] if ctx.guild.get_member(uid)]

        if len(valid_entries) < winners:
            final_embed = discord.Embed(
                title=centered_title,
                description=f"{arrow} **Ended on:** {now.strftime('%d %b %Y, %I:%M %p IST')}\n{arrow} **Winners:** Not enough entries.\n{arrow} **Hosted by:** {host_tag}",
                color=light_blue
            )
            final_embed.set_footer(text="Giveaway Ended")
            await msg.edit(embed=final_embed)
            return await channel.send(f"**Not enough entries to select winners.**", reference=msg)

        chosen = random.sample(valid_entries, winners)
        giveaway_winners[msg.id] = [m.id for m in chosen]
        mentions = ", ".join(m.mention for m in chosen)

        final_embed = discord.Embed(
            title=centered_title,
            description=f"{arrow} **Ended on:** {now.strftime('%d %b %Y, %I:%M %p IST')}\n{arrow} **Winners:** {mentions}\n{arrow} **Hosted by:** {host_tag}",
            color=light_blue
        )
        final_embed.set_footer(text="Giveaway Ended")
        await msg.edit(embed=final_embed)
        await channel.send(f"🎉 Congratulations {mentions}! You’ve won `{prize}`!", reference=msg)

        giveaway_ended_embeds[msg.id] = final_embed
    except asyncio.CancelledError:
        return

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    msg = reaction.message
    if msg.id not in giveaway_messages:
        return
    if msg.embeds and "Giveaway Ended" in msg.embeds[0].footer.text:
        try: await reaction.remove(user)
        except: pass
        return
    if str(reaction.emoji) != reaction_emoji:
        try: await reaction.remove(user)
        except: pass
        return
    if user.id not in giveaway_entries[msg.id]:
        giveaway_entries[msg.id].append(user.id)

@bot.command()
@commands.has_permissions(administrator=True)
async def giveawaycancel(ctx, message_id: int = None):
    if str(ctx.guild.id) not in activated_servers:
        return
    if not message_id:
        return await ctx.send(embed=discord.Embed(description="Provide a valid giveaway message ID.", color=discord.Color.red()))
    msg = giveaway_messages.get(message_id)
    if not msg:
        return await ctx.send(embed=discord.Embed(description="Giveaway not found.", color=discord.Color.red()))
    try: await msg.delete()
    except: pass
    giveaway_entries.pop(message_id, None)
    giveaway_messages.pop(message_id, None)
    giveaway_winners.pop(message_id, None)
    giveaway_ended_embeds.pop(message_id, None)
    rerolled_history.pop(message_id, None)
    await ctx.send(embed=discord.Embed(description="Giveaway canceled successfully.", color=discord.Color.red()))

@bot.command()
@commands.has_permissions(administrator=True)
async def reroll(ctx, message_id: int):
    if str(ctx.guild.id) not in activated_servers:
        return

    mentions = ctx.message.mentions
    msg = giveaway_messages.get(message_id)
    entries = giveaway_entries.get(message_id, [])
    prev_winner_ids = giveaway_winners.get(message_id, [])

    if not mentions or not msg or not prev_winner_ids:
        return await ctx.send("Invalid reroll request.")

    rerolled_ids = [m.id for m in mentions]

    if not all(uid in prev_winner_ids for uid in rerolled_ids):
        return await ctx.send("Only current winners can be rerolled.")

    history = rerolled_history.get(message_id, [])
    history.extend(rerolled_ids)
    rerolled_history[message_id] = list(set(history))

    eligible = [uid for uid in entries if uid not in prev_winner_ids and uid not in rerolled_history[message_id]]
    if len(eligible) < len(rerolled_ids):
        return await ctx.send("Not enough eligible participants to reroll.")

    new_winner_ids = random.sample(eligible, len(rerolled_ids))

    updated_winner_ids = []
    new_idx = 0
    for uid in prev_winner_ids:
        if uid in rerolled_ids:
            updated_winner_ids.append(new_winner_ids[new_idx])
            new_idx += 1
        else:
            updated_winner_ids.append(uid)

    giveaway_winners[message_id] = updated_winner_ids

    new_mentions = [ctx.guild.get_member(uid).mention for uid in updated_winner_ids]
    embed = giveaway_ended_embeds.get(message_id)
    if not embed:
        return await ctx.send("Final giveaway state not found.")

    # Update embed description
    lines = embed.description.split("\n")
    for i, line in enumerate(lines):
        if "**Winners:**" in line:
            lines[i] = f"{arrow} **Winners:** {', '.join(new_mentions)}"

    updated_embed = discord.Embed(title=embed.title, description="\n".join(lines), color=light_blue)
    updated_embed.set_footer(text="Giveaway Ended")
    await msg.edit(embed=updated_embed)

    # Always send update in original giveaway channel, as a reply
    await msg.channel.send(
        f"🎉 Updated Final Winners: {', '.join(new_mentions)}",
        reference=msg
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def deactivate(ctx):
    if str(ctx.guild.id) not in activated_servers:
        return await ctx.send("Bot is already deactivated in this server.")
    activated_servers.remove(str(ctx.guild.id))
    with open(ACTIVATION_FILE, "w") as f:
        json.dump(activated_servers, f)
    await ctx.send("Bot has been deactivated in this server.")

@bot.command()
@commands.has_permissions(administrator=True)
async def reactivate(ctx):
    if str(ctx.guild.id) in activated_servers:
        return await ctx.send("Bot is already active.")
    activated_servers.append(str(ctx.guild.id))
    with open(ACTIVATION_FILE, "w") as f:
        json.dump(activated_servers, f)
    await ctx.send("Bot has been reactivated.")

@bot.event
async def on_guild_join(guild):
    if str(guild.id) not in activated_servers:
        activated_servers.append(str(guild.id))
        with open(ACTIVATION_FILE, "w") as f:
            json.dump(activated_servers, f)

# Flask keep-alive
app = Flask('')

@app.route('/')
def home():
    return "Giveaway Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run).start()

keep_alive()
bot.run(os.getenv("TOKEN"))
