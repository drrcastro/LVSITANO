import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))

# Configurar intents – lembre de habilitar "MESSAGE CONTENT INTENT" no portal do Discord
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.reactions = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário que mapeia cada mensagem (ID) para o conjunto de IDs dos usuários que reagiram
message_reactions = {}  # { message_id: set(user_id) }

async def check_user_reactions(user_id, guild):
    """Retorna True se o usuário reagiu a todas as mensagens monitoradas."""
    for reactions in message_reactions.values():
        if user_id not in reactions:
            return False
    return True

async def update_user_role(member, guild):
    """Adiciona ou remove o cargo conforme se o usuário reagiu a todas as mensagens."""
    role = guild.get_role(ROLE_ID)
    if not role:
        return

    if await check_user_reactions(member.id, guild):
        if role not in member.roles:
            try:
                await member.add_roles(role)
                print(f'✅ {member} recebeu o cargo {role.name}')
            except Exception as e:
                print(f'⚠️ Erro ao adicionar cargo a {member}: {e}')
    else:
        if role in member.roles:
            try:
                await member.remove_roles(role)
                print(f'❌ {member} perdeu o cargo {role.name}')
            except Exception as e:
                print(f'⚠️ Erro ao remover cargo de {member}: {e}')

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    await initialize_reactions()

@bot.event
async def on_message(message):
    # Processa apenas mensagens do canal monitorado e ignora mensagens de bots
    if message.channel.id != CHANNEL_ID or message.author.bot:
        await bot.process_commands(message)
        return

    print(f'Nova mensagem postada: {message.id} no canal {message.channel.id}')
    # Registra a nova mensagem com um conjunto vazio de reações
    message_reactions[message.id] = set()

    # Ao inserir uma nova mensagem, atualiza os cargos de todos os membros
    guild = message.guild
    for member in guild.members:
        if not member.bot:
            await update_user_role(member, guild)

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID or payload.user_id == bot.user.id:
        return

    # Atualiza o dicionário: adiciona o usuário à mensagem
    message_reactions.setdefault(payload.message_id, set()).add(payload.user_id)
    print(f'➕ Usuário {payload.user_id} adicionou reação na mensagem {payload.message_id}')

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if member:
        await update_user_role(member, guild)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    if payload.message_id in message_reactions:
        message_reactions[payload.message_id].discard(payload.user_id)
    print(f'➖ Usuário {payload.user_id} removeu reação da mensagem {payload.message_id}')

    member = guild.get_member(payload.user_id)
    if member:
        await update_user_role(member, guild)

@bot.event
async def on_raw_message_delete(payload):
    # Este evento é disparado mesmo para mensagens não cacheadas
    if payload.channel_id != CHANNEL_ID:
        return

    if payload.message_id in message_reactions:
        del message_reactions[payload.message_id]
        print(f'🗑️ Mensagem {payload.message_id} removida do rastreamento.')

    # Após a remoção, atualiza os cargos para todos os membros da guilda
    guild = bot.get_guild(payload.guild_id)
    for member in guild.members:
        if not member.bot:
            await update_user_role(member, guild)

async def initialize_reactions():
    """Carrega as reações das últimas 100 mensagens do canal e atualiza os cargos."""
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    channel = guild.get_channel(CHANNEL_ID)
    if not channel:
        print(f'⚠️ Canal com ID {CHANNEL_ID} não encontrado!')
        return

    print('Inicializando rastreamento de mensagens e reações...')
    message_reactions.clear()

    async for message in channel.history(limit=100):
        message_reactions[message.id] = set()
        for reaction in message.reactions:
            async for user in reaction.users():
                if not user.bot:
                    message_reactions[message.id].add(user.id)

    print(f'✅ Rastreamento inicializado: {len(message_reactions)} mensagens registradas.')

    # Atualiza os cargos para TODOS os membros da guilda
    for member in guild.members:
        if not member.bot:
            await update_user_role(member, guild)

bot.run(BOT_TOKEN)
