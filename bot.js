const { Client, GatewayIntentBits } = require('discord.js'); // Alteração aqui
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds, 
        GatewayIntentBits.GuildMessages, 
        GatewayIntentBits.MessageReactions
    ]
});

const TOKEN = 'SEU_TOKEN_DO_BOT';
const CHANNEL_ID = 'ID_DO_CANAL_ESPECIFICO';
const ROLE_ID = 'ID_DO_ROLE_A_SER_ADICIONADO';

let mensagensRequeridas = new Set(); // Para armazenar as mensagens que o membro precisa reagir

client.once('ready', () => {
    console.log('Bot está online!');
    
    // Obtém todas as mensagens do canal específico e armazena em 'mensagensRequeridas'
    const canal = client.channels.cache.get(CHANNEL_ID);
    canal.messages.fetch({ limit: 100 }).then(messages => {
        messages.forEach(message => {
            mensagensRequeridas.add(message.id);
        });
    });
});

client.on('messageCreate', message => {
    // Quando uma nova mensagem for enviada, adiciona à lista de mensagens requeridas
    if (message.channel.id === CHANNEL_ID) {
        mensagensRequeridas.add(message.id);
    }
});

client.on('messageReactionAdd', async (reaction, user) => {
    if (reaction.message.channel.id === CHANNEL_ID) {
        // Verifica se o usuário reagiu a todas as mensagens
        const reactedMessages = new Set();
        
        // Recolhe todas as reações que o usuário fez
        for (const [messageId, message] of reaction.message.channel.messages.cache) {
            const reactions = message.reactions.cache.filter(reaction => reaction.users.cache.has(user.id));
            if (reactions.size > 0) {
                reactedMessages.add(messageId);
            }
        }

        // Se o usuário reagiu a todas as mensagens, atribui o role
        if (mensagensRequeridas.size === reactedMessages.size) {
            const member = await reaction.message.guild.members.fetch(user.id);
            await member.roles.add(ROLE_ID);
        }
    }
});

client.on('messageReactionRemove', async (reaction, user) => {
    if (reaction.message.channel.id === CHANNEL_ID) {
        // Verifica se o usuário reagiu a todas as mensagens após remover a reação
        const reactedMessages = new Set();

        // Recolhe todas as reações que o usuário fez
        for (const [messageId, message] of reaction.message.channel.messages.cache) {
            const reactions = message.reactions.cache.filter(reaction => reaction.users.cache.has(user.id));
            if (reactions.size > 0) {
                reactedMessages.add(messageId);
            }
        }

        // Se o usuário não reagiu a todas as mensagens, remove o role
        if (mensagensRequeridas.size !== reactedMessages.size) {
            const member = await reaction.message.guild.members.fetch(user.id);
            await member.roles.remove(ROLE_ID);
        }
    }
});

client.login(TOKEN);
