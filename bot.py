import asyncio
import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))

# Configurar intents
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.reactions = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
tree = bot.tree  # Slash command handler

# Dicionário que mapeia mensagens para usuários que reagiram
message_reactions = {}  # { message_id: set(user_id) }

async def check_user_reactions(user_id, guild):
    """Retorna True se o usuário reagiu a todas as mensagens monitoradas."""
    for reactions in message_reactions.values():
        if user_id not in reactions:
            return False
    return True

async def update_user_role(member, guild):
    """Adiciona ou remove o cargo conforme as reações."""
    role = guild.get_role(ROLE_ID)
    if not role:
        return

    if await check_user_reactions(member.id, guild):
        if role not in member.roles:
            await member.add_roles(role)
            print(f'✅ {member} recebeu o cargo {role.name}')
    else:
        if role in member.roles:
            await member.remove_roles(role)
            print(f'❌ {member} perdeu o cargo {role.name} porque deixou de reagir a uma das mensagens monitoradas.')

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Monitorando reações"))
    await initialize_reactions()
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ {len(synced)} comandos de barra sincronizados!')
    except Exception as e:
        print(f'⚠️ Erro ao sincronizar comandos: {e}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)  # Garante que os comandos sejam processados corretamente

@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID or payload.user_id == bot.user.id:
        return

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

@tree.command(name="status", description="Mostra o status das mensagens, reações e roles dos membros", guild=discord.Object(id=GUILD_ID))
async def status(interaction: discord.Interaction):
    """Slash command para mostrar status do rastreamento, incluindo estatísticas de reações e roles."""
    try:
        guild = interaction.guild
        total_msgs = len(message_reactions)
        
        # Força a atualização dos cargos para os membros com o role requisito
        required_role = guild.get_role(REQUIRED_ROLE_ID)
        assigned_role = guild.get_role(ROLE_ID)
        if required_role and assigned_role:
            for member in required_role.members:
                await update_user_role(member, guild)
        
        # Recarrega os roles a partir do cache atualizado
        # (Isso é opcional, pois o objeto 'member' já deve ter os roles atualizados)
        
        embed = discord.Embed(title="📊 Status do Rastreamento", color=discord.Color.blue())
        embed.add_field(name="📌 Mensagens Monitoradas", value=str(total_msgs), inline=False)
        
        # Informações de reações por mensagem
        details = ""
        for msg_id, users in message_reactions.items():
            details += f"📝 ID {msg_id}: {len(users)} reações\n"
        embed.add_field(name="📌 Reações por Mensagem", value=details or "Nenhuma reação registrada", inline=False)
        
        # Lista dos membros com o role requisito e sua contagem de reações
        if required_role:
            membros_info = ""
            for member in required_role.members:
                # Conta quantas mensagens o membro reagiu
                reacted = sum(1 for users in message_reactions.values() if member.id in users)
                membros_info += f"{member.display_name} - {reacted}/{total_msgs}\n"
            membros_info = membros_info or "Nenhum membro com o role requisito encontrado."
        else:
            membros_info = "Role requisito não encontrado."
        embed.add_field(name="👥 Membros com o role requisito:", value=membros_info, inline=False)
        
        # Categorias de roles
        if not required_role:
            required_role_members = set()
        else:
            required_role_members = set(required_role.members)
        if not assigned_role:
            assigned_role_members = set()
        else:
            assigned_role_members = set(assigned_role.members)
        
        # Membros com ambos os roles
        ambos = required_role_members & assigned_role_members
        # Membros com o role requisito e sem o role atribuído
        apenas_requisito = required_role_members - assigned_role_members
        # Membros apenas com o role atribuído (fora do requisito)
        apenas_atribuido = assigned_role_members - required_role_members
        
        def format_members(members_set):
            if not members_set:
                return "Nenhum"
            return "\n".join(member.display_name for member in members_set)
        
        embed.add_field(name="✅ Membros com o role requisito e o role atribuído:", value=format_members(ambos), inline=False)
        embed.add_field(name="❌ Membros com o role requisito e sem o role atribuído:", value=format_members(apenas_requisito), inline=False)
        embed.add_field(name="ℹ️ Membros apenas com o role atribuído:", value=format_members(apenas_atribuido), inline=False)
        
        await interaction.response.send_message(embed=embed)
        print(f'📊 Comando /status solicitado por {interaction.user}')
    except Exception as e:
        print(f"⚠️ Erro no comando /status: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("Ocorreu um erro ao processar o comando.", ephemeral=True)


async def initialize_reactions():
    """Carrega as reações das últimas 100 mensagens."""
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

bot.run(BOT_TOKEN)
