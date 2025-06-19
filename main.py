import asyncio
import discord
import datetime
import shutil
import tkinter
from tkinter import filedialog
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.theme import Theme
from pathlib import Path
import os

#TODO:
# 1. Minor Improvement on Chat UI, see fn[display_history, render_history], and mention stuff
# 2. Add Upload Command
# 3. Add Delete message Command
# 4. Add forward Command
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "upload"
UPLOAD_DIR.mkdir(exist_ok=True)

# CONFIGURATION
theme = Theme(
        {
            "time": "grey39",
            "self": "bold #ff00ff",
            "other": "cyan",
            "head": "#00ffff",
            "e": "bold red", # error
            "o": "bold #00ff00", # ok
            "i": "bold yellow" # info
            }
        )
CONTEXT_WINDOW_SHOW_MESSAGE_TOTAL = 30 # Total messages to show in a single buffer
# i promise ill add more configuration here, im just too lazy to add one

console = Console(theme=theme)

# Clear screen
def clear():
    console.clear()

def pick_files():
    root = tkinter.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(title="Choose file to Upload. Any types.") 
    root.update()
    root.destroy()
    return [Path(p) for p in paths]

class CMDLexer(Lexer):
    def lex_document(self, document: Document):
        text = document.text
        def get_line(lineno):
            if text.lstrip().startswith('-'):
                return [("class:command", text)]
            return [("class:default", text)]
        return get_line

class DiscordCompleter(Completer):
    def __init__(self, client):
        self.client = client

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()
        # Server Nav
        if text.startswith('-s '):
            prefix = text[len('-s '):]
            for guild in self.client.guilds:
                if guild.name.lower().startswith(prefix.lower()):
                    yield Completion(guild.name, start_position=-len(prefix))
        
        # DM / Friend Nav
        elif any(text.startswith(CMDS) for CMDS in ("-cf ", "-dm ")):
            prefix = text.split(" ", 1)[1]
            for user in self.client.users:
                label = f"{user.display_name if hasattr(user,'display_name') else user.name} ({user.name})"

                if user.name.lower().startswith(prefix.lower()):
                    yield Completion(user.name, display=label, start_position=-len(prefix))
        
        # Forward Nav
        elif text.startswith('-fw '):
            parts = text.split(" ", 2)
            if len(parts) < 3: return # this means the user still typing for index param
            pref = parts[-1]
            
            for user in self.client.users:
                label=f"{user.display_name if hasattr(user,'display_name') else user.name} ({user.name})"
                if user.name.lower().startswith(pref.lower()):
                    yield Completion(user.name, display=label, start_position=-len(pref))

        

        # Channel Nav
        elif text.startswith('-c '):
            guild = self.client.current_guild
            if not guild:
                return
            prefix = text[len('-c '):]
            for channel in guild.text_channels:
                if channel.name.lower().startswith(prefix.lower()):
                    yield Completion(channel.name, start_position=-len(prefix))
        # Mention
        elif "@" in text.split(" ")[-1]:
            partial = text.split(" ")[-1].split("@")[-1]
            if self.client.current_guild:
                for u in self.client.current_guild.members:
                    if u.name.lower().startswith(partial.lower()):
                        yield Completion(u.name,start_position=-len(partial))

class DiscordClient(discord.Client):
    # Temporary Variables
    def __init__(self):
        super().__init__()
        self.completer = DiscordCompleter(self)
        self.current_channel = None
        self.current_guild = None
        self.show_displayname = True
        self.show_username = True
        self.upload_staged = []
        self.history_buffer = []
        self.history_offset = 0
        self.pending_pings = []
        # self.blocked_members = [] # next update
        # self.ignored_members = []

    # ----- HELPER -----
    # Author Format
    def fmt_author(self, member):
        if self.show_displayname and hasattr(member, "display_name"):
            if self.show_username:
                return f"{member.display_name} ({member.name})"
            else:
                return member.name
        return member.name
# ... existing code ...
    # Timestamp Format
    def fmt_time(self, dt):
        now = datetime.datetime.now().replace(tzinfo=datetime.timezone.utc)
        age = now - dt
        if age.total_seconds() < 86_400:
            return dt.strftime("%H:%M")
        return dt.strftime("%d/%m/%y")
    
    # ----- EVENTS -----
    # onReady Event
    async def on_ready(self):
        console.print(f"[bold #00ff00]OK {self.user}[/]")
        user = self.user    
    # onMessage Event
    async def on_message(self, message):
        # Ignore self
        if message.author == self.user:
            return

        # Ping Notification
        if self.user in message.mentions:
            console.bell()
            console.print(f"[i]PING by {message.author} in {message.channel}[/]")
            self.pending_pings.append(message)
        # Refresh History on Channel
        if self.current_channel and message.channel.id == self.current_channel.id:   
            await self.refresh_history(live=True)
    
    # Refresh History
    async def refresh_history(self, live=False):
        if not self.current_channel: 
            return
        buf = [m async for m in self.current_channel.history(limit=100)]
        self.history_buffer = list(reversed(buf))
        await self.render_history(live=live)

    # Display History
    async def render_history(self, live=False, window_size=CONTEXT_WINDOW_SHOW_MESSAGE_TOTAL):
        clear()
        total = len(self.history_buffer)
        # calculate window indices from the end
        # history_offset counts windows from the end: 0 = last window
        end_index = total - self.history_offset * window_size 
        start_index = max(0, end_index - window_size)
        window = self.history_buffer[start_index:end_index]

        header=f"ON:{self.current_guild}(#{self.current_channel}) [{start_index+1}-{end_index} / {total}]"
        console.print(f"[head]{header}[/head]")

        for index, message in enumerate(window, 1):
#             if message.author.id in self.blocked_members: # In next update
#                console.print(f"<{index}> ----- Blocked/Ignored ({self.fmt_author(message.author)})")
#                continue
            timestamp = f"[time]{self.fmt_time(message.created_at)}[/time]"
            auth_name = self.fmt_author(message.author)
            author = f"[self]{auth_name}[/self]" if message.author.id==self.user.id else f"[other]{auth_name}[/other]"
            header_line = f"<{index}> {timestamp} {author}"

            # If the message is a reply, adjust the header_line with the replied message index.
            if message.reference and message.reference.message_id:
                replied_index = None
                for i, m in enumerate(self.history_buffer, 1):
                    if m.id == message.reference.message_id:
                        replied_index = i
                        break
                if replied_index is None:
                    replied_index = "?"
                header_line = f"<{index} TO {replied_index}>"

            if "\n" in message.content:
                console.print(header_line)
                console.rule()  # horizontal rule before message
                console.print(message.content)
                console.rule()  # horizontal rule after message
            else:
                console.print(f"{header_line} {message.content}")

            # show reactions succinctly
            if message.reactions:
                reacts = " ".join(f"{r.emoji}×{r.count}" for r in message.reactions)
                console.print(f"     {reacts}")

async def start_cli(client):
    style = Style.from_dict({
        "command": "#00ff00",
        "default": ""
    })
    session = PromptSession(completer=client.completer, lexer=CMDLexer(), style=style)
    clear()
    console.print("[bold green]On. Start with -s and -c. Wait for OK notif... [/]")
    while True:
        try:
            text = await session.prompt_async(ANSI('\x1b[32m> \x1b[0m'))
        except (EOFError, KeyboardInterrupt):
            await client.close()
            break
        
        # Shorthands
        C = text.strip() # C(ommands) 
        def CS(command_name): # C(ommands).s(tartswith)
            return C.startswith(command_name)
        CN = C[3:] # The first 3 chars of C
        
        clear() # Clear first
        
        # ---- CMDS -----
        # Exit
        if C in ('-exit', '-e', '-quit', '-q'):
            console.print("[bold red]/////////// SIGHUP ///////////[/]")
            await client.close()
            break
        elif text == '-changelog':
            console.print("""[purple]
# Changelog
    v25.06.17 (yy/mm/dd)
        - Initial release
            *i forgot what features i did*
    
    v25.06.19 (Major Tweaks and Improvement)
        - Improved Chat UI
            a. Different color for user and other people
            b. Added timestamp
            c. Auto-clear for every command trigger
            d. Long message has horizontal bar
            e. Reply to message is visible
            f. Display name and User name shows (tweakable)
            g. Added more colors
            h. Color change upon command insert, the input I mean
        - More commands (check -h)
            a. -d(elete messages)
            b. -up(load file)
            c. -de(stage)up(load file)
            d. -f(or)w(ard) message
            e. -n(o)t(i)f
            f. -g(o to)n(o)t(i)f
        - Misc
            a. Minor revamp of code structure
            b. Added notifications for ping (untested)    
[/]
                          """)

        # Help
        elif text == '-h':
            console.print("""[purple]
How to Use:
-changeleg to see changelog
# Navigation:
    -s [server]: Pick a server
    -c [channel]: Pick a channel to Chat (require -s to be triggered)
    -cf [friend]: Pick a friend to DM
    -q(uit) or -e(xit): Exit the CLI
# Typing
    -r [message no.] [txt]: Reply to message no with txt
    -d [messages no.]: Delete messages index, accept list (e.g., -d 1 2 3)
    -up: Uploads a file, check your window list, there will be an explorer pop up, when you're done, it is saved into upload/, and you can send the file via '-r' or 'say' in which it will deletes after each -r or 'say'
    -deup: Delete all staged file upload
    -fw [message no.] [friend/member/dm]: Forward message index to somebody
    "@": Typing @ will gives a list of member in current channel to be mentioned
# Misc
    -ntf/-notif: Checks notification (within the buffer)
    -gntf/-gonotif: Go to notification location
    ->n & -<n: Scroll > (newest) or < (oldest) to n messages
[/]
                          """)
        # Server Navigation 
        elif CS('-s '):
            name = CN
            guild = discord.utils.find(lambda g: g.name == name, client.guilds)
            if guild:
                client.current_guild = guild
                console.print(f"[i]Server: {guild.name}[/i]")
            else:
                console.print(f"[e]SERVER NOT EXIST: {name}[/e]")
        # Channel Navigation
        elif CS('-c '):
            if not client.current_guild:
                console.print("[e]Pick server first via -s[/e]")
                continue
            name = CN
            channel = discord.utils.find(
                lambda c: c.name == name,
                client.current_guild.text_channels
            )
            try:
                if channel:
                    client.current_channel = channel
                    client.history_offset = 0
                    console.print(f"[i]Channel: {channel.name}[/i]")
                    # now delegate to our shared history window
                    await client.refresh_history()
                else:
                    # this is impossible to happen anyway xd
                    console.print(f"[e]CHANNEL NOT EXIST: {name}[e]")
            except:
                console.print(f"[e]You do not have access to the channel.[/e]")
        # Scrolling
        elif CS('-<'):
            # parse optional number
            num = int(text[1:]) if len(text) > 1 and text[1:].isdigit() else 10
            client.history_offset = min(len(client.history_buffer) // num, client.history_offset + 1)
            await client.refresh_history()
            continue
        elif CS('->'):
            # parse optional number
            num = int(text[1:]) if len(text) > 1 and text[1:].isdigit() else 10
            client.history_offset = max(0, client.history_offset - 1)
            await client.refresh_history()
            continue
        
        # Replying
        elif CS('-r '):
            # reply: \r <num> <message>
            parts = text.split(' ', 2)
            idx, msg = int(parts[1]), parts[2]
            try:
                target = client.history_buffer[idx-1]
                if hasattr(client, "upload_staged") and client.upload_staged:
                    F = [discord.File(p) for p in client.upload_staged]
                else:
                    F = None
                # Send the reply with or without files
                await target.reply(msg, files=F)
                client.upload_staged.clear()
            except Exception as e:
                console.print(f"[e]{e}[e], do the index even exist?") #eeeeee
            await client.refresh_history()
            continue
        
        # Deleting Message
        elif CS('-d '):
            indices = CN.split(' ') #split each index if >1
            for each_ind in indices:
                try:
                    idx = int(each_ind)
                    msg = client.history_buffer[idx-1]
                    if msg.author.id != client.user.id:
                        console.print('[e]Cannot delete other people messages[e]')
                    else:
                        await msg.delete()
                except ValueError:
                    console.print(f'[e]Invalid index: {idx_str}[/e]')
                except IndexError:
                    console.print(f'[e]Out of range: {idx_str}[/e]')

            await client.refresh_history()
            continue
        
        # Message forward
        elif CS("-fw "):
            # -fw <messageNo> <user>
            parts = text.split(" ", 2)
            if len(parts) < 3:
                console.print("[error]-fw <no> <user>")
                continue
            try:
                idx = int(parts[1])
            except ValueError:
                console.print("[error]Invalid message number[/error]")
                continue
            user_arg = parts[2].strip()
            if not user_arg:
                console.print("[error]User not specified[/error]")
                continue
            msg = client.history_buffer[idx-1]
            u = discord.utils.get(client.users, name=user_arg)
            if not u:
                console.print(f"[error]No such user {user_arg}[/error]")
                continue
            dm = await u.create_dm()
            await dm.send(msg.content)
            await client.refresh_history()
        
        # Upload staging
        elif C == "-up":
            client.upload_staged.clear()
            shutil.rmtree(UPLOAD_DIR,ignore_errors=True)
            UPLOAD_DIR.mkdir(exist_ok=True)
            picked = pick_files()
            
            if not picked:  # Check if any files were picked
                console.print("[o]Null.[/o]")
                continue

            for p in picked:
                dst = UPLOAD_DIR/p.name
                shutil.copy2(p,dst)
                client.upload_staged.append(dst)
                console.print(f"[o]Staged: {dst.name}[/o]")
            continue
        elif C == "-deup":
            client.upload_staged.clear()
            shutil.rmtree(UPLOAD_DIR,ignore_errors=True)
            UPLOAD_DIR.mkdir(exist_ok=True)
            console.print("[o]Upload reset.[/o]")
            
            
        # DM / Friend Navigation
        elif CS('-cf '):
            # Incase this doesn't make sense as why it is `cf`, so. The friend list in Discord act similarly like channel, so channel but friend... Makes sense right?
            name = CN
            user = discord.utils.find(lambda u: u.name == name, client.users)
            if user:
                client.current_channel = None
                console.print(f"**DM**: {user.name}")
                # fetch DM channel
                dm = client.get_user(user.id)
                channel = await user.create_dm()
                client.current_channel = channel
                client.history_offset = 0
                await client.refresh_history()
            else:
                console.print(f"[red]FRIEND NOT FOUND: {name}[/]")
        
        # Notifications
        elif C in ("-ntf","-notif"):
            if not client.pending_pings:
                console.print("[i]No pings.[/i]")
            for i,m in enumerate(client.pending_pings,1):
                console.print(f"[o]{i}. {client.fmt_author(m.author)} @ {m.channel}: {m.content[:60]}[o]")
        elif CS("-gntf") or CS("-gonotif"):
            parts=text.split(" ")
            if len(parts)<2: continue
            idx=int(parts[1])-1
            if idx<0 or idx>=len(client.pending_pings): console.print("[e]Bad index[e]"); continue
            ping=client.pending_pings[idx]
            client.current_channel=ping.channel
            await client.refresh_history()
        else:
            if client.current_channel:
                try:
                    if client.upload_staged:
                        F = [discord.File(p) for p in client.upload_staged]
                    else:
                        F = None
                    await client.current_channel.send(text,
                                       files = F
                                       ) #TODO: Add upload here
                    client.upload_staged.clear()
                    await client.refresh_history()
                except Exception as e:
                    console.print(f"[e]FAIL TO SNED MESSAGES: {e}[e]")
            else:
                console.print("[e]Select server & channel first. Use `server and `channel first.[e]")

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
        console.print("[err]token.txt does not exist\nIncase you haven't set them up, you can create a text file called 'token.txt' right beside this file, add your Discord Token, and retry[/]")
    else:
        asyncio.run(main(token))

