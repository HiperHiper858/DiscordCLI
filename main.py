import asyncio
import discord
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from pathlib import Path
import os

BASE_DIR = Path(__file__).parent

console = Console()
user = '[yellow]You[/]'

class DiscordCompleter(Completer):
    def __init__(self, client):
        self.client = client

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()
        if text.startswith('-s '):
            prefix = text[len('-s '):]
            for guild in self.client.guilds:
                if guild.name.lower().startswith(prefix.lower()):
                    yield Completion(guild.name, start_position=-len(prefix))
        
        elif text.startswith('-cf '):
            prefix = text[len('-cf '):]
            for user in self.client.users:
                if user.name.lower().startswith(prefix.lower()):
                    yield Completion(user.name, start_position=-len(prefix))
        elif text.startswith('-c '):
            guild = self.client.current_guild
            if not guild:
                return
            prefix = text[len('-c '):]
            for channel in guild.text_channels:
                if channel.name.lower().startswith(prefix.lower()):
                    yield Completion(channel.name, start_position=-len(prefix))

class DiscordClient(discord.Client):
    def __init__(self):
        super().__init__()
        self.completer = DiscordCompleter(self)
        self.current_channel = None
        self.current_guild = None

    async def on_ready(self):
        console.print(f"[bold #00ff00]OK {self.user}[/]")
    async def on_message(self, message):
        if message.author == self.user:
            return
        if self.current_channel and message.channel.id == self.current_channel.id:   
            color = 'yellow' if msg.author.id == client.user.id else 'cyan'
            console.print(f"<{idx}> [{color}]{msg.author.name}:[/] {msg.content}")

async def start_cli(client):
    global user
    session = PromptSession(completer=client.completer)
    console.print("[bold green]On. Start with -s and -c. Wait for OK notif... [/]")
    while True:
        try:
            text = await session.prompt_async(ANSI('\x1b[32m> \x1b[0m'))
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip() in ('-exit', '-e', '-quit', '-q'):
            console.print("[bold red]/////////// SIGHUP ///////////[/]")
            await client.close()
            break
        elif text == '-h':
            console.print("""
        How to Use:
# Navigation:
-s [server]: Pick a server
-c [channel]: Pick a channel to Chat (require -s to be triggered)
-cf [friend]: Pick a friend to DM
-q(uit) or -e(xit): Exit the CLI
# Typing
-r [message no.] [txt]: Reply to message no with txt
->n & -<n: Scroll > (newest) or < (oldest) to n messages

                          """)
        elif text.startswith('-s '):
            name = text[len('-s '):]
            guild = discord.utils.find(lambda g: g.name == name, client.guilds)
            if guild:
                client.current_guild = guild
                console.print(f"Server: {guild.name}")
            else:
                console.print(f"[red]SERVER NOT EXIST: {name}[/]")
        elif text.startswith('-c '):
            if not client.current_guild:
                console.print("[red]Pick server first via -s[/]")
                continue
            name = text[len('-c '):]
            channel = discord.utils.find(
                lambda c: c.name == name,
                client.current_guild.text_channels
            )
            if channel:
                client.current_channel = channel
                client.history_offset = 0
                console.print(f"Channel: {channel.name}")
                # now delegate to our shared history window
                await display_history(client)
            else:
                # this is impossible to happen anyway xd
                console.print(f"[red]CHANNEL NOT EXIST: {name}[/]")
        elif text.startswith('-<'):
            # parse optional number
            num = int(text[1:]) if len(text) > 1 and text[1:].isdigit() else 10
            client.history_offset = min(len(client.history_buffer) // num, client.history_offset + 1)
            await display_history(client, num)
            continue
        elif text.startswith('->'):
            # parse optional number
            num = int(text[1:]) if len(text) > 1 and text[1:].isdigit() else 10
            client.history_offset = max(0, client.history_offset - 1)
            await display_history(client, num)
            continue
        elif text.startswith('-r'):
            # reply: \r <num> <message>
            parts = text.split(' ', 2)
            idx, msg = int(parts[1]), parts[2]
            target = client.history_buffer[idx-1]
            await target.reply(msg)
            console.print(f"[green]<{user}-{idx}>: {msg}[/]")
            continue
        elif text.startswith('-cf '):
            # Incase this doesn't make sense as why it is `cf`, so. The friend list in Discord act similarly like channel, so channel but friend... Makes sense right?
            name = text[len('-cf '):]
            user = discord.utils.find(lambda u: u.name == name, client.users)
            if user:
                client.current_channel = None
                console.print(f"**DM**: {user.name}")
                # fetch DM channel
                dm = client.get_user(user.id)
                channel = await user.create_dm()
                client.current_channel = channel
                client.history_offset = 0
                await display_history(client)
            else:
                console.print(f"[red]FRIEND NOT FOUND: {name}[/]")
        else:
            if client.current_channel:
                try:
                    await client.current_channel.send(text)
                    console.print(f"[green]<{user}>: {text}[/]")
                except Exception as e:
                    console.print(f"[red]FAIL TO REPLY: {e}[/]")
            else:
                console.print("[red]Select server & channel first. Use `server and `channel first.[/]")

async def display_history(client, window_size=10):
    if not client.current_channel:
        return
    # fetch and buffer messages oldest->newest
    buf = [msg async for msg in client.current_channel.history(limit=100)]
    client.history_buffer = list(reversed(buf))  # oldest first
    total = len(client.history_buffer)
    # calculate window indices from the end
    # history_offset counts windows from the end: 0 = last window
    end_index = total - client.history_offset * window_size
    start_index = max(0, end_index - window_size)
    window = client.history_buffer[start_index:end_index]
    console.print(f"-- Messages {total - end_index + 1} to {total - start_index} of {total} --")
    for idx, msg in enumerate(window, 1):
        color = 'yellow' if msg.author.id == client.user.id else 'cyan'
        console.print(f"<{idx}> [{color}]{msg.author.name}:[/] {msg.content}")

async def main(token):
    client = DiscordClient()
    await asyncio.gather(
        client.start(token),
        start_cli(client)
    )

if __name__ == '__main__':
    with open(os.path.join(BASE_DIR, "token.txt"), "r") as f:
        token = f.read().strip()
    if not token:
        console.print("[red]Set the DISCORD_TOKEN environment variable.[/]")
    else:
        asyncio.run(main(token))

