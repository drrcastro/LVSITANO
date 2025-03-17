require("dotenv").config();
const { Client, GatewayIntentBits } = require("discord.js");

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildMessageReactions,
  ],
});

const GUILD_ID = process.env.GUILD_ID;
const CHANNEL_ID = process.env.CHANNEL_ID;
const ROLE_ID = process.env.ROLE_ID;

client.once("ready", () => {
  console.log(`✅ Bot conectado como ${client.user.tag}`);
});

async function getUnreactedMessages(member) {
  const guild = client.guilds.cache.get(GUILD_ID);
  const channel = guild.channels.cache.get(CHANNEL_ID);
  const messages = await channel.messages.fetch({ limit: 100 });

  const unreactedMessages = [];
  for (const message of messages.values()) {
    let reacted = false;
    for (const reaction of message.reactions.cache.values()) {
      const users = await reaction.users.fetch();
      if (users.has(member.id)) {
        reacted = true;
        break;
      }
    }
    if (!reacted) {
      unreactedMessages.push(message);
    }
  }
  return unreactedMessages;
}

client.on("messageReactionAdd", async (reaction, user) => {
  if (user.bot || reaction.message.channelId !== CHANNEL_ID) return;

  const guild = client.guilds.cache.get(GUILD_ID);
  const member = await guild.members.fetch(user.id);
  const unreactedMessages = await getUnreactedMessages(member);
  const role = guild.roles.cache.get(ROLE_ID);

  if (unreactedMessages.length === 0 && !member.roles.cache.has(ROLE_ID)) {
    await member.roles.add(role);
    console.log(`✅ Role ${role.name} concedido a ${member.user.tag}`);
  }
});

client.on("messageCreate", async (message) => {
  if (message.channelId === CHANNEL_ID && !message.author.bot) {
    const guild = message.guild;
    const role = guild.roles.cache.get(ROLE_ID);
    role.members.forEach(async (member) => {
      await member.roles.remove(role);
      console.log(`❌ Role ${role.name} removido de ${member.user.tag}`);
    });
  }
});

client.login(process.env.TOKEN);
