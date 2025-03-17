import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    print(f'Nova mensagem detectada: {message.id}')

    guild = message.guild
    role = guild.get_role(ROLE_ID)

    if role:
        for member in guild.members:
            if role in member.roles:
                await member.remove_roles(role)
                print(f'Role removido de {member.name}')
    else:
        print(f'Role com ID {ROLE_ID} não encontrado')

    await bot.process_commands(message)

async def check_reactions_and_apply_role(member, channel, role):
    messages = list(await channel.history(limit=None).flatten()) # Corrigido aqui!
    has_reacted_to_all = True
    for msg in messages:
        if not discord.utils.get(msg.reactions, lambda r: discord.utils.get(r.users(), id=member.id)):
            if msg.author != bot.user: #ignora as mensagens do bot
                has_reacted_to_all = False
                break

    if has_reacted_to_all:
        await member.add_roles(role)
        print(f'Role reatribuído a {member.name} (reações verificadas)')

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    channel = bot.get_channel(CHANNEL_ID)
    member = channel.guild.get_member(payload.user_id)
    role = channel.guild.get_role(ROLE_ID)
    required_role = discord.utils.get(member.roles, id=REQUIRED_ROLE_ID)

    if member and bot.user != member:
        if required_role:
            await check_reactions_and_apply_role(member, channel, role)
        else:
            print(f'{member.name} não possui o role necessário')

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    channel = bot.get_channel(CHANNEL_ID)
    member = channel.guild.get_member(payload.user_id)
    role = channel.guild.get_role(ROLE_ID)

    if member and bot.user != member:
        if role in member.roles:
            await member.remove_roles(role)
            print(f'Role removido de {member.name} (reação removida)')

@bot.event
async def on_member_update(before, after):
    if REQUIRED_ROLE_ID in [role.id for role in after.roles] and REQUIRED_ROLE_ID not in [role.id for role in before.roles]:
        channel = bot.get_channel(CHANNEL_ID)
        role = after.guild.get_role(ROLE_ID)
        await check_reactions_and_apply_role(after, channel, role)

bot.run(TOKEN)
