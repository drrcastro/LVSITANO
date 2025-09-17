import asyncio
import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.reactions = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
tree = bot.tree
message_reactions = {}

# --- FUNÇÕES AUXILIARES ---

async def check_user_reactions(user_id):
    for reactions in message_reactions.values():
        if user_id not in reactions:
            return False
    return True

async def update_user_role(member):
    guild = member.guild
    role = guild.get_role(ROLE_ID)
    required_role = guild.get_role(REQUIRED_ROLE_ID)
    if not role or not required_role:
        return

    if required_role not in member.roles:
        if role in member.roles:
            await member.remove_roles(role)
            print(f'❌ {member} perdeu o cargo {role.name} (sem cargo requisito)')
        return

    if await check_user_reactions(member.id):
        if role not in member.roles:
            await member.add_roles(role)
            print(f'✅ {member} recebeu o cargo {role.name}')
    else:
        if role in member.roles:
            await member.remove_roles(role)
            print(f'❌ {member} perdeu o cargo {role.name}')

async def initialize_reactions():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f'⚠️ Guild com ID {GUILD_ID} não encontrada!')
        return
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

async def update_all_roles():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f'⚠️ Guild com ID {GUILD_ID} não encontrada!')
        return
    for member in guild.members:
        await update_user_role(member)

async def handle_on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Notes"))
    print("Guilds conectadas:")
    for g in bot.guilds:
        print(f"- {g.name} (ID: {g.id})")
    await initialize_reactions()
    await update_all_roles()

    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ {len(synced)} comandos de barra sincronizados!')
    except Exception as e:
        print(f'⚠️ Erro ao sincronizar comandos: {e}')

async def handle_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID or payload.user_id == bot.user.id:
        return

    message_reactions.setdefault(payload.message_id, set()).add(payload.user_id)
    print(f'➕ Usuário {payload.user_id} adicionou reação na mensagem {payload.message_id}')

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        print(f'⚠️ Guild com ID {payload.guild_id} não encontrada!')
        return
    member = guild.get_member(payload.user_id)
    if member:
        await update_user_role(member)

async def handle_reaction_remove(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    if payload.message_id in message_reactions:
        message_reactions[payload.message_id].discard(payload.user_id)
        print(f'➖ Usuário {payload.user_id} removeu reação da mensagem {payload.message_id}')

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        print(f'⚠️ Guild com ID {payload.guild_id} não encontrada!')
        return
    member = guild.get_member(payload.user_id)
    if member:
        await update_user_role(member)

async def handle_new_message(message):
    if message.channel.id == CHANNEL_ID and not message.author.bot:
        message_reactions[message.id] = set()
        print(f'📩 Nova mensagem adicionada para monitorização: {message.id}')

async def handle_message_delete(payload):
    if payload.channel_id != CHANNEL_ID:
        return

    if payload.message_id in message_reactions:
        del message_reactions[payload.message_id]
        print(f'🗑️ Mensagem {payload.message_id} foi apagada e removida do rastreamento.')

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        print(f'⚠️ Guild com ID {payload.guild_id} não encontrada!')
        return
    for member in guild.members:
        await update_user_role(member)

# --- EVENTOS ---

@bot.event
async def on_ready():
    await handle_on_ready()

@bot.event
async def on_message(message):
    await handle_new_message(message)
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction_add(payload)

@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction_remove(payload)

@bot.event
async def on_raw_message_delete(payload):
    await handle_message_delete(payload)

# --- VIEW PAGINADA PARA /STATUS ---

class StatusPaginator(View):
    def __init__(self, pages, author):
        super().__init__(timeout=120)
        self.pages = pages
        self.author = author
        self.index = 0

    async def update_message(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Apenas o autor do comando pode usar os botões.", ephemeral=True)
        self.index = (self.index - 1) % len(self.pages)
        await self.update_message(interaction)

    @discord.ui.button(label="Próximo ➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Apenas o autor do comando pode usar os botões.", ephemeral=True)
        self.index = (self.index + 1) % len(self.pages)
        await self.update_message(interaction)

# --- COMANDO /STATUS ---

@tree.command(name="status", description="Mostra o status das mensagens, reações e roles dos membros", guild=discord.Object(id=GUILD_ID))
async def status(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
        guild = interaction.guild
        total_msgs = len(message_reactions)
        required_role = guild.get_role(REQUIRED_ROLE_ID)
        assigned_role = guild.get_role(ROLE_ID)

        # Página 1 (será exibida primeiro na ordem pedida): Comparação de roles
        required_role_members = set(required_role.members) if required_role else set()
        assigned_role_members = set(assigned_role.members) if assigned_role else set()

        ambos = required_role_members & assigned_role_members
        apenas_requisito = required_role_members - assigned_role_members
        apenas_atribuido = assigned_role_members - required_role_members

        def format_members(title, members_set):
            count = len(members_set)
            members_list = "\n".join(sorted((member.display_name for member in members_set), key=str.lower)) if members_set else "Nenhum"
            return title, f"{count} membros:\n{members_list}"

        embed6 = discord.Embed(title="📋 Comparação de Cargos", color=discord.Color.purple())
        for title, members in [
            format_members("✅ Com ambos os roles", ambos),
            format_members(f"❌ Apenas {required_role.name if required_role else 'N/D'}", apenas_requisito),
            format_members(f"ℹ️ Apenas {assigned_role.name if assigned_role else 'N/D'}", apenas_atribuido)
        ]:
            embed6.add_field(name=title, value=members, inline=False)

        # Páginas seguintes: progresso dos grupos
        villain_role = discord.utils.get(guild.roles, name="Villain")
        robot_role = discord.utils.get(guild.roles, name="Robot")

        def format_progress(members):
            return "\n".join(
                f"{'✅' if assigned_role in member.roles else '❌'} {member.display_name} - "
                f"{sum(1 for users in message_reactions.values() if member.id in users)}/{total_msgs}"
                for member in sorted(members, key=lambda m: m.display_name.lower())
            ) or "Nenhum membro encontrado."

        villains = [m for m in guild.members if villain_role in m.roles] if villain_role else []
        robots = [m for m in guild.members if robot_role in m.roles] if robot_role else []
        restantes = [m for m in guild.members if (villain_role not in m.roles and robot_role not in m.roles)]

        embed3 = discord.Embed(title="👥 Progresso - Villains", description=format_progress(villains), color=discord.Color.red())
        embed4 = discord.Embed(title="🤖 Progresso - Robots", description=format_progress(robots), color=discord.Color.blue())
        embed5 = discord.Embed(title="👤 Progresso - Restantes", description=format_progress(restantes), color=discord.Color.orange())

        # Status geral
        embed1 = discord.Embed(title="📊 Status Geral", color=discord.Color.green())
        embed1.add_field(name="📌 Mensagens Monitoradas", value=str(total_msgs), inline=False)

        # Reações por mensagem
        details = "\n".join(f"📜 ID {msg_id}: {len(users)} reações" for msg_id, users in message_reactions.items()) or "Nenhuma reação registrada"
        embed2 = discord.Embed(title="📨 Reações por Mensagem", description=details, color=discord.Color.blurple())

        # Ordem final das páginas
        pages = [embed6, embed3, embed4, embed5, embed1, embed2]
        view = StatusPaginator(pages, interaction.user)
        await interaction.followup.send(embed=pages[0], view=view)

    except Exception as e:
        print(f"⚠️ Erro inesperado: {e}")
        try:
            await interaction.followup.send("❌ Ocorreu um erro ao processar o status.")
        except Exception:
            pass

# --- INICIAR BOT ---
bot.run(BOT_TOKEN)
