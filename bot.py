import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))  # Nome corrigido para manter consistência
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))

# Configuração de intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para armazenar reações por mensagem
message_reactions = {}

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    print(f'📩 Nova mensagem detectada: {message.id} no canal {message.channel.id}')

    if message.channel.id == CHANNEL_ID and not message.author.bot:
        guild = message.guild
        role = guild.get_role(ROLE_ID)

        # 🔴 Remover o cargo de todos os membros do servidor que o possuam
        if role:
            for member in guild.members:
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                        print(f'🚫 Role removido de {member.name}')
                    except discord.Forbidden:
                        print(f'❌ Permissões insuficientes para remover o cargo de {member.name}')
                    except Exception as e:
                        print(f'⚠️ Erro inesperado ao remover cargo de {member.name}: {e}')
        else:
            print(f'⚠️ Role com ID {ROLE_ID} não encontrado!')

        # Reiniciar rastreamento de reações para a nova mensagem
        message_reactions[message.id] = set()

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        print(f'➕ Reação adicionada: {user.name} reagiu à mensagem {reaction.message.id}')

        if reaction.message.id not in message_reactions:
            message_reactions[reaction.message.id] = set()

        message_reactions[reaction.message.id].add(user.id)

        required_role = discord.utils.get(user.guild.roles, id=REQUIRED_ROLE_ID)
        if required_role and required_role in user.roles:
            if all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role and role not in user.roles:
                    try:
                        await user.add_roles(role)
                        print(f'✅ {user.name} recebeu o cargo {role.name}.')
                    except discord.Forbidden:
                        print(f'❌ Permissões insuficientes para adicionar o cargo a {user.name}')
                    except Exception as e:
                        print(f'⚠️ Erro ao tentar adicionar o cargo a {user
