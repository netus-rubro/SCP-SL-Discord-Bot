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
import importlib.util
import time
import sys

# Global variables
last_query_time = 0
QUERY_INTERVAL = 11

# Load sensitive information from key.py
def load_sensitive_info():
    key_path = os.path.join(os.path.dirname(__file__), 'key.py')
    spec = importlib.util.spec_from_file_location("key", key_path)
    key = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(key)
    return {
        "SERVER_ID": key.SERVER_ID,
        "API_KEY": key.API_KEY,
        "BOT_TOKEN": key.BOT_TOKEN
    }

sensitive_info = load_sensitive_info()

# Load configuration from config.json
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.isfile(config_path):
        logging.error(f"Configuration file not found at {config_path}. Please ensure 'config.json' is present in the correct directory.")
        exit(1)
    with open(config_path, 'r') as f:
        return json.load(f)

config = load_config()

# Fetch sensitive data
ID = sensitive_info["SERVER_ID"]
API_KEY = sensitive_info["API_KEY"]
BOT_TOKEN = sensitive_info["BOT_TOKEN"]

# Configurable settings
WAIT_TIME = config.get("WAIT_TIME", 60)
ENABLE_STATUS = config.get("ENABLE_STATUS", True)
SERVER_INDEX = config.get("SERVER_INDEX", 0)
BLACKLIST = config.get("BLACKLIST", [])
AUTHORIZED_USER_ID = config.get("AUTHORIZED_USER_ID")
BOT_VERSION = "v4.0.0"

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

# Save and load JSON data
def save_data_to_json(data, filename):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Data successfully written to '{filename}'.")
    except Exception as e:
        logger.error(f"Error writing to '{filename}': {e}")

def load_json_data(filename):
    if os.path.isfile(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading from '{filename}': {e}")
    return {}

# Function to set the bot's status based on API data
async def set_bot_status(session):
    try:
        async with session.get(f"https://api.scpslgame.com/serverinfo.php?id={ID}&key={API_KEY}&players=true") as response:
            content_type = response.headers.get('Content-Type', '')

            # Log content type for debugging
            logger.info(f"Content-Type received: {content_type}")

            # Read the raw response as text
            raw_text = await response.text()
            logger.info(f"Raw content: {raw_text}")

            # Attempt to manually parse as JSON, since the content type is incorrect
            try:
                data = json.loads(raw_text)  # Attempt to parse the raw text as JSON
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse response as JSON: {json_err}")
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="Error parsing server data"))
                return

            # Handle the JSON data if parsing succeeds
            if data.get("Success"):
                player_count = data["Servers"][SERVER_INDEX]["Players"]
                total_players, total_slots = map(int, player_count.split("/"))

                # Update bot presence
                status = (discord.Status.idle if total_players == 0 else 
                          discord.Status.dnd if total_players == total_slots else 
                          discord.Status.online)
                activity_message = f"{total_players}/{total_slots} players online"
                await client.change_presence(status=status, activity=discord.Game(name=activity_message))
                logger.info(f"Player count: {activity_message}")
            else:
                logger.error(f"API Error: {data.get('Error')}")
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="Error fetching player data"))

    except Exception as e:
        logger.error(f"Error fetching status from API: {e}")
        await client.change_presence(status=discord.Status.idle, activity=discord.Game(name=f"Error: {e}"))

# Event: When the bot is ready
@client.event
async def on_ready():
    logger.info("The bot is running.")
    
    async with aiohttp.ClientSession() as session:
        while True:
            await set_bot_status(session)
            await asyncio.sleep(WAIT_TIME)

# Event: Message processing and command handling
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
            "`!version` - Displays the bot's current version.\n"
            "`!json_test` - Test reading from the JSON file.\n"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Command to display player count
@client.command(name='players')
async def player_count(ctx):
    global last_query_time

    current_time = time.time()
    
    # Check if QUERY_INTERVAL has passed since the last query
    if current_time - last_query_time >= QUERY_INTERVAL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.scpslgame.com/serverinfo.php?id={ID}&key={API_KEY}&players=true") as response:
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        data = await response.json()
                    else:
                        html_content = await response.text()
                        logger.error(f"Unexpected content type: {content_type}")
                        logger.error(f"Response Text: {html_content}")
                        data = {}
                    
                    if data.get("Success"):
                        save_data_to_json(data, 'data.json')

                        # Update the last query time
                        last_query_time = current_time

                        # Proceed to generate the player count plot
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
                        raise Exception("No player count data found.")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP Client Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to retrieve player count data.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            embed = discord.Embed(
                title="Error",
                description="An unexpected error occurred.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Rate Limit",
            description=f"Please wait {int(QUERY_INTERVAL - (current_time - last_query_time))} seconds before using this command again.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

# Command to display system info
@client.command(name='info')
async def info(ctx):
    uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    embed = discord.Embed(
        title="System Information",
        description=(
            f"**Uptime:** {str(uptime).split('.')[0]}\n"
            f"**Platform:** {platform.system()} {platform.version()}\n"
            f"**CPU Usage:** {psutil.cpu_percent()}%\n"
            f"**Memory Usage:** {psutil.virtual_memory().percent}%"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Command to display bot version
@client.command(name='version')
async def version(ctx):
    embed = discord.Embed(
        title="Bot Version",
        description=f"The current bot version is {BOT_VERSION}.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# Command to test JSON read/write
@client.command(name='json_test')
async def json_test(ctx):
    data = load_json_data('data.json')
    if data:
        embed = discord.Embed(
            title="JSON Test",
            description="Successfully read from 'data.json'.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="JSON Test",
            description="Failed to read from 'data.json'.",
            color=discord.Color.red()
        )
    await ctx.send(embed=embed)

# Command to restart the bot
@client.command(name='restart')
async def restart(ctx):
    if ctx.author.id == AUTHORIZED_USER_ID:
        # Request confirmation via DM
        def check(m):
            return m.author == ctx.author and m.channel.type == discord.ChannelType.private

        try:
            # Send a DM to the user asking for confirmation
            dm_message = await ctx.author.send(
                "Are you sure you want to restart the bot? Type 'YES' to confirm."
            )
            
            # Wait for the user's confirmation response
            confirmation_message = await client.wait_for('message', timeout=60.0, check=check)
            
            if confirmation_message.content.strip().upper() == 'YES':
                await ctx.send("Restarting the bot...")
                logger.info("Restart command issued. Restarting the bot...")
                
                # Close the bot connection
                await client.close()

                # Restart the bot by re-running the script
                os.execv(sys.executable, ['python'] + sys.argv)
            else:
                await ctx.send("Restart canceled. You did not type 'YES'.")
                
        except asyncio.TimeoutError:
            await ctx.send("Restart canceled. You did not respond in time.")
            logger.info("Restart command timed out.")
            
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            logger.error(f"Error during restart command: {e}")
            
    else:
        await ctx.send("You are not authorized to use this command.")

# Run the bot
client.run(BOT_TOKEN)
