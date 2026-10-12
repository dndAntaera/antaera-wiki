// The Antæra Wiki's Discord bot: it answers /dmnotes.
//
// Discord sends each slash command here as an HTTP request, and Cloudflare
// runs this on demand, so nothing has to stay switched on. /dmnotes opens a
// form for the DM's Notes; saving it writes them at the very top of the
// latest wiki announcement, the message the deploy workflow posts through
// the webhook. Only server admins can run it.
//
// The notes live in the announcement's own text, above the ping. The deploy
// workflow only ever edits the announcement's embed, so its later edits leave
// them alone.
//
// Secrets, set by .github/workflows/discord-bot.yml:
//   DISCORD_PUBLIC_KEY   proves each request really came from Discord
//   DISCORD_BOT_TOKEN    reads the announcement channel to find the latest post
//   DISCORD_WEBHOOK_URL  edits that post: only the webhook that posted it can

const API = "https://discord.com/api/v10";
const ADMINISTRATOR = 1n << 3n;
const EPHEMERAL = 1 << 6;
const HEADER = "### DM's Notes";
// A message's text caps at 2000 characters, and the notes share it with
// their heading and the ping.
const MAX_NOTES = 1800;
const USER_AGENT = "DiscordBot (https://github.com/dndAntaera/antaera-wiki, 1.0)";

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("The Antæra Wiki's Discord bot.\n");
    const body = await request.text();
    if (!(await fromDiscord(request, body, env.DISCORD_PUBLIC_KEY))) {
      return new Response("Bad request signature", { status: 401 });
    }
    const interaction = JSON.parse(body);
    const api = env.DISCORD_API || API; // pointed elsewhere only by the tests

    if (interaction.type === 1) return reply({ type: 1 }); // Discord checking in

    // Discord already hides the command from everyone else (it is registered
    // for admins only), but a server can loosen that in its settings.
    if (!isAdmin(interaction)) {
      return reply(ephemeral("Only server admins can use /dmnotes."));
    }
    if (interaction.type === 2 && interaction.data?.name === "dmnotes") {
      return openForm(env, api);
    }
    if (interaction.type === 5 && interaction.data?.custom_id?.startsWith("dmnotes:")) {
      // Saving takes two calls to Discord; answer at once and finish after.
      ctx.waitUntil(saveNotes(interaction, env, api));
      return reply({ type: 5, data: { flags: EPHEMERAL } });
    }
    return reply(ephemeral("That isn't something this bot does."));
  },
};

async function fromDiscord(request, body, publicKey) {
  const signature = request.headers.get("X-Signature-Ed25519");
  const timestamp = request.headers.get("X-Signature-Timestamp");
  if (!signature || !timestamp || !publicKey) return false;
  try {
    const key = await crypto.subtle.importKey(
      "raw", bytes(publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify(
      "Ed25519", key, bytes(signature), new TextEncoder().encode(timestamp + body));
  } catch {
    return false;
  }
}

function bytes(hex) {
  return new Uint8Array(hex.match(/../g).map((h) => parseInt(h, 16)));
}

function isAdmin(interaction) {
  try {
    return (BigInt(interaction.member?.permissions ?? 0) & ADMINISTRATOR) === ADMINISTRATOR;
  } catch {
    return false;
  }
}

// --- /dmnotes ---------------------------------------------------------------

async function openForm(env, api) {
  let post;
  try {
    post = await latestAnnouncement(env, api);
  } catch (e) {
    return reply(ephemeral("I couldn't read the announcement channel: " + e.message));
  }
  if (!post) return reply(ephemeral("There's no wiki announcement to add notes to yet."));

  const input = { type: 4, custom_id: "notes", style: 2, required: false, max_length: MAX_NOTES };
  const current = splitNotes(post.content)[0];
  if (current) input.value = current;
  return reply({
    type: 9,
    data: {
      custom_id: "dmnotes:" + post.id,
      title: "DM's Notes",
      components: [{
        type: 18,
        label: "Your thoughts on this update",
        description: "Shown at the top of the latest announcement. Leave empty to remove them.",
        component: input,
      }],
    },
  });
}

async function saveNotes(interaction, env, api) {
  const id = interaction.data.custom_id.slice("dmnotes:".length);
  const notes = (field(interaction.data.components, "notes") || "").trim();
  let answer;
  try {
    const url = hook(env, "/messages/" + id);
    const post = await discord("GET", url);
    const content = withNotes(post.content, notes);
    if (content.length > 2000) {
      answer = `Those notes are ${content.length - 2000} characters too long; nothing was changed.`;
    } else {
      // Editing never pings, but the mentions already in the text are named
      // so Discord keeps showing them as mentions.
      await discord("PATCH", url, {
        content,
        allowed_mentions: { parse: [], roles: [...content.matchAll(/<@&(\d+)>/g)].map((m) => m[1]) },
      });
      const link = `https://discord.com/channels/${interaction.guild_id}/${post.channel_id}/${post.id}`;
      answer = notes ? `DM's Notes saved: ${link}` : `DM's Notes removed: ${link}`;
    }
  } catch (e) {
    answer = "I couldn't update the announcement: " + e.message;
  }
  await discord("PATCH",
    `${api}/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`,
    { content: answer });
}

async function latestAnnouncement(env, api) {
  const webhook = await discord("GET", hook(env, ""));
  const messages = await discord("GET",
    `${api}/channels/${webhook.channel_id}/messages?limit=50`, null, env.DISCORD_BOT_TOKEN);
  // Newest first. Test messages from the "Test the Discord announcement"
  // workflow come through the same webhook and are passed over.
  return messages.find((m) => m.webhook_id === webhook.id
    && m.embeds?.[0]?.title && !m.embeds[0].title.endsWith("(test)"));
}

// The notes sit above everything else in the message's text:
//
//   ### DM's Notes
//   > first line
//   > second line
//
//   Ping: || @Scars ||
function splitNotes(content) {
  const lines = (content || "").split("\n");
  if (lines[0] !== HEADER) return ["", content || ""];
  let i = 1;
  const notes = [];
  for (; i < lines.length && lines[i].startsWith(">"); i++) notes.push(lines[i].replace(/^> ?/, ""));
  if (lines[i] === "") i++;
  return [notes.join("\n"), lines.slice(i).join("\n")];
}

function withNotes(content, notes) {
  const rest = splitNotes(content)[1];
  if (!notes) return rest;
  const quoted = notes.split("\n").map((line) => "> " + line).join("\n");
  return (`${HEADER}\n${quoted}\n\n${rest}`).trimEnd();
}

// A form's value, wherever Discord nests it: in a Label, or in the Action Row
// that older forms used.
function field(components, id) {
  for (const c of components || []) {
    if (c.custom_id === id) return c.value;
    const found = field([c.component, ...(c.components || [])].filter(Boolean), id);
    if (found !== undefined) return found;
  }
  return undefined;
}

// --- Discord ----------------------------------------------------------------

function hook(env, suffix) {
  const url = new URL(env.DISCORD_WEBHOOK_URL);
  url.pathname = url.pathname.replace(/\/$/, "") + suffix;
  return url.toString();
}

async function discord(method, url, body, botToken) {
  const headers = { "User-Agent": USER_AGENT };
  if (botToken) headers.Authorization = "Bot " + botToken;
  if (body) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    // Webhook and interaction tokens sit in the path; keep them out of errors.
    const path = new URL(url).pathname.replace(/(\/webhooks\/\d+\/)[^/]+/, "$1…");
    throw new Error(`Discord answered ${response.status} to ${method} ${path}`);
  }
  return response.status === 204 ? null : response.json();
}

function reply(data) {
  return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
}

function ephemeral(content) {
  return { type: 4, data: { content, flags: EPHEMERAL } };
}
