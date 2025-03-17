import os
import discord
from discord.ext import commands

# Recupera as variáveis de ambiente
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))  # O ID do canal deve ser convertido para inteiro
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))  # O ID do cargo deve ser convertido para inteiro

if BOT_TOKEN is None or CHANNEL_ID is None or ROLE_ID is None:
    print("Erro: uma ou mais variáveis de ambiente não estão definidas corretamente.")
else:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True

    # Criação da instância do bot
    bot = commands.Bot(command_prefix="!", intents=intents)

    message_reactions = {}

    @bot.event
    async def on_ready():
        print(f'Bot {bot.user} está online!')

    @bot.event
    async def on_message(message):
        print(f"Mensagem recebida no canal {message.channel.id}")
        if message.channel.id == CHANNEL_ID and not message.author.bot:
            message_reactions[message.id] = set()

        await bot.process_commands(message)

    @bot.event
    async def on_reaction_add(reaction, user):
        if reaction.message.channel.id == CHANNEL_ID and not user.bot:
            print(f"Reação adicionada: {user.name} reagiu à mensagem {reaction.message.id}")
            if reaction.message.id not in message_reactions:
                message_reactions[reaction.message.id] = set()

            message_reactions[reaction.message.id].add(user.id)

            if all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role not in user.roles:
                    await user.add_roles(role)
                    print(f"{user.name} recebeu o cargo {role.name}.")
                else:
                    print(f"{user.name} já possui o cargo {role.name}.")

    @bot.event
    async def on_reaction_remove(reaction, user):
        if reaction.message.channel.id == CHANNEL_ID and not user.bot:
            print(f"Reação removida: {user.name} removeu a reação da mensagem {reaction.message.id}")
            if reaction.message.id in message_reactions:
                message_reactions[reaction.message.id].discard(user.id)

            if not all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role in user.roles:
                    await user.remove_roles(role)
                    print(f"{user.name} perdeu o cargo {role.name}.")

    bot.run(BOT_TOKEN)
