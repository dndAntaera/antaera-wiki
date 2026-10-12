# -*- coding: utf-8 -*-
"""Point Discord at the bot and register /dmnotes.

Run by .github/workflows/discord-bot.yml after each deploy of the worker:

  1. checks the bot has been added to the server the announcements go to,
     and prints the link that adds it if not;
  2. tells Discord to send the bot's interactions to the worker. Discord
     checks the address there and then, by sending it a test request;
  3. registers /dmnotes in that server, for admins only.

Environment: DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL, and WORKER_URL, the
worker's address. Without WORKER_URL it is looked up from Cloudflare with
CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
WORKER = "antaera-wiki-bot"          # name in wrangler.toml
USER_AGENT = "DiscordBot (https://github.com/dndAntaera/antaera-wiki, 1.0)"
ADMINISTRATOR = "8"
# What the bot needs in the announcement channel: to see it, and to read back
# far enough to find the latest announcement.
VIEW_CHANNEL, READ_MESSAGE_HISTORY = 1 << 10, 1 << 16

COMMANDS = [{
    "name": "dmnotes",
    "type": 1,
    "description": "Write the DM's Notes at the top of the latest wiki announcement",
    "default_member_permissions": ADMINISTRATOR,
}]


def call(method, url, body=None, token=None, auth="Bot"):
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "%s %s" % (auth, token)
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw[:300].decode("utf-8", "replace")}


def fail(message):
    print("::error::" + message.splitlines()[0])
    print(message)
    summary(message)
    sys.exit(1)


def summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n\n")


def worker_url():
    url = os.environ.get("WORKER_URL", "").strip()
    if url:
        return url.rstrip("/") + "/"
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    status, body = call("GET", "https://api.cloudflare.com/client/v4/accounts/%s/workers/subdomain"
                        % account, token=token, auth="Bearer")
    subdomain = (body or {}).get("result", {}).get("subdomain") if status == 200 else None
    if not subdomain:
        fail("Couldn't find the worker's address. Open Workers & Pages in the "
             "Cloudflare dashboard once, so the account has a workers.dev subdomain.")
    return "https://%s.%s.workers.dev/" % (WORKER, subdomain)


def main():
    token = os.environ["DISCORD_BOT_TOKEN"].strip()
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"].strip()

    status, app = call("GET", API + "/applications/@me", token=token)
    if status != 200:
        fail("Discord refused the bot token (HTTP %d). Reset it under Bot in the "
             "Developer Portal and save it again as DISCORD_BOT_TOKEN." % status)
    status, webhook = call("GET", webhook_url)
    if status != 200:
        fail("Discord refused the webhook (HTTP %d): check DISCORD_WEBHOOK_URL." % status)
    guild, channel = webhook["guild_id"], webhook["channel_id"]

    # 1. Is the bot in the server?
    invite = ("https://discord.com/oauth2/authorize?client_id=%s&scope=bot+applications.commands"
              "&permissions=%d&guild_id=%s&disable_guild_select=true"
              % (app["id"], VIEW_CHANNEL | READ_MESSAGE_HISTORY, guild))
    status, guilds = call("GET", API + "/users/@me/guilds", token=token)
    if status != 200 or not any(g["id"] == guild for g in guilds):
        fail("The bot isn't in the server yet. Open this link, add it, then run "
             "this workflow again:\n\n" + invite)
    status, _ = call("GET", API + "/channels/%s/messages?limit=1" % channel, token=token)
    if status != 200:
        fail("The bot can't read the announcement channel (HTTP %d). In that channel's "
             "permissions, allow the bot View Channel and Read Message History." % status)

    # 2. Where Discord sends interactions.
    url = worker_url()
    status, body = call("PATCH", API + "/applications/@me",
                        {"interactions_endpoint_url": url}, token=token)
    if status != 200:
        fail("Discord didn't accept %s as the bot's address (HTTP %d): %s\n\nIf the "
             "worker has only just deployed, run this workflow again in a minute."
             % (url, status, json.dumps(body)))

    # 3. The command, in the announcements' server, admins only.
    status, body = call("PUT", API + "/applications/%s/guilds/%s/commands" % (app["id"], guild),
                        COMMANDS, token=token)
    if status != 200:
        fail("Discord didn't register /dmnotes (HTTP %d): %s" % (status, json.dumps(body)))

    done = ("The bot answers at %s, and /dmnotes is registered for the server's admins."
            % url)
    print(done)
    summary(done)


if __name__ == "__main__":
    main()
