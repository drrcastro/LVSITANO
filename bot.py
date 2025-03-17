import os
import discord
from discord.ext import commands

# Recupera as variáveis de ambiente
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))  # O ID do canal deve ser convertido para inteiro
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))  # O ID do cargo a ser atribuído
REQUIRE_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))  # O ID do cargo que o usuário deve ter para receber o novo

if BOT_TOKEN is None or CHANNEL_ID is None or ROLE_ID is None or REQUIRE_ROLE_ID is None:
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
        print(f"Mensagem recebida no canal: {message.channel.id}") # Verifique se a mensagem é do canal correto
        if message.channel.id == CHANNEL_ID and not message.author.bot:
            print(f"Mensagem é do canal monitorado! Removendo cargos de todos os membros...") # Remover o cargo de todos os usuários que o possuem
            for member in message.guild.members:
                role = discord.utils.get(member.guild.roles, id=ROLE_ID)
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                        print(f"{member.name} perdeu o cargo {role.name}.")
                    except discord.Forbidden as e:
                        print(f"Erro ao tentar remover o cargo de {member.name}: {e}")# Reiniciar as reações para a nova mensagem
            message_reactions[message.id] = set()
            print(f"Reações reiniciadas para a mensagem {message.id}")

        await bot.process_commands(message)  # Processa os comandos do bot (caso haja algum comando sendo executado)

    @bot.event
    async def on_reaction_add(reaction, user):
        if reaction.message.channel.id == CHANNEL_ID and not user.bot:
            print(f"Reação adicionada: {user.name} reagiu à mensagem {reaction.message.id}")
            if reaction.message.id not in message_reactions:
                message_reactions[reaction.message.id] = set()
            message_reactions[reaction.message.id].add(user.id) # Verifica se o usuário já tem o cargo necessário
            if any(role.id == REQUIRE_ROLE_ID for role in user.roles):
                if all(user.id in reactions for reactions in message_reactions.values()):
                    role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                    if role not in user.roles:
                        try:
                            await user.add_roles(role)
                            print(f"{user.name} recebeu o cargo {role.name}.")
                        except discord.Forbidden as e:
                            print(f"Erro de permissão ao tentar adicionar o cargo: {e}")
                    else:
                        print(f"{user.name} já possui o cargo {role.name}.")
                else:
                    print(f"{user.name} ainda não reagiu a todas as mensagens.")
            else:
                print(f"{user.name} não tem o cargo necessário para receber o novo cargo.")

    @bot.event
    async def on_reaction_remove(reaction, user):
        if reaction.message.channel.id == CHANNEL_ID and not user.bot:
            print(f"Reação removida: {user.name} removeu a reação da mensagem {reaction.message.id}")
            if reaction.message.id in message_reactions:
                message_reactions[reaction.message.id].discard(user.id)

            if not all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role in user.roles:
                    try:
                        await user.remove_roles(role)
                        print(f"{user.name} perdeu o cargo {role.name}.")
                    except discord.Forbidden as e:
                        print(f"Erro ao tentar remover o cargo de {user.name}: {e}")

    @bot.command()
    async def test_remove(ctx, member: discord.Member):
        """Comando para testar a remoção de cargos manualmente"""
        role = discord.utils.get(ctx.guild.roles, id=ROLE_ID)
        if role in member.roles:
            try:
                await member.remove_roles(role)
                await ctx.send(f"{member.name} perdeu o cargo {role.name}.")
            except discord.Forbidden as e:
                await ctx.send(f"Erro ao tentar remover o cargo: {e}")
        else:
            await ctx.send(f"{member.name} não tem o cargo {role.name}.")

    bot.run(BOT_TOKEN)
