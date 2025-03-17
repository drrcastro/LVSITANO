import discord
from discord.ext import commands

TOKEN = SEU_TOKEN_AQUI
GUILD_ID = 123456789012345678  # ID do seu servidor
CHANNEL_ID = 123456789012345678  # ID do canal a ser monitorado
ROLE_ID = 123456789012345678  # ID do cargo a ser atribuído

intents = discord.Intents.default()
intents.messages = True
intents.reactions = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix=!, intents=intents)

@bot.event
async def on_ready()
    print(fBot conectado como {bot.user})

async def get_unreacted_messages(member)
     Retorna mensagens do canal que o membro ainda não reagiu. 
    guild = bot.get_guild(GUILD_ID)
    channel = guild.get_channel(CHANNEL_ID)
    messages = [msg async for msg in channel.history(limit=100)]  # Últimas 100 mensagens

    unreacted_messages = []
    for msg in messages
        reacted = False
        for reaction in msg.reactions
            users = [user async for user in reaction.users()]
            if member in users
                reacted = True
                break
        if not reacted
            unreacted_messages.append(msg)
    
    return unreacted_messages

@bot.event
async def on_raw_reaction_add(payload)
     Verifica se o usuário reagiu a todas as mensagens e atribui o cargo. 
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    
    if member.bot or payload.channel_id != CHANNEL_ID
        return

    unreacted_messages = await get_unreacted_messages(member)
    
    role = guild.get_role(ROLE_ID)
    if len(unreacted_messages) == 0 and role not in member.roles
        await member.add_roles(role)
        print(fRole {role.name} concedido a {member.name})

@bot.event
async def on_message(message)
     Remove o cargo de todos os membros quando uma nova mensagem for enviada. 
    if message.channel.id == CHANNEL_ID and not message.author.bot
        guild = message.guild
        role = guild.get_role(ROLE_ID)
        for member in role.members
            await member.remove_roles(role)
            print(fRole {role.name} removido de {member.name})

bot.run(TOKEN)
