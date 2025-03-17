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

message_reactions = {}

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

    if message.channel.id == CHANNEL_ID and not message.author.bot:
        message_reactions[message.id] = set()

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    print(f'Reação adicionada por {user.name} em {reaction.message.id}')
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        if reaction.message.id not in message_reactions:
            message_reactions[reaction.message.id] = set()

        message_reactions[reaction.message.id].add(user.id)

        required_role = discord.utils.get(user.guild.roles, id=REQUIRED_ROLE_ID)
        print(f'Role de requisito encontrado: {required_role}')
        if required_role:
            print(f'{user.name} tem o role de requisito')
            if all(user.id in reactions for reactions in message_reactions.values()):
                print(f'{user.name} reagiu a todas as mensagens')
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role not in user.roles:
                    await user.add_roles(role)
                    print(f"{user.name} recebeu o cargo {role.name}.")
        else:
            print(f'{user.name} não possui o role necessário')

@bot.event
async def on_reaction_remove(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        if reaction.message.id in message_reactions:
            message_reactions[reaction.message.id].discard(user.id)

        if not all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role in user.roles:
                await user.remove_roles(role)
                print(f"{user.name} perdeu o cargo {role.name}.")

@bot.event
async def on_member_update(before, after):
    if REQUIRED_ROLE_ID in [role.id for role in after.roles] and REQUIRED_ROLE_ID not in [role.id for role in before.roles]:
        user = after
        required_role = discord.utils.get(user.guild.roles, id=REQUIRED_ROLE_ID)
        if required_role:
            if all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role not in user.roles:
                    await user.add_roles(role)
                    print(f"{user.name} recebeu o cargo {role.name} (ao receber o role de requisição).")

bot.run(TOKEN)
