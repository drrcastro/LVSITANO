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
        await interaction.response.defer()
        guild = interaction.guild
        total_msgs = len(message_reactions)
        
        required_role = guild.get_role(REQUIRED_ROLE_ID)
        assigned_role = guild.get_role(ROLE_ID)
        if required_role and assigned_role:
            for member in required_role.members:
                await update_user_role(member, guild)
        
        embed = discord.Embed(title="📊 Status do Rastreamento", color=discord.Color.blue())
        embed.add_field(name="📌 Mensagens Monitoradas", value=str(total_msgs), inline=False)
        
        details = ""
        for msg_id, users in message_reactions.items():
            details += f"📝 ID {msg_id}: {len(users)} reações\n"
        embed.add_field(name="📌 Reações por Mensagem", value=details or "Nenhuma reação registrada", inline=False)
        
        required_role_members = set(required_role.members) if required_role else set()
        assigned_role_members = set(assigned_role.members) if assigned_role else set()
        
        ambos = required_role_members & assigned_role_members
        apenas_requisito = required_role_members - assigned_role_members
        apenas_atribuido = assigned_role_members - required_role_members
        
        def format_members(title, members_set):
            count = len(members_set)
            members_list = "\n".join(member.display_name for member in sorted(members_set, key=lambda m: m.display_name.lower())) if members_set else "Nenhum"
            return f"{title} ({count})", members_list

        # Em seguida, ao adicionar os campos:
        campo_ambos_title, campo_ambos_value = format_members(f"Membros ({required_role.name}) e ({assigned_role.name})", ambos)
        campo_apenas_requisito_title, campo_apenas_requisito_value = format_members(f"Membros ({required_role.name}) sem ({assigned_role.name})", apenas_requisito)
        campo_apenas_atribuido_title, campo_apenas_atribuido_value = format_members(f"Membros apenas com ({assigned_role.name})", apenas_atribuido)

        embed.add_field(name=campo_ambos_title, value=campo_ambos_value, inline=False)
        embed.add_field(name=campo_apenas_requisito_title, value=campo_apenas_requisito_value, inline=False)
        embed.add_field(name=campo_apenas_atribuido_title, value=campo_apenas_atribuido_value, inline=False)

        
        await interaction.followup.send(embed=embed)
        print(f'📊 Comando /status solicitado por {interaction.user}')
    except Exception as e:
        print(f"⚠️ Erro no comando /status: {e}")
        await interaction.followup.send("Ocorreu um erro ao processar o comando.", ephemeral=True)

async def initialize_reactions():
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
