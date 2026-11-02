import asyncio
import logging
import os
from datetime import datetime, timezone

import aiosqlite
import discord
from discord import app_commands
from discord.ext import tasks
from discord.ui import View
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lvsitano")


# ---------- CONFIGURAÇÃO ----------
def _env_int(name: str, default: int | None = None, required: bool = True) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        if required:
            raise SystemExit(f"❌ Variável de ambiente em falta: {name}")
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"❌ A variável de ambiente {name} tem de ser um número inteiro (valor atual: {raw!r})")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "sim", "on")


BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ Variável de ambiente em falta: DISCORD_BOT_TOKEN")

ROLE_ID = _env_int("DISCORD_ROLE_ID")                    # Note Reader
REQUIRED_ROLE_ID = _env_int("DISCORD_REQUIRE_ROLE_ID")   # Villain
CHANNEL_ID = _env_int("DISCORD_CHANNEL_ID")              # canal #notas
GUILD_ID = _env_int("DISCORD_GUILD_ID")
# Opcional: se não estiver definido, procura um role chamado "Robot" (comportamento antigo).
ROBOT_ROLE_ID = _env_int("DISCORD_ROBOT_ROLE_ID", required=False)
# Número de notas mais recentes que contam (0 = todas as notas do canal).
NOTES_LIMIT: int | None = _env_int("DISCORD_NOTES_LIMIT", default=100, required=False) or None
# Se true, o autor de uma nota conta automaticamente como tendo reagido à própria nota.
AUTHOR_AUTO_READ = _env_bool("DISCORD_AUTHOR_AUTO_READ", default=False)
# Caminho da base de dados (aponta para um volume persistente se o alojamento tiver disco efémero).
DB_PATH = os.getenv("DB_PATH", "message_counts.sqlite3")

GUILD_OBJ = discord.Object(id=GUILD_ID)
EMBED_DESC_LIMIT = 4000  # limite do Discord é 4096; deixamos margem
NOTE_MESSAGE_TYPES = (discord.MessageType.default, discord.MessageType.reply)


# ---------- CONTAGEM DE MENSAGENS (SQLite assíncrono) ----------
def get_year_month(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m")


def months_ago(n: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    total = now.year * 12 + (now.month - 1) - n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


class MessageCountDB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def open(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS message_counts (
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                year_month TEXT    NOT NULL,
                count      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, year_month)
            );
        """)
        await self.conn.commit()

    async def close(self):
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def increment(self, guild_id: int, user_id: int, year_month: str):
        await self.conn.execute("""
            INSERT INTO message_counts (guild_id, user_id, year_month, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, year_month)
            DO UPDATE SET count = count + 1;
        """, (guild_id, user_id, year_month))
        await self.conn.commit()

    async def decrement(self, guild_id: int, user_id: int, year_month: str):
        await self.conn.execute("""
            UPDATE message_counts SET count = MAX(count - 1, 0)
            WHERE guild_id = ? AND user_id = ? AND year_month = ?;
        """, (guild_id, user_id, year_month))
        await self.conn.commit()

    async def counts_for_month(self, guild_id: int, year_month: str) -> dict[int, int]:
        async with self.conn.execute("""
            SELECT user_id, count FROM message_counts
            WHERE guild_id = ? AND year_month = ?;
        """, (guild_id, year_month)) as cur:
            rows = await cur.fetchall()
        return {user_id: cnt for (user_id, cnt) in rows}

    async def purge_before(self, cutoff_year_month: str):
        await self.conn.execute("DELETE FROM message_counts WHERE year_month < ?;", (cutoff_year_month,))
        await self.conn.commit()


db = MessageCountDB(DB_PATH)


# ---------- BOT ----------
class LvsitanoBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # necessário para ver os roles de todos os membros
        # message_content não é necessário: o bot nunca lê o conteúdo das mensagens.
        super().__init__(
            intents=intents,
            activity=discord.Activity(type=discord.ActivityType.watching, name="the Notes"),
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Corre uma única vez por processo (ao contrário do on_ready, que repete em cada reconexão).
        await db.open()
        purge_old_months.start()
        try:
            synced = await self.tree.sync(guild=GUILD_OBJ)
            log.info("✅ %d comandos de barra sincronizados.", len(synced))
        except discord.HTTPException:
            log.exception("⚠️ Erro ao sincronizar comandos")

    async def close(self):
        await db.close()
        await super().close()


bot = LvsitanoBot()


# ---------- ESTADO DAS NOTAS ----------
# {message_id: set(user_ids)} ordenado da nota mais antiga para a mais recente.
note_reactions: dict[int, set[int]] = {}
# Só há alterações de roles depois de uma sincronização bem-sucedida (evita dar o role a todos
# quando o canal não é encontrado ou o histórico falha).
notes_ready = False
# Serializa todas as alterações de estado e de roles (eventos, sincronização).
state_lock = asyncio.Lock()


def is_note(message: discord.Message) -> bool:
    """Só mensagens normais de humanos contam como nota (ignora bots, webhooks e mensagens de sistema)."""
    return not message.author.bot and message.type in NOTE_MESSAGE_TYPES


def jump_url(message_id: int) -> str:
    return f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{message_id}"


async def collect_reactors(message: discord.Message) -> set[int]:
    """Devolve os IDs de todos os humanos que reagiram à mensagem (com qualquer emoji)."""
    users: set[int] = set()
    for reaction in message.reactions:
        if getattr(reaction, "normal_count", reaction.count):
            async for user in reaction.users():
                if not user.bot:
                    users.add(user.id)
        if getattr(reaction, "burst_count", 0):  # super reações
            async for user in reaction.users(type=discord.ReactionType.burst):
                if not user.bot:
                    users.add(user.id)
    if AUTHOR_AUTO_READ:
        users.add(message.author.id)
    return users


async def get_notes_channel(guild: discord.Guild) -> discord.abc.Messageable | None:
    channel = guild.get_channel(CHANNEL_ID)
    if channel is None:
        try:
            channel = await guild.fetch_channel(CHANNEL_ID)
        except discord.HTTPException:
            return None
    return channel


def trim_window():
    """Mantém apenas as NOTES_LIMIT notas mais recentes (igual no arranque e em tempo real)."""
    if NOTES_LIMIT is None:
        return
    while len(note_reactions) > NOTES_LIMIT:
        del note_reactions[next(iter(note_reactions))]


async def resync_notes(guild: discord.Guild) -> bool:
    """Relê o canal de notas. Chamar com state_lock adquirido."""
    global notes_ready
    notes_ready = False
    channel = await get_notes_channel(guild)
    if channel is None:
        log.error("⚠️ Canal com ID %s não encontrado! Alterações de roles suspensas.", CHANNEL_ID)
        return False

    log.info("A sincronizar notas e reações...")
    collected: list[tuple[int, set[int]]] = []
    try:
        async for message in channel.history(limit=None):
            if not is_note(message):
                continue
            collected.append((message.id, await collect_reactors(message)))
            if NOTES_LIMIT is not None and len(collected) >= NOTES_LIMIT:
                break
    except discord.HTTPException:
        log.exception("⚠️ Erro ao ler o histórico do canal de notas. Alterações de roles suspensas.")
        return False

    collected.reverse()  # mais antiga -> mais recente
    note_reactions.clear()
    note_reactions.update(collected)
    notes_ready = True
    log.info("✅ Sincronização concluída: %d notas monitorizadas.", len(note_reactions))
    return True


async def refresh_note(guild: discord.Guild, message_id: int):
    """Volta a ler as reações de uma nota (usado quando reações são removidas/limpas)."""
    channel = await get_notes_channel(guild)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        note_reactions.pop(message_id, None)
        return
    except discord.HTTPException:
        log.exception("⚠️ Erro ao reler a nota %s", message_id)
        return
    if message_id in note_reactions:
        note_reactions[message_id] = await collect_reactors(message)


# ---------- LÓGICA DE ROLES ----------
def has_read_all(user_id: int) -> bool:
    # Sem notas monitorizadas ninguém se qualifica (antes, uma lista vazia dava o role a toda a gente).
    if not note_reactions:
        return False
    return all(user_id in users for users in note_reactions.values())


async def update_user_role(member: discord.Member):
    """Chamar com state_lock adquirido."""
    if not notes_ready:
        return
    guild = member.guild
    role = guild.get_role(ROLE_ID)
    required_role = guild.get_role(REQUIRED_ROLE_ID)
    if role is None or required_role is None:
        log.warning("⚠️ Role %s ou %s não encontrado no servidor.", ROLE_ID, REQUIRED_ROLE_ID)
        return

    should_have = required_role in member.roles and has_read_all(member.id)
    has = role in member.roles
    try:
        if should_have and not has:
            await member.add_roles(role, reason="Reagiu a todas as notas")
            log.info("✅ %s recebeu o cargo %s", member, role.name)
        elif has and not should_have:
            reason = "Tem notas por reagir" if required_role in member.roles else f"Sem o cargo {required_role.name}"
            await member.remove_roles(role, reason=reason)
            log.info("❌ %s perdeu o cargo %s (%s)", member, role.name, reason)
    except discord.Forbidden:
        log.error("⛔ Sem permissão para alterar o cargo de %s. Confirma que o role do bot está acima de %s.",
                  member, role.name)
    except discord.HTTPException:
        log.exception("⚠️ Erro ao alterar o cargo de %s", member)


async def update_all_roles(guild: discord.Guild):
    """Avalia apenas quem pode mudar de estado (tem Villain ou Note Reader). Chamar com state_lock."""
    role = guild.get_role(ROLE_ID)
    required_role = guild.get_role(REQUIRED_ROLE_ID)
    candidates: set[discord.Member] = set()
    if role:
        candidates.update(role.members)
    if required_role:
        candidates.update(required_role.members)
    for member in candidates:
        await update_user_role(member)


# ---------- TAREFA DE LIMPEZA ----------
@tasks.loop(hours=24)
async def purge_old_months():
    """Mantém os últimos 12 meses (mês atual + 11 anteriores)."""
    try:
        await db.purge_before(months_ago(11))
    except Exception:
        log.exception("[purge_old_months] Erro")


@purge_old_months.before_loop
async def before_purge():
    await bot.wait_until_ready()


# ---------- EVENTOS ----------
@bot.event
async def on_ready():
    log.info("✅ Bot conectado como %s", bot.user)
    for g in bot.guilds:
        log.info("Guild: %s (ID: %s)", g.name, g.id)
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        log.error("⚠️ Guild com ID %s não encontrada!", GUILD_ID)
        return
    # on_ready repete após reconexões: voltamos a sincronizar para apanhar eventos perdidos
    # enquanto o bot esteve desligado (os comandos só são sincronizados uma vez, no setup_hook).
    async with state_lock:
        if await resync_notes(guild):
            await update_all_roles(guild)


@bot.event
async def on_message(message: discord.Message):
    if message.guild is None or message.author.bot or message.is_system():
        return
    try:
        await db.increment(message.guild.id, message.author.id, get_year_month(message.created_at))
    except Exception:
        log.exception("⚠️ Erro ao contar mensagem")

    if message.guild.id == GUILD_ID and message.channel.id == CHANNEL_ID and is_note(message):
        async with state_lock:
            if not notes_ready:
                return
            note_reactions[message.id] = {message.author.id} if AUTHOR_AUTO_READ else set()
            trim_window()
            log.info("📩 Nova nota monitorizada: %s", message.id)
            # Quem já tinha o Note Reader perde-o até reagir à nova nota.
            await update_all_roles(message.guild)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id != GUILD_ID or payload.channel_id != CHANNEL_ID:
        return
    if payload.member is None or payload.member.bot:
        return
    async with state_lock:
        users = note_reactions.get(payload.message_id)
        if users is None:
            return  # mensagem não monitorizada (antiga, de bot ou de sistema)
        users.add(payload.user_id)
        log.info("➕ %s reagiu à nota %s", payload.member, payload.message_id)
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        await update_user_role(member or payload.member)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.guild_id != GUILD_ID or payload.channel_id != CHANNEL_ID:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    async with state_lock:
        if payload.message_id not in note_reactions:
            return
        # Relê a mensagem: o utilizador pode ainda ter outra reação (outro emoji) na mesma nota.
        await refresh_note(guild, payload.message_id)
        log.info("➖ Utilizador %s removeu uma reação da nota %s", payload.user_id, payload.message_id)
        member = guild.get_member(payload.user_id)
        if member:
            await update_user_role(member)


@bot.event
async def on_raw_reaction_clear(payload: discord.RawReactionClearEvent):
    await _handle_reaction_clear(payload.guild_id, payload.channel_id, payload.message_id)


@bot.event
async def on_raw_reaction_clear_emoji(payload: discord.RawReactionClearEmojiEvent):
    await _handle_reaction_clear(payload.guild_id, payload.channel_id, payload.message_id)


async def _handle_reaction_clear(guild_id: int | None, channel_id: int, message_id: int):
    if guild_id != GUILD_ID or channel_id != CHANNEL_ID:
        return
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    async with state_lock:
        if message_id not in note_reactions:
            return
        await refresh_note(guild, message_id)
        log.info("🧹 Reações limpas na nota %s", message_id)
        await update_all_roles(guild)


async def _decrement_deleted(messages):
    for msg in messages:
        if msg.guild is None or msg.author.bot or msg.is_system():
            continue
        try:
            await db.decrement(msg.guild.id, msg.author.id, get_year_month(msg.created_at))
        except Exception:
            log.exception("⚠️ Erro ao descontar mensagem apagada")


async def _handle_notes_deleted(guild_id: int | None, channel_id: int, message_ids: set[int]):
    if guild_id != GUILD_ID or channel_id != CHANNEL_ID:
        return
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    async with state_lock:
        tracked = message_ids & note_reactions.keys()
        if not tracked:
            return
        window_was_full = NOTES_LIMIT is not None and len(note_reactions) >= NOTES_LIMIT
        for mid in tracked:
            del note_reactions[mid]
        log.info("🗑️ %d nota(s) apagada(s) e removida(s) da monitorização.", len(tracked))
        if window_was_full:
            # Notas mais antigas entram agora na janela das NOTES_LIMIT mais recentes.
            if not await resync_notes(guild):
                return
        await update_all_roles(guild)


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    # Só é possível descontar se a mensagem estava em cache (o Discord não envia o autor).
    if payload.cached_message is not None:
        await _decrement_deleted([payload.cached_message])
    await _handle_notes_deleted(payload.guild_id, payload.channel_id, {payload.message_id})


@bot.event
async def on_raw_bulk_message_delete(payload: discord.RawBulkMessageDeleteEvent):
    await _decrement_deleted(payload.cached_messages)
    await _handle_notes_deleted(payload.guild_id, payload.channel_id, set(payload.message_ids))


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.guild.id != GUILD_ID:
        return
    changed = {r.id for r in before.roles} ^ {r.id for r in after.roles}
    if ROLE_ID in changed or REQUIRED_ROLE_ID in changed:
        async with state_lock:
            await update_user_role(after)


# ---------- PAGINAÇÃO / EMBEDS ----------
def chunk_lines(lines: list[str], limit: int = EMBED_DESC_LIMIT) -> list[str]:
    chunks, current, size = [], [], 0
    for line in lines:
        if len(line) > limit:
            line = line[: limit - 1] + "…"
        extra = len(line) + (1 if current else 0)
        if current and size + extra > limit:
            chunks.append("\n".join(current))
            current, size = [line], len(line)
        else:
            current.append(line)
            size += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_embeds(title: str, lines: list[str], color: discord.Color, empty_text: str) -> list[discord.Embed]:
    chunks = chunk_lines(lines) or [empty_text]
    embeds = []
    for i, chunk in enumerate(chunks, start=1):
        suffix = f" ({i}/{len(chunks)})" if len(chunks) > 1 else ""
        embeds.append(discord.Embed(title=f"{title}{suffix}", description=chunk, color=color))
    return embeds


class Paginator(View):
    def __init__(self, pages: list[discord.Embed], author_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self.message: discord.WebhookMessage | None = None
        for i, page in enumerate(pages, start=1):
            base = page.footer.text
            page.set_footer(text=f"{base} • Página {i}/{len(pages)}" if base else f"Página {i}/{len(pages)}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Apenas o autor do comando pode usar os botões.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Próximo ➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def send_paginated(interaction: discord.Interaction, pages: list[discord.Embed], ephemeral: bool):
    if len(pages) == 1:
        await interaction.followup.send(embed=pages[0], ephemeral=ephemeral)
        return
    view = Paginator(pages, interaction.user.id)
    view.message = await interaction.followup.send(embed=pages[0], view=view, ephemeral=ephemeral, wait=True)


def esc(text: str) -> str:
    return discord.utils.escape_markdown(text)


def note_label(message_id: int) -> str:
    created = discord.utils.snowflake_time(message_id)
    return f"{discord.utils.format_dt(created, 'd')} — [abrir nota]({jump_url(message_id)})"


# ---------- COMANDO /status ----------
def build_status_pages(guild: discord.Guild) -> list[discord.Embed]:
    total = len(note_reactions)
    required_role = guild.get_role(REQUIRED_ROLE_ID)
    assigned_role = guild.get_role(ROLE_ID)
    robot_role = guild.get_role(ROBOT_ROLE_ID) if ROBOT_ROLE_ID else discord.utils.get(guild.roles, name="Robot")
    req_name = required_role.name if required_role else "N/D"
    asg_name = assigned_role.name if assigned_role else "N/D"

    def names(members) -> list[str]:
        return sorted((esc(m.display_name) for m in members), key=str.lower)

    def progress(members) -> list[str]:
        return [
            f"{'✅' if assigned_role and assigned_role in m.roles else '❌'} {esc(m.display_name)} - "
            f"{sum(1 for users in note_reactions.values() if m.id in users)}/{total}"
            for m in sorted(members, key=lambda m: m.display_name.lower())
        ]

    pages: list[discord.Embed] = []

    # Comparação de cargos
    req_members = set(required_role.members) if required_role else set()
    asg_members = set(assigned_role.members) if assigned_role else set()
    for title, members in [
        ("✅ Com ambos os roles", req_members & asg_members),
        (f"❌ Apenas {req_name}", req_members - asg_members),
        (f"ℹ️ Apenas {asg_name}", asg_members - req_members),
    ]:
        pages += build_embeds(f"📋 {title} ({len(members)})", names(members), discord.Color.purple(), "Nenhum")

    # Progresso por grupo
    villains = [m for m in guild.members if required_role and required_role in m.roles]
    robots = [m for m in guild.members if robot_role and robot_role in m.roles]
    others = [m for m in guild.members if m not in villains and m not in robots]
    pages += build_embeds(f"👥 Progresso - {req_name}", progress(villains), discord.Color.red(), "Nenhum membro encontrado.")
    pages += build_embeds("🤖 Progresso - Robots", progress(robots), discord.Color.blue(), "Nenhum membro encontrado.")
    pages += build_embeds("👤 Progresso - Restantes", progress(others), discord.Color.orange(), "Nenhum membro encontrado.")

    # Status geral
    general = discord.Embed(title="📊 Status Geral", color=discord.Color.green())
    general.add_field(name="📌 Notas monitorizadas", value=str(total), inline=False)
    general.add_field(name="🪟 Janela", value=f"Últimas {NOTES_LIMIT} notas" if NOTES_LIMIT else "Todas as notas", inline=False)
    general.add_field(name="🔄 Estado", value="✅ Sincronizado" if notes_ready else "⏳ Não sincronizado", inline=False)
    pages.append(general)

    # Reações por nota (mais recente primeiro, com link)
    details = [f"📝 {note_label(mid)}: {len(users)} leitores" for mid, users in reversed(note_reactions.items())]
    pages += build_embeds("📨 Reações por Nota", details, discord.Color.blurple(), "Nenhuma nota monitorizada.")
    return pages


@bot.tree.command(name="status", description="Mostra o status das notas, reações e roles dos membros", guild=GUILD_OBJ)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(publico="Publicar a resposta no canal (padrão: só tu vês).")
async def status(interaction: discord.Interaction, publico: bool = False):
    await interaction.response.defer(thinking=True, ephemeral=not publico)
    try:
        await send_paginated(interaction, build_status_pages(interaction.guild), ephemeral=not publico)
    except Exception:
        log.exception("⚠️ Erro no /status")
        try:
            await interaction.followup.send("❌ Ocorreu um erro ao processar o status.", ephemeral=True)
        except discord.HTTPException:
            pass


# ---------- COMANDO /notas_em_falta ----------
@bot.tree.command(name="notas_em_falta", description="Mostra as notas a que ainda não reagiste.", guild=GUILD_OBJ)
async def missing_notes(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    if not notes_ready:
        return await interaction.followup.send("⏳ O bot ainda está a sincronizar as notas. Tenta daqui a pouco.", ephemeral=True)
    total = len(note_reactions)
    if total == 0:
        return await interaction.followup.send("ℹ️ Não há notas monitorizadas.", ephemeral=True)
    missing = [mid for mid, users in reversed(note_reactions.items()) if interaction.user.id not in users]
    if not missing:
        return await interaction.followup.send(f"✅ Já reagiste a todas as {total} notas!", ephemeral=True)
    lines = [f"• {note_label(mid)}" for mid in missing]
    pages = build_embeds(f"📌 Notas em falta ({len(missing)}/{total})", lines, discord.Color.orange(), "")
    await send_paginated(interaction, pages, ephemeral=True)


# ---------- COMANDOS /atividade E /mensagens ----------
@bot.tree.command(name="atividade", description="Mostra os membros com menos mensagens num mês.", guild=GUILD_OBJ)
@app_commands.default_permissions(manage_roles=True)
@app_commands.rename(limit="limite", role="cargo", month="mes", include_bots="incluir_bots", public="publico")
@app_commands.describe(
    limit="Quantos membros listar (1-100, padrão 10).",
    role="Inclui apenas membros com este cargo (opcional).",
    month="Mês a mostrar em AAAA-MM (padrão: mês atual).",
    include_bots="Incluir contas de bot (padrão: não).",
    public="Publicar no canal (padrão: só tu vês).",
)
async def least_active(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 100] = 10,
    role: discord.Role | None = None,
    month: str | None = None,
    include_bots: bool = False,
    public: bool = False,
):
    await interaction.response.defer(ephemeral=not public)
    guild = interaction.guild
    if guild is None:
        return await interaction.followup.send("Usa este comando num servidor.", ephemeral=True)

    if month:
        try:
            ym = datetime.strptime(month, "%Y-%m").strftime("%Y-%m")
        except ValueError:
            return await interaction.followup.send("Mês inválido. Usa `AAAA-MM` (ex.: `2025-11`).", ephemeral=True)
    else:
        ym = get_year_month()

    counts = await db.counts_for_month(guild.id, ym)
    if not guild.chunked:
        await guild.chunk(cache=True)

    members = list(guild.members)
    if role:
        members = [m for m in members if role in m.roles]
    if not include_bots:
        members = [m for m in members if not m.bot]
    if not members:
        return await interaction.followup.send("Nenhum membro corresponde aos filtros.", ephemeral=True)

    scored = sorted(((m, counts.get(m.id, 0)) for m in members), key=lambda t: (t[1], t[0].display_name.lower()))[:limit]
    lines = [f"**{i}.** {m.mention} — `{c}` mensage{'ns' if c != 1 else 'm'}" for i, (m, c) in enumerate(scored, start=1)]
    pages = build_embeds(f"Menos ativos — {guild.name}", lines, discord.Color.orange(), "")
    footer = f"Mês: {ym} • Bots: {'sim' if include_bots else 'não'} • Cargo: {role.name if role else 'Qualquer'}"
    for page in pages:
        page.set_footer(text=footer)
    await send_paginated(interaction, pages, ephemeral=not public)


@bot.tree.command(name="mensagens", description="Mostra a tua contagem de mensagens no mês atual.", guild=GUILD_OBJ)
async def my_messages(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("Usa este comando num servidor.", ephemeral=True)
    ym = get_year_month()
    c = (await db.counts_for_month(guild.id, ym)).get(interaction.user.id, 0)
    await interaction.response.send_message(f"Mandaste **{c}** mensage{'ns' if c != 1 else 'm'} em **{ym}**.", ephemeral=True)


# --- INICIAR BOT ---
if __name__ == "__main__":
    bot.run(BOT_TOKEN, log_handler=None)  # usa o logging configurado acima
