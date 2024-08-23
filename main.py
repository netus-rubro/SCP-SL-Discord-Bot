import os
import asyncio
import discord
from discord.ext import commands
import aiohttp
import json
import logging
import matplotlib.pyplot as plt
import io
import psutil
import platform
from datetime import datetime
from key import SERVER_ID, API_KEY, BOT_TOKEN

# Made by Joseph_fallen

# Fetch sensitive data directly
ID = SERVER_ID
API_KEY = API_KEY
BOT_TOKEN = BOT_TOKEN

# Configurable settings
ENABLE_STATUS = True
WAIT_TIME = 11  # How often the bot should query the API in seconds
ENABLE_SECONDARY_BOT = False
SERVER_INDEX = 0  # Change this if you want to display another server
BOT_VERSION = "v1.2.1"

ADMIN_ROLE_ID = 123456789012345678

# Blacklist configuration
BLACKLIST = ['!!', '!!!', '!!!!']  # Add your blacklisted words or phrases here

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord bot configuration
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
intents.presences = True

client = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Initialize data.json if it doesn't exist
def initialize_data_file():
    if not os.path.exists("data.json"):
        logger.info("Creating data.json file.")
        default_data = {
            "Success": False,
            "Servers": [
                {
                    "Players": "0/0"
                }
            ]
        }
        with open("data.json", "w") as f:
            json.dump(default_data, f)
        logger.info("data.json file created with default values.")

@client.event
async def on_ready():
    logger.info("The bot is running.")
    initialize_data_file()
    while True:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://api.scpslgame.com/serverinfo.php?id={ID}&key={API_KEY}&players=true") as response:
                    content_type = response.headers.get('Content-Type', '')

                    if 'application/json' not in content_type:
                        response_text = await response.text()
                        logger.error(f"Unexpected content type: {content_type}")
                        logger.error(f"Response Text: {response_text}")
                        try:
                            data = json.loads(response_text)
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Error parsing JSON: {json_err}")
                            data = {}
                    else:
                        data = await response.json()

                    if data.get("Success"):
                        with open("data.json", "w") as f:
                            json.dump(data, f)

                        player_count = data["Servers"][SERVER_INDEX]["Players"]

                        if ENABLE_STATUS:
                            total_players, total_slots = map(int, player_count.split("/"))
                            status = (discord.Status.idle if total_players == 0 else 
                                      discord.Status.dnd if total_players == total_slots else 
                                      discord.Status.online)
                            activity_message = f"{total_players}/{total_slots} players online"
                            await client.change_presence(status=status, activity=discord.CustomActivity(name=activity_message))
                            logger.info(f"Player count: {activity_message}")
                    else:
                        logger.error(f"API Error: {data.get('Error')}")
                        activity_message = "0/0 players online (Check your config?)"
                        await client.change_presence(status=discord.Status.idle, activity=discord.CustomActivity(name=activity_message))
                        logger.info(f"Player count: {activity_message}")
            except Exception as e:
                logger.error(f"Error: {e}")
                activity_message = (f"Error: {e}")
                await client.change_presence(status=discord.Status.idle, activity=discord.CustomActivity(name=activity_message))
                logger.info(f"Player count: {activity_message}")
            await asyncio.sleep(WAIT_TIME)

@client.event
async def on_message(message):
    if message.author == client.user:
        return  # Ignore messages sent by the bot itself

    if any(blacklisted_word in message.content.lower() for blacklisted_word in BLACKLIST):
        logger.info(f"Ignored a message containing a blacklisted word: {message.content}")
        return  # Ignore the message if it contains a blacklisted word

    await client.process_commands(message)  # Process commands if no blacklisted words are found

# Basic commands
@client.command(name='ping')
async def ping(ctx):
    embed = discord.Embed(
        title="Ping",
        description=f"Pong! {round(client.latency * 1000)}ms",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@client.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="Help Menu",
        description=(
            "`!ping` - Check the bot's latency.\n"
            "`!help` - Display this help message.\n"
            "`!players` - Display the amount of players currently in the server.\n"
            "`!info` - Display the system uptime and other information.\n"
            "!version` - Displays the bot's current version.\n"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@client.command(name='players')
async def player_count(ctx):
    try:
        initialize_data_file()  # Ensure the data.json file exists

        with open("data.json", "r") as f:
            data = json.load(f)

        if data.get("Success"):
            player_count = data["Servers"][SERVER_INDEX]["Players"]
            total_players, total_slots = map(int, player_count.split("/"))

            # Create the plot
            fig, ax = plt.subplots(figsize=(10, 5))
            fig.patch.set_facecolor('#1c1c1c')  # Background color of the figure


            # Set the text in the middle
            plt.text(0.5, 0.5, f'{total_players:,} / {total_slots:,}\nPlayers Online', 
                     horizontalalignment='center', verticalalignment='center', 
                     fontsize=50, color='#4CAF50', fontweight='bold',
                     transform=ax.transAxes)

            # Remove axes
            ax.axis('off')

            # Save the plot to a BytesIO object
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
            buf.seek(0)
            plt.close(fig)

            # Send the plot as a file in Discord
            await ctx.send(file=discord.File(fp=buf, filename='player_count.png'))

        else:
            raise Exception(f"API Error: {data.get('Error')}")

    except Exception as e:
        logger.error(f"Error: {e}")
        embed = discord.Embed(
            title="Error",
            description="Unable to fetch player count information.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@client.command(name='version')
async def system_info(ctx):
    # Construct the embed
    embed = discord.Embed(title="Bot Version", color=discord.Color.dark_purple())
    embed.add_field(name="Bot Version", value=(BOT_VERSION), inline=False)

    await ctx.send(embed=embed)

@client.command(name='info')
async def system_info(ctx):
    # Uptime
    uptime_seconds = (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds()
    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))

    # System Info
    uname = platform.uname()
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    memory_usage = memory_info.percent

    # Construct the embed
    embed = discord.Embed(title="System Information", color=discord.Color.green())
    embed.add_field(name="System", value=f"{uname.system} {uname.release} ({uname.version})", inline=False)
    embed.add_field(name="Machine", value=f"{uname.machine}", inline=False)
    embed.add_field(name="Processor", value=f"{uname.processor}", inline=False)
    embed.add_field(name="Uptime", value=f"{uptime_str}", inline=False)
    embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=False)
    embed.add_field(name="Memory Usage", value=f"{memory_usage}%", inline=False)
    
    await ctx.send(embed=embed)

# Error handler for commands
@client.event
async def on_command_error(ctx, error):
    embed = discord.Embed(
        title="Error",
        description=f"An error occurred while processing the command: {error}",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)
    # Log the error to the console for debugging purposes
    logger.error(f"Command error in {ctx.command}: {error}")

# Run the bot
client.run(BOT_TOKEN)
