import asyncio
import os
import sqlite3
from datetime import datetime, timezone
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))

# ---------- DATABASE STORAGE ----------
DB_PATH = "message_counts.sqlite3"

def get_year_month(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_counts (
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            year_month TEXT    NOT NULL,
            count      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, year_month)
        );
    """)
    conn.commit()
    conn.close()

def increment_message_count(guild_id: int, user_id: int, year_month: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO message_counts (guild_id, user_id, year_month, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(guild_id, user_id, year_month)
        DO UPDATE SET count = count + 1;
    """, (guild_id, user_id, year_month))
    conn.commit()
    conn.close()

def decrement_message_count(guild_id: int, user_id: int, year_month: str):
    """Decrements the user's message count, keeping a minimum of 0."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            UPDATE message_counts 
            SET count = MAX(0, count - 1)
            WHERE guild_id = ? AND user_id = ? AND year_month = ?;
        """, (guild_id, user_id, year_month))
        conn.commit()
    except sqlite3.Error as e:
        print(f"⚠️ Erro no banco de dados ao decrementar: {e}")
    finally:
        conn.close()

def get_counts_for_month(guild_id: int, year_month: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, count
        FROM message_counts
        WHERE guild_id = ? AND year_month = ?;
    """, (guild_id, year_month))
    rows = cur.fetchall()
    conn.close()
    return {user_id: cnt for (user_id, cnt) in rows}
# ---------------------------------------------------

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
            print(f'❌ {member.display_name} perdeu o cargo {role.name} (sem cargo requisito)')
        return

    if await check_user_reactions(member.id):
        if role not in member.roles:
            await member.add_roles(role)
            print(f'✅ {member.display_name} recebeu o cargo {role.name}')
    else:
        if role in member.roles:
            await member.remove_roles(role)
            print(f'❌ {member.display_name} perdeu o cargo {role.name}')

async def update_all_roles():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f'⚠️ Guild com ID {GUILD_ID} não encontrada!')
        return
    for member in guild.members:
        await update_user_role(member)

async def perform_full_sync():
    """Resets DB counts for the server and rebuilds everything from message history."""
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f'⚠️ Guild com ID {GUILD_ID} não encontrada para sync!')
        return

    print('🔄 Iniciando resync completo do servidor...')
    
    # 1. Clear database for this specific guild to avoid duplicate counts
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM message_counts WHERE guild_id = ?", (GUILD_ID,))
    conn.commit()
    conn.close()

    db_batch = {}
    message_reactions.clear()
    
    # 2. Iterate through all text channels to rebuild counts
    # (And map reactions if it's the specific CHANNEL_ID)
    for text_channel in guild.text_channels:
        try:
            async for message in text_channel.history(limit=None):
                # Count ALL messages in the server for the database
                if not message.author.bot:
                    ym = get_year_month(message.created_at)
                    key = (guild.id, message.author.id, ym)
                    db_batch[key] = db_batch.get(key, 0) + 1
                    
                # Map reactions ONLY if it's the monitored channel
                if text_channel.id == CHANNEL_ID:
                    message_reactions[message.id] = set()
                    for reaction in message.reactions:
                        async for user in reaction.users():
                            if not user.bot:
                                message_reactions[message.id].add(user.id)
        except discord.Forbidden:
            continue # Skip channels the bot doesn't have permission to read
            
    # 3. Batch insert the newly calculated counts into the database (Fast)
    if db_batch:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for (g_id, u_id, ym), cnt in db_batch.items():
            cur.execute("""
                INSERT INTO message_counts (guild_id, user_id, year_month, count)
                VALUES (?, ?, ?, ?)
            """, (g_id, u_id, ym, cnt))
        conn.commit()
        conn.close()
        
    print(f'✅ Resync concluído! Contadores atualizados e {len(message_reactions)} mensagens monitoradas para reações.')
    
    # 4. Update roles based on the newly synced data
    await update_all_roles()

# ---------- HOUSEKEEPING ----------
@tasks.loop(hours=24)
async def purge_old_months():
    """Keep only the last 12 months of data to keep the DB compact."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cutoff = f"{now.year - 1}-{now.month:02d}"  # 12 months ago
        cur.execute("DELETE FROM message_counts WHERE year_month < ?;", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ [purge_old_months] Error: {e}")

@purge_old_months.before_loop
async def before_purge():
    await bot.wait_until_ready()

async def handle_on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Notes"))

    init_db()
    if not purge_old_months.is_running():
        purge_old_months.start()

    print("Guilds conectadas:")
    for g in bot.guilds:
        print(f"- {g.name} (ID: {g.id})")

    # Perform the full sync every time the bot starts
    await perform_full_sync()

    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f'✅ {len(synced)} comandos de barra sincronizados!')
    except Exception as e:
        print(f'⚠️ Erro ao sincronizar comandos: {e}')

# ---------- EVENTOS ----------
@bot.event
async def on_ready():
    await handle_on_ready()

@bot.event
async def on_message(message: discord.Message):
    # Track messages dynamically as they come in
    if message.guild is not None and not message.author.bot:
        ym = get_year_month()
        increment_message_count(message.guild.id, message.author.id, ym)

    await handle_new_message(message)
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction_add(payload)

@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction_remove(payload)

@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    # Process reaction tracking removal
    await handle_message_delete(payload)
    
    # Process database message decrement (Real-time syncing)
    if payload.cached_message and not payload.cached_message.author.bot:
        ym = get_year_month(payload.cached_message.created_at)
        decrement_message_count(payload.guild_id, payload.cached_message.author.id, ym)

# --- HANDLERS EXISTENTES ---
async def handle_reaction_add(payload):
    if payload.channel_id != CHANNEL_ID or payload.user_id == bot.user.id:
        return
    message_reactions.setdefault(payload.message_id, set()).add(payload.user_id)
    print(f'➕ Usuário {payload.user_id} adicionou reação na mensagem {payload.message_id}')
    guild = bot.get_guild(payload.guild_id)
    if not guild:
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
        return
    member = guild.get_member(payload.user_id)
    if member:
        await update_user_role(member)

async def handle_new_message(message):
    if message.guild and message.channel.id == CHANNEL_ID and not message.author.bot:
        message_reactions[message.id] = set()
        print(f'📩 Nova mensagem adicionada para monitorização: {message.id}')

async def handle_message_delete(payload):
    if payload.channel_id != CHANNEL_ID:
        return
    if payload.message_id in message_reactions:
        del message_reactions[payload.message_id]
        print(f'🗑️ Mensagem {payload.message_id} foi apagada e removida do rastreamento de reações.')
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    for member in guild.members:
        await update_user_role(member)

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

# --- COMANDOS ---
@tree.command(name="status", description="Mostra o status das mensagens, reações e roles dos membros", guild=discord.Object(id=GUILD_ID))
async def status(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
        guild = interaction.guild
        total_msgs = len(message_reactions)
        required_role = guild.get_role(REQUIRED_ROLE_ID)
        assigned_role = guild.get_role(ROLE_ID)

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

        embed1 = discord.Embed(title="📊 Status Geral", color=discord.Color.green())
        embed1.add_field(name="📌 Mensagens Monitoradas", value=str(total_msgs), inline=False)

        details = "\n".join(f"📝 ID {msg_id}: {len(users)} reações" for msg_id, users in message_reactions.items()) or "Nenhuma reação registrada"
        embed2 = discord.Embed(title="📨 Reações por Mensagem", description=details, color=discord.Color.blurple())

        pages = [embed6, embed3, embed4, embed5, embed1, embed2]
        view = StatusPaginator(pages, interaction.user)
        await interaction.followup.send(embed=pages[0], view=view)
    except Exception as e:
        print(f"⚠️ Erro inesperado: {e}")
        try:
            await interaction.followup.send("❌ Ocorreu um erro ao processar o status.")
        except Exception:
            pass

@tree.command(name="atividade", description="Mostre os membros o menor número de mensagens em um mês.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    limit="Quantos membros listar (1-100, padrão 10).",
    role="Inclui apenas membros com este Role (opcional).",
    month="Mês a mostrar em AAAA-MM (padrão: mês atual).",
    include_bots="Incluir contas de bot (padrão: False).",
    public="Publicar publicamente (padrão: False)."
)
async def least_active(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 100] = 10,
    role: discord.Role | None = None,
    month: str | None = None,
    include_bots: bool = False,
    public: bool = False
):
    await interaction.response.defer(ephemeral=not public)

    guild = interaction.guild
    if guild is None:
        return await interaction.followup.send("Use this command in a server.", ephemeral=True)

    if month:
        try:
            dt = datetime.strptime(month, "%Y-%m")
            ym = dt.strftime("%Y-%m")
        except ValueError:
            return await interaction.followup.send("Invalid month. Use `YYYY-MM` (e.g., `2025-11`).", ephemeral=True)
    else:
        ym = get_year_month()

    counts = get_counts_for_month(guild.id, ym)

    if not guild.chunked:
        await guild.chunk(cache=True)

    members = list(guild.members)
    if role:
        members = [m for m in members if role in m.roles]
    if not include_bots:
        members = [m for m in members if not m.bot]

    scored = [(m, counts.get(m.id, 0)) for m in members]
    if not scored:
        return await interaction.followup.send("No members matched your filters.", ephemeral=not public)

    scored.sort(key=lambda t: (t[1], t[0].display_name.lower()))
    scored = scored[:limit]

    lines = [f"**{i}.** {member.mention} — `{c}` message{'s' if c != 1 else ''}"
             for i, (member, c) in enumerate(scored, start=1)]

    embed = discord.Embed(
        title=f"Least Active — {guild.name}",
        description="\n".join(lines),
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Month: {ym} • Include bots: {include_bots} • Role: {role.name if role else 'Any'}")
    await interaction.followup.send(embed=embed, ephemeral=not public)

@tree.command(name="mensagens", description="Mostra a sua contagem de mensagens para o mês atual.", guild=discord.Object(id=GUILD_ID))
async def my_messages(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("Use this in a server.", ephemeral=True)
    ym = get_year_month()
    c = get_counts_for_month(guild.id, ym).get(interaction.user.id, 0)
    await interaction.response.send_message(f"Mandaste **{c}** mensagens em **{ym}**.", ephemeral=True)

# --- INICIAR BOT ---
bot.run(BOT_TOKEN)
