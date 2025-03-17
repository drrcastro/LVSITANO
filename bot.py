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
