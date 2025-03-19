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
    guild = bot.guilds[0]  # Supondo que o bot está em um único servidor

    # Recuperar mensagens antigas do canal e inicializar as reações
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async for message in channel.history(limit=100):  # Ajuste o limite conforme necessário
            message_reactions[message.id] = set()
            for reaction in message.reactions:
                async for user in reaction.users():
                    if not user.bot:
                        message_reactions[message.id].add(user.id)

    # Verificar membros que já possuem o cargo necessário e atribuir o cargo de reação
    role_required = discord.utils.get(guild.roles, id=REQUIRED_ROLE_ID)
    role_target = discord.utils.get(guild.roles, id=ROLE_ID)
    if role_required and role_target:
        for member in guild.members:
            if role_required in member.roles:  # Verifica se o usuário tem o cargo necessário
                if all(member.id in reactions for reactions in message_reactions.values()):
                    if role_target not in member.roles:
                        try:
                            await member.add_roles(role_target)
                            print(f'✅ {member.name} recebeu o cargo {role_target.name} ao iniciar o bot.')
                        except discord.Forbidden:
                            print(f'❌ Permissões insuficientes para adicionar o cargo a {member.name}')
                        except Exception as e:
                            print(f'⚠️ Erro ao tentar adicionar o cargo a {member.name}: {e}')
    else:
        print('⚠️ Cargo necessário ou cargo alvo não encontrados.')

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
                        print(f'⚠️ Erro ao tentar adicionar o cargo a {user.name}: {e}')
        else:
            print(f'⚠️ {user.name} não possui o cargo necessário para ganhar o novo cargo.')

@bot.event
async def on_reaction_remove(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        print(f'➖ Reação removida: {user.name} removeu a reação da mensagem {reaction.message.id}')

        if reaction.message.id in message_reactions:
            message_reactions[reaction.message.id].discard(user.id)

        if not all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role and role in user.roles:
                try:
                    await user.remove_roles(role)
                    print(f'🚫 {user.name} perdeu o cargo {role.name}.')
                except discord.Forbidden:
                    print(f'❌ Permissões insuficientes para remover o cargo de {user.name}')
                except Exception as e:
                    print(f'⚠️ Erro ao tentar remover o cargo de {user.name}: {e}')

@bot.event
async def on_member_update(before, after):
    """ Garante que, ao receber o cargo necessário, o usuário obtenha o cargo alvo se tiver reagido a todas as mensagens. """
    if REQUIRED_ROLE_ID in [role.id for role in after.roles] and REQUIRED_ROLE_ID not in [role.id for role in before.roles]:
        user = after
        required_role = discord.utils.get(user.guild.roles, id=REQUIRED_ROLE_ID)

        if required_role:
            if all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role and role not in user.roles:
                    try:
                        await user.add_roles(role)
                        print(f'✅ {user.name} recebeu o cargo {role.name} (ao receber o cargo necessário).')
                    except discord.Forbidden:
                        print(f'❌ Permissões insuficientes para adicionar o cargo a {user.name}')
                    except Exception as e:
                        print(f'⚠️ Erro ao tentar adicionar o cargo a {user.name}: {e}')

@bot.event
async def on_message_delete(message):
    """ Remove a mensagem do rastreamento se for deletada. """
    if message.channel.id == CHANNEL_ID:
        if message.id in message_reactions:
            del message_reactions[message.id]
            print(f'🗑️ Mensagem {message.id} foi apagada e removida do rastreamento.')

        # Após remover a mensagem, verificar se algum usuário perdeu o cargo
        role = discord.utils.get(message.guild.roles, id=ROLE_ID)
        if role:
            for member in message.guild.members:
                if role in member.roles:
                    if not all(member.id in reactions for reactions in message_reactions.values()):
                        try:
                            await member.remove_roles(role)
                            print(f'🚫 {member.name} perdeu o cargo {role.name} pois uma mensagem foi apagada.')
                        except discord.Forbidden:
                            print(f'❌ Permissões insuficientes para remover o cargo de {member.name}')
                        except Exception as e:
                            print(f'⚠️ Erro ao tentar remover o cargo de {member.name}: {e}')

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
    guild = bot.guilds[0]  # Supondo que o bot está em um único servidor

    # Recuperar mensagens antigas do canal e inicializar as reações
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async for message in channel.history(limit=100):  # Ajuste o limite conforme necessário
            message_reactions[message.id] = set()
            for reaction in message.reactions:
                async for user in reaction.users():
                    if not user.bot:
                        message_reactions[message.id].add(user.id)

    # Verificar membros que já possuem o cargo necessário e atribuir o cargo de reação
    role_required = discord.utils.get(guild.roles, id=REQUIRED_ROLE_ID)
    role_target = discord.utils.get(guild.roles, id=ROLE_ID)
    if role_required and role_target:
        for member in guild.members:
            if role_required in member.roles:  # Verifica se o usuário tem o cargo necessário
                if all(member.id in reactions for reactions in message_reactions.values()):
                    if role_target not in member.roles:
                        try:
                            await member.add_roles(role_target)
                            print(f'✅ {member.name} recebeu o cargo {role_target.name} ao iniciar o bot.')
                        except discord.Forbidden:
                            print(f'❌ Permissões insuficientes para adicionar o cargo a {member.name}')
                        except Exception as e:
                            print(f'⚠️ Erro ao tentar adicionar o cargo a {member.name}: {e}')
    else:
        print('⚠️ Cargo necessário ou cargo alvo não encontrados.')

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
                        print(f'⚠️ Erro ao tentar adicionar o cargo a {user.name}: {e}')
        else:
            print(f'⚠️ {user.name} não possui o cargo necessário para ganhar o novo cargo.')

@bot.event
async def on_reaction_remove(reaction, user):
    if reaction.message.channel.id == CHANNEL_ID and not user.bot:
        print(f'➖ Reação removida: {user.name} removeu a reação da mensagem {reaction.message.id}')

        if reaction.message.id in message_reactions:
            message_reactions[reaction.message.id].discard(user.id)

        if not all(user.id in reactions for reactions in message_reactions.values()):
            role = discord.utils.get(user.guild.roles, id=ROLE_ID)
            if role and role in user.roles:
                try:
                    await user.remove_roles(role)
                    print(f'🚫 {user.name} perdeu o cargo {role.name}.')
                except discord.Forbidden:
                    print(f'❌ Permissões insuficientes para remover o cargo de {user.name}')
                except Exception as e:
                    print(f'⚠️ Erro ao tentar remover o cargo de {user.name}: {e}')

@bot.event
async def on_member_update(before, after):
    """ Garante que, ao receber o cargo necessário, o usuário obtenha o cargo alvo se tiver reagido a todas as mensagens. """
    if REQUIRED_ROLE_ID in [role.id for role in after.roles] and REQUIRED_ROLE_ID not in [role.id for role in before.roles]:
        user = after
        required_role = discord.utils.get(user.guild.roles, id=REQUIRED_ROLE_ID)

        if required_role:
            if all(user.id in reactions for reactions in message_reactions.values()):
                role = discord.utils.get(user.guild.roles, id=ROLE_ID)
                if role and role not in user.roles:
                    try:
                        await user.add_roles(role)
                        print(f'✅ {user.name} recebeu o cargo {role.name} (ao receber o cargo necessário).')
                    except discord.Forbidden:
                        print(f'❌ Permissões insuficientes para adicionar o cargo a {user.name}')
                    except Exception as e:
                        print(f'⚠️ Erro ao tentar adicionar o cargo a {user.name}: {e}')

@bot.event
async def on_message_delete(message):
    """ Remove a mensagem do rastreamento se for deletada. """
    if message.channel.id == CHANNEL_ID:
        if message.id in message_reactions:
            del message_reactions[message.id]
            print(f'🗑️ Mensagem {message.id} foi apagada e removida do rastreamento.')

        # Após remover a mensagem, verificar se algum usuário perdeu o cargo
        role = discord.utils.get(message.guild.roles, id=ROLE_ID)
        if role:
            for member in message.guild.members:
                if role in member.roles:
                    if not all(member.id in reactions for reactions in message_reactions.values()):
                        try:
                            await member.remove_roles(role)
                            print(f'🚫 {member.name} perdeu o cargo {role.name} pois uma mensagem foi apagada.')
                        except discord.Forbidden:
                            print(f'❌ Permissões insuficientes para remover o cargo de {member.name}')
                        except Exception as e:
                            print(f'⚠️ Erro ao tentar remover o cargo de {member.name}: {e}')


# Adiciona a função de inicialização no final do código
async def initialize_reactions():
    """ Inicializa o rastreamento das mensagens e reações ao iniciar o bot. """
    await bot.wait_until_ready()  # Espera o bot estar pronto antes de executar

    guild = bot.guilds[0]  # Supondo que o bot está em um único servidor
    channel = bot.get_channel(CHANNEL_ID)

    if not channel:
        print(f'⚠️ Canal com ID {CHANNEL_ID} não encontrado!')
        return

    print('🔄 Inicializando rastreamento de mensagens e reações...')
    
    # Resetar o dicionário de reações
    message_reactions.clear()

    async for message in channel.history(limit=100):  # Ajuste o limite conforme necessário
        message_reactions[message.id] = set()
        
        for reaction in message.reactions:
            async for user in reaction.users():
                if not user.bot:
                    message_reactions[message.id].add(user.id)

    # Verificar e conceder cargos para usuários que já reagiram a todas as mensagens
    role_required = discord.utils.get(guild.roles, id=REQUIRED_ROLE_ID)
    role_target = discord.utils.get(guild.roles, id=ROLE_ID)

    if role_required and role_target:
        for member in guild.members:
            if role_required in member.roles:  # Se tem o cargo necessário
                if all(member.id in reactions for reactions in message_reactions.values()):
                    if role_target not in member.roles:
                        try:
                            await member.add_roles(role_target)
                            print(f'✅ {member.name} recebeu o cargo {role_target.name} após reinicialização.')
                        except discord.Forbidden:
                            print(f'❌ Permissões insuficientes para adicionar o cargo a {member.name}')
                        except Exception as e:
                            print(f'⚠️ Erro ao tentar adicionar o cargo a {member.name}: {e}')
    else:
        print('⚠️ Cargo necessário ou cargo alvo não encontrados.')

# Executar a função de inicialização assim que o bot estiver pronto
bot.loop.create_task(initialize_reactions())

# Inicia o bot
bot.run(BOT_TOKEN)

