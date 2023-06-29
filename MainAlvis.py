'''
@author: jodru

Alvis - Main version

I was here at the beginning, and I will proclaim the end.
'''

import discord
from requests import get
from discord.ext import commands, tasks
import asyncio
import youtube_dl
from youtube_dl import YoutubeDL
import logging
import ffmpeg
from collections import deque, defaultdict
from dotenv import load_dotenv
import os

import sqlite3

conn = sqlite3.connect('database.db', check_same_thread = False)

def makeDatabase():
    #Init database, enable = 0 logs are disabled, enable = 1 logs are enabled
    #As well as birthday tables but that's for a future update
    c = conn.cursor()
    try: 
        c.execute("""CREATE TABLE registeredGuildsLogs (
                guildID integer UNIQUE,
                channelID integer,
                enableDelete integer,
                enableEdit integer
                )""")
        conn.commit()
        c.execute("""CREATE TABLE registeredGuildsBirthday (
                guildID integer UNIQUE,
                channelID integer
                )""")
        conn.commit()
    except:
        print();
    c.close()

load_dotenv()

# Bot logging section
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)


musQueue = defaultdict(deque)
loopEnable = defaultdict(bool)
nowp = {}
logChannel = {}

# YTDL Section


youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {'options': '-vn','before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

#This works
class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, volume=1):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class MusicPlayer(commands.Cog): #Dedicated music player
    def __init__(self, bot):
        self.bot = bot
        
    @classmethod
    def playmusic(self, vc, queue, idd, text):
        """Plays music."""
        
        def afterEnd(err):
            
            if loopEnable[idd] == True:
                asyncio.run(MusicPlayer.makeLoopObj(queue, idd))
            
            queueQ = musQueue[idd]
            if queueQ:
                self.playmusic(vc, queueQ, idd, text)   
            else:
                nowp[idd] = None
                asyncio.run_coroutine_threadsafe(vc.disconnect(), vc.loop)
                
        nowp[idd] = queue[0]
        vc.play(queue.popleft(), after=afterEnd) # Pop and play
        # Sends message - now playing
    
    @classmethod
    async def makeLoopObj(self, queue, idd):
        """Resets queue and sends currently playing song back to the beginning of the queue for looping purposes."""
        url = nowp[idd].url
        player = await YTDLSource.from_url(url, loop=None, stream=True)
        musQueue[idd].appendleft(player) # Append player left
                 
    @classmethod
    def queue_text(self, queueCopy):
            """Returns a block of text describing a given song queue."""
            
            if queueCopy != None:
                i = 0
                for x in queueCopy:
                    queueCopy[i] = f"{i+1}: {x.title}"
                    i = i+1
                return "\n".join([x for x in queueCopy])
            
            else:
                return "The play queue is empty."
            
class VoiceComs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def join(self, ctx):
        """Joins current voice channel. Must be used before playing music."""
        
        try:
            channel = ctx.author.voice.channel
        except Exception:
            await ctx.send('Author is not in call. Dummy.')
            return
        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)
        await channel.connect()
        
    @commands.command()
    async def dc(self, ctx):
        """Disconnects from channel."""
        
        await ctx.voice_client.disconnect()

    @commands.command()
    async def play(self, ctx, *, search): #Using url, either adds link to the queue or sends it directly to MusicPlayer to start playing.
        """Plays music from youtube link."""
        
        if ctx.voice_client is None:
            try:
                channel = ctx.author.voice.channel
            except Exception:
                await ctx.send('Author is not in call. Dummy.')
                return
            await channel.connect()
        
        
        vc = ctx.guild.voice_client
        tc = ctx.channel        
        
        if not "youtube" or ".com" in search:
            with YoutubeDL(ytdl_format_options) as ydl:
                try:
                    get(search)
                except:
                    info = ydl.extract_info(f"ytsearch:{search}", download=False)['entries'][0]
                else:
                    info = ydl.extract_info(search, download=False)
            
                url = info.get("webpage_url", None)
                    
                await ctx.send(f'Searching for {search}...')
                search = url
     
        
        player = await YTDLSource.from_url(search, loop=self.bot.loop, stream=True)
        musQueue[ctx.guild.id].append(player) # Set player obj for sending to MusicPlayer       
            
        if not vc.is_playing(): 
            await ctx.send(f'Now playing: {player.title}') 
            MusicPlayer.playmusic(vc, musQueue[ctx.guild.id], ctx.guild.id, tc)     
                
        elif vc.is_playing():
            await ctx.send(f'Added {player.title} to the queue') 
            return
            
        '''else:
            raise ValueError('Not sure how you got here, since you got something that was not true or false, but here we are...')
    
        except Exception:
            await ctx.send('Error!')
            return'''
            
    @commands.command()
    async def queue(self, ctx):
        """Display the current play queue."""
        
        queueCopy = musQueue[ctx.guild.id].copy()
        
        if queueCopy: #If queue is a thing...
            await ctx.send("```" + MusicPlayer.queue_text(queueCopy) + "```")
        else:
            await ctx.send("Queue is empty.")
            
    @commands.command()
    async def queueclear(self, ctx):
        """Clears the current queue."""
             
        if musQueue[ctx.guild.id]: #If queue is a thing...
            await musQueue[ctx.guild.id].clear()
            await ctx.send("The queue has been cleared.")
        else:
            await ctx.send("Queue is empty.")
    
    @commands.command()
    async def loop(self, ctx):
        """Enables/disables loop."""
        
         
        if loopEnable[ctx.guild.id]: #If the loop command has been used before...
            
            if loopEnable[ctx.guild.id] == False:
                loopEnable[ctx.guild.id] = True
                await ctx.send("Loop on.")
            else:
                loopEnable[ctx.guild.id] = False
                await ctx.send("Loop off.")
        else:
            loopEnable[ctx.guild.id] = True
            await ctx.send("Loop on.")
    
    @commands.command()
    async def pause(self, ctx):
        """Pauses currently playing music."""
        async with ctx.typing(): 
            if ctx.guild.voice_client.is_playing():
                ctx.guild.voice_client.pause()
            elif ctx.guild.voice_client.is_paused():
                await ctx.send("Already paused.")
            else:
                await ctx.send("Not currently playing anything.")
    
    @commands.command()
    async def resume(self, ctx):
        """Resumes paused music."""
        async with ctx.typing(): 
            if ctx.guild.voice_client.is_paused():
                ctx.guild.voice_client.resume()
            elif ctx.guild.voice_client.is_playing():
                await ctx.send("Already playing music.")
            else:    
                await ctx.send("Not currently playing anything.")    
                
    @commands.command()
    async def stop(self, ctx):
        """Stops the currently playing music."""
        async with ctx.typing(): 
            if ctx.guild.voice_client.is_paused():
                ctx.guild.voice_client.stop()
            elif ctx.guild.voice_client.is_playing():
                ctx.guild.voice_client.stop()
            else:    
                await ctx.send("Not currently playing anything.")
                
    @commands.command()
    async def skip(self, ctx): #No vote system enabled, please be careful!
        """Skips the currently playing song."""

        if ctx.guild.voice_client.is_playing():
            ctx.guild.voice_client.stop()
        else:
            await ctx.send("Not currently playing anything.")

    @commands.command()
    async def np(self, ctx):
        """Shows which song is currently playing"""
        idd = ctx.guild.id
        print(nowp)
        if nowp[idd]:
            await ctx.send(f'Now playing: {nowp[idd].title}')     
        else:
            await ctx.send("Nothing playing at the moment.")
        
class RegComs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None

    @commands.command()
    async def hellothere(self, ctx):
        """This is about all the "hello world" you old farts are gonna get."""
        await ctx.send("General Kenobi!")

    @commands.command()
    async def remind(self, ctx, time : str, *, message=''):
    
        """Adds a reminder to be sent after the specified time"""
    
        last = time[-1]
        thyme = time[:-1]
        thymeParse = int(thyme)
        segundo = 0
        try:
        
            if last == "s":
                segundo = thymeParse
            elif last == "m":
                segundo = thymeParse * 60
            elif last == "h":
                segundo = thymeParse * 60 * 60
            elif last == "d":
                segundo = thymeParse * 60 * 60 * 24
            else:
                raise ValueError('The dumbass did it wrong')
    
        except Exception:
            await ctx.send('Incorrect format. Try again idiot.')
            return
        await ctx.send("Reminder set in " + str(time) + ". The message is " + message)
        await asyncio.sleep(segundo)
        await ctx.send(f'Hi {ctx.message.author.mention}, you asked me to remind you about ' + message)

class LogComs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None


    @commands.command()
    @commands.has_permissions(administrator=True)
    async def registerLogs(self, ctx):
        """Register guild in database. Guild must be registered in order to use log functions."""
        #check sql database if guild is there, if not add to list. Return registered or already registered.
        #If not already registered, leave cID cell null and set enabled to false
        
        #Insert Guild ID into database if entry does not already exist
        c = conn.cursor()
        try:
            c.execute("INSERT INTO registeredGuildsLogs VALUES (?, NULL, 0, 0)", (ctx.guild.id,))
            conn.commit()
            await ctx.send("Guild registered.")
        except:
            await ctx.send("Guild ID already exists.")
        c.close()
        
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setLogChannel(self, ctx, *, channel: discord.TextChannel):
        """Set the log channel to the id provided."""
        #Set channel for logs
        c = conn.cursor()
        try:
            c.execute("UPDATE registeredGuildsLogs SET channelID = ? WHERE guildID = ?", (channel.id, ctx.guild.id))
            conn.commit()
            await ctx.send("Log channel updated.")
        except:
            await ctx.send("Error. Did you mention a channel after the command?")
        c.close()
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def enableDeletedMessageLog(self, ctx):
        """Enable deleted message logging"""
        
        #If cID exists, enable or disable log. if cID does not exist, return error and tell them to do better
        #Enable logs
        c = conn.cursor()
        try:
            c.execute("SELECT enableDelete FROM registeredGuildsLogs WHERE guildID = ?", (ctx.guild.id,))
            toggle = c.fetchone()[0]
        except:
            await ctx.send("Guild not found. Please register the guild.")
        else:
            c.execute("SELECT channelID FROM registeredGuildsLogs WHERE guildID = ?", (ctx.guild.id,))
            currChannelID = c.fetchone()[0]
            
            if currChannelID == None:
                await ctx.send("Channel ID has not been set. Please set a channel ID first.")    
            elif toggle == 1:
                c.execute("UPDATE registeredGuildsLogs SET enableDelete = 0 WHERE guildID = ?", (ctx.guild.id,))
                conn.commit()
                await ctx.send("Deleted message logs disabled.")
            else:
                c.execute("UPDATE registeredGuildsLogs SET enableDelete = 1 WHERE guildID = ?", (ctx.guild.id,))
                conn.commit()
                await ctx.send("Deleted message logs enabled.")
        c.close()
    
    @commands.command()
    @commands.has_permissions(administrator=True)  
    async def enableEditedMessageLog(self, ctx):
        """Enable deleted message logging"""
        
        #If cID exists, enable or disable log. if cID does not exist, return error and tell them to do better
        #Enable logs
        c = conn.cursor()
        print(ctx.guild.id)
        try:
            c.execute("SELECT enableEdit FROM registeredGuildsLogs WHERE guildID = ?", (ctx.guild.id,))
            toggle = c.fetchone()[0]
        except:
            await ctx.send("Guild not found. Please register the guild.")
        else:
            c.execute("SELECT channelID FROM registeredGuildsLogs WHERE guildID = ?", (ctx.guild.id,))
            currChannelID = c.fetchone()[0]
            
            if currChannelID == None:
                await ctx.send("Channel ID has not been set. Please set a channel ID first.")    
            elif toggle == 1:
                c.execute("UPDATE registeredGuildsLogs SET enableEdit = 0 WHERE guildID = ?", (ctx.guild.id,))
                conn.commit()
                await ctx.send("Deleted message logs disabled.")
            else:
                c.execute("UPDATE registeredGuildsLogs SET enableEdit = 1 WHERE guildID = ?", (ctx.guild.id,))
                conn.commit()
                await ctx.send("Edited message logs enabled.")
        c.close()
            
TOKEN = os.getenv("DISCORD_TOKEN") 

description = '''A collection of useful features for use by jodru and his friends.'''
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='?', activity = discord.Game(name="v1.2.2 - Edit logs enabled"), description=description, intents= intents)

@bot.event
async def on_ready():
    makeDatabase() #initialize database
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.event
async def on_message_delete(message):
    c = conn.cursor()
    try:
        c.execute("SELECT enableDelete FROM registeredGuildsLogs WHERE guildID = ?", (message.guild.id,))
        enable = c.fetchone()[0]
        c.execute("SELECT channelID FROM registeredGuildsLogs WHERE guildID = ?", (message.guild.id,))
        cID = c.fetchone()[0]
    except:
        print()
    else:
        if enable == 1:
            channel = bot.get_channel(cID)
            embed = discord.Embed(type = "rich",
                                  title = "",
                                  description = f'**Message sent by user {message.author.mention} in {message.channel.mention} deleted**', 
                                  color = message.author.color)
            embed.set_author(name = message.author.display_name, icon_url = message.author.avatar.url)
            embed.add_field(name = "",
                            value = f'{message.content}')
            await channel.send(embed=embed)
    c.close()

@bot.event
async def on_message_edit(message_before, message_after):
    c = conn.cursor()
    try:
        c.execute("SELECT enableEdit FROM registeredGuildsLogs WHERE guildID = ?", (message_before.guild.id,))
        enable = c.fetchone()[0]
        c.execute("SELECT channelID FROM registeredGuildsLogs WHERE guildID = ?", (message_before.guild.id,))
        cID = c.fetchone()[0]
    except:
        print()
    else:
        if enable == 1:
            channel = bot.get_channel(cID)
            embed = discord.Embed(type = "rich",
                                  title = "",
                                  description = f'**Message sent by user {message_before.author.mention} in {message_before.channel.mention} edited**', 
                                  color = message_before.author.color)
            embed.set_author(name = message_before.author.display_name, icon_url = message_before.author.avatar.url)
            embed.add_field(name = "Before",
                            value = f'{message_before.content}',
                            inline=False)
            
            embed.add_field(name = "After",
                            value = f'{message_after.content}',
                            inline=False)
            await channel.send(embed=embed)
    c.close()

async def main():
    async with bot:
        await bot.add_cog(LogComs(bot))
        await bot.add_cog(RegComs(bot)) 
        await bot.add_cog(VoiceComs(bot))
        await bot.start(TOKEN)

asyncio.run(main())

