import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)


# Armazena as mensagens e quem reagiu a elas
message_reactions = {}

@bot.event
async def on_ready():
    print(f'Bot {bot.user} está online!')

@bot.event
async def on_message(message):
    if message.channel.id == CHANNEL_ID == message.author.bot:
        return
    print(f'Nova mensagem detectada: {message.id}')

    guild = message.guild
    role = guild.get_role(ROLE_ID)

    if role:
        for user in guild.members:
            if role in user.roles:
                await user.remove_roles(role)
                print(f'Role removido de {user.name}')
    else:
        print(f'Role com ID {ROLE_ID} não encontrado')
        # Armazena as mensagens para que possamos verificar quem reagiu
        message_reactions[message.id] = set()

    # Permite que os comandos sejam processados
    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        # Armazena quem reagiu a qual mensagem
        if reaction.message.id not in message_reactions:
            message_reactions[reaction.message.id] = set()
        
        message_reactions[reaction.message.id].add(user.id)

        # Verifica se o usuário reagiu a todas as mensagens
        if all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role not in user.roles:
                await user.add_roles(role)
                print(f"{user.name} recebeu o cargo {role.name}.")

@bot.event
async def on_reaction_remove(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        # Remove a reação de quem reagiu
        if reaction.message.id in message_reactions:
            message_reactions[reaction.message.id].discard(user.id)

        # Verifica se o usuário reagiu a todas as mensagens
        if not all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role in user.roles:
                await user.remove_roles(role)
                print(f"{user.name} perdeu o cargo {role.name}.")

# Substitua com o seu token do bot
bot.run('YOUR_BOT_TOKEN')
