import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Obtém os valores das variáveis de ambiente
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
ROLE_ID = int(os.getenv('DISCORD_ROLE_ID'))
REQUIRED_ROLE_ID = int(os.getenv('DISCORD_REQUIRE_ROLE_ID'))
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))

# Configuração das intents necessárias para o bot funcionar corretamente
intents = discord.Intents.default()
intents.members = True  # Permite o bot interagir com membros
intents.message_content = True  # Permite o bot acessar o conteúdo das mensagens
intents.reactions = True  # Permite o bot monitorar reações

# Inicializa o bot com o prefixo '!' para comandos
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário que armazena reações por mensagem
message_reactions = {}

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    await initialize_reactions()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignora mensagens enviadas pelo próprio bot

    print(f' Nova mensagem detectada: {message.id} no canal {message.channel.id}')

    if message.channel.id == CHANNEL_ID and not message.author.bot:
        guild = message.guild
        role = guild.get_role(ROLE_ID)

        if role:
            for member in guild.members:
                if role in member.roles:
                    try:
                        await member.remove_roles(role)
                        print(f' Cargo removido de {member.name}')
                    except discord.Forbidden:
                        print(f'❌ Sem permissão para remover o cargo de {member.name}')
                    except Exception as e:
                        print(f'⚠️ Erro ao remover cargo de {member.name}: {e}')

        # Inicializa a lista de reações para a nova mensagem
        message_reactions[message.id] = set()

    await bot.process_commands(message)  # Permite que comandos do bot sejam processados

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        print(f'➕ {user.name} reagiu à mensagem {reaction.message.id}')

        message_reactions.setdefault(reaction.message.id, set()).add(user.id)

        # Verifica se todas as mensagens possuem a reação do usuário
        if all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role and role not in user.roles:
                try:
                    await user.add_roles(role)
                    print(f'✅ {user.name} recebeu o cargo {role.name}')
                except discord.Forbidden:
                    print(f'❌ Sem permissão para adicionar o cargo a {user.name}')
                except Exception as e:
                    print(f'⚠️ Erro ao adicionar o cargo a {user.name}: {e}')

@bot.event
async def on_reaction_remove(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        print(f'➖ {user.name} removeu reação da mensagem {reaction.message.id}')

        message_reactions.get(reaction.message.id, set()).discard(user.id)

        # Se o usuário não reagiu a todas as mensagens, remove o cargo
        if not all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role and role in user.roles:
                try:
                    await user.remove_roles(role)
                    print(f' {user.name} perdeu o cargo {role.name}')
                except discord.Forbidden:
                    print(f'❌ Sem permissão para remover o cargo de {user.name}')
                except Exception as e:
                    print(f'⚠️ Erro ao remover o cargo de {user.name}: {e}')

@bot.event
async def on_message_delete(message):
    if message.channel.id == CHANNEL_ID:
        if message.id in message_reactions:
            del message_reactions[message.id]
            print(f'️ Mensagem {message.id} apagada, removida do rastreamento.')

        role = discord.utils.get(message.guild.roles, id=ROLE_ID)
        if role:
            for member in message.guild.members:
                if role in member.roles and not all(member.id in reactions for reactions in message_reactions.values()):
                    try:
                        await member.remove_roles(role)
                        print(f' {member.name} perdeu o cargo {role.name} após a exclusão de uma mensagem.')
                    except discord.Forbidden:
                        print(f'❌ Sem permissão para remover o cargo de {member.name}')
                    except Exception as e:
                        print(f'⚠️ Erro ao remover o cargo de {member.name}: {e}')

async def initialize_reactions():
    await bot.wait_until_ready()
    await asyncio.sleep(1)

    guild = bot.guilds[0]
    print(f"Guild ID: {guild.id}")
    await guild.fetch_roles()
    await asyncio.sleep(5)  # Aumenta o atraso para 5 segundos

    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        print(f'⚠️ Canal com ID {CHANNEL_ID} não encontrado!')
        return

    print(' Inicializando rastreamento de mensagens e reações...')
    message_reactions.clear()

    async for message in channel.history(limit=100):
        message_reactions[message.id] = set()
        for reaction in message.reactions:
            async for user in reaction.users():
                if not user.bot:
                    message_reactions[message.id].add(user.id)
                    role_required = discord.utils.get(guild.roles, id=REQUIRED_ROLE_ID)
                    role_target = discord.utils.get(guild.roles, id=ROLE_ID)

                    if role_required and role_target:
                        print(f"Cargo necessário: {role_required.name}, Cargo alvo: {role_target.name}")

                        required_check = role_required in user.roles
                        reactions_check = all(user.id in reactions for reactions in message_reactions.values())

                        print(f"Verificação de cargo necessário: {required_check}, Verificação de reações: {reactions_check}")

                        if required_check:
                            if reactions_check:
                                if role_target not in user.roles:
                                    try:
                                        await user.add_roles(role_target)
                                        print(f'✅ {user.name} recebeu o cargo {role_target.name} após reinicialização.')
                                    except discord.Forbidden:
                                        print(f'❌ Sem permissão para adicionar o cargo a {user.name}')
                                    except Exception as e:
                                        print(f'⚠️ Erro ao adicionar o cargo a {user.name}: {e}')
                    else:
                        print('⚠️ Cargo necessário ou cargo alvo não encontrados.')
                        print(f"Cargo necessário encontrado: {role_required != None}, Cargo alvo encontrado: {role_target != None}")

    print(f'✅ Rastreamento inicializado: {len(message_reactions)} mensagens registradas.')

# Inicia o bot
bot.run(BOT_TOKEN)
