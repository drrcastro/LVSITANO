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

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    channel = bot.get_channel(CHANNEL_ID)

    user = bot.get_user(payload.user_id)
    member = channel.guild.get_member(payload.user_id)

    if member and bot.user != user:
        required_role = discord.utils.get(member.roles, id=REQUIRED_ROLE_ID)
        if required_role:
            role_to_reapply = channel.guild.get_role(ROLE_ID)
            if role_to_reapply:
                await member.add_roles(role_to_reapply)
                print(f'Role reatribuído a {member.name}')
            else:
                print(f'Role com ID {ROLE_ID} não encontrado')
        else:
            print(f'{member.name} não possui o role necessário')

bot.run(TOKEN)
