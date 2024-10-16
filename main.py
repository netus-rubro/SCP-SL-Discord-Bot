import os
import sys
import asyncio
import discord
from discord.ext import commands
import aiohttp
import json
from loguru import logger
import matplotlib.pyplot as plt
import io
import time
import importlib.util
import yaml

# Import the update checker
from updater import check_for_updates

# Constants
last_query_time = 0
QUERY_INTERVAL = 5
DATA_FILE = 'player_data.json'

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

# Load configuration from config.yml
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yml')  # Change to .yml
    if not os.path.isfile(config_path):
        logger.error(f"Configuration file not found at {config_path}. Please ensure 'config.yml' is present in the correct directory.")
        exit(1)
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)  # Use yaml to load the config

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
VERSION_SUFFIX = config.get("VERSION_SUFFIX", "-Public")  # Get version suffix from config
BOT_VERSION = "v4.3.1" + VERSION_SUFFIX  # Append the suffix to the bot version

# Setup logging with Loguru
logger.add(sys.stdout, format="{time} {level} {message}", level="INFO")

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
            logger.info(f"Content-Type received: {content_type}")

            raw_text = await response.text()
            logger.info(f"Raw content: {raw_text}")

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed to parse response as JSON: {json_err}")
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="Error parsing server data"))
                return

            if data.get("Success"):
                player_count = data["Servers"][SERVER_INDEX]["Players"]
                total_players, total_slots = map(int, player_count.split("/"))

                status = (discord.Status.idle if total_players == 0 else 
                          discord.Status.dnd if total_players == total_slots else 
                          discord.Status.online)
                activity_message = f"{total_players}/{total_slots} players online"
                await client.change_presence(status=status, activity=discord.Game(name=activity_message))
                logger.info(f"Player count: {activity_message}")
                
                save_data_to_json(data, DATA_FILE)
            else:
                logger.error(f"API Error: {data.get('Error')}")
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="Error fetching player data"))

    except Exception as e:
        logger.error(f"Error fetching status from API: {e}")
        await client.change_presence(status=discord.Status.idle, activity=discord.Game(name=f"Error: {e}"))

# Reconnect logic with exponential backoff
async def reconnect_with_backoff(max_retries=10):
    retry_delay = 1
    for attempt in range(max_retries):
        try:
            session = await create_session()
            return session
        except Exception as e:
            logger.error(f"Reconnect attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("Max reconnect attempts reached, giving up.")
                break

# Restart the bot
async def restart_bot():
    logger.warning("Restarting the bot due to connection issues...")
    os.execv(sys.executable, ['python'] + sys.argv)

async def create_session():
    return aiohttp.ClientSession()

# Event: When the bot is ready
@client.event
async def on_ready():
    logger.info("The bot is running.")
    
    # Check for updates when the bot starts
    await check_for_updates(BOT_VERSION, VERSION_SUFFIX)
    
    session = await create_session()
    while True:
        await set_bot_status(session)
        await asyncio.sleep(WAIT_TIME)

# Event: Bot disconnects
@client.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord.")
    await reconnect_with_backoff()

# Event: Bot resumes connection
@client.event
async def on_resumed():
    logger.info("Bot reconnected to Discord.")
    session = await create_session()
    while True:
        await set_bot_status(session)
        await asyncio.sleep(WAIT_TIME)

# Event: Message processing and command handling
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if any(blacklisted_word in message.content.lower() for blacklisted_word in BLACKLIST):
        logger.info(f"Ignored a message containing a blacklisted word: {message.content}")
        return

    await client.process_commands(message)

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
    
    if current_time - last_query_time >= QUERY_INTERVAL:
        try:
            data = load_json_data(DATA_FILE)
            if data.get("Success"):
                last_query_time = current_time
                player_count = data["Servers"][SERVER_INDEX]["Players"]
                total_players, total_slots = map(int, player_count.split("/"))

                fig, ax = plt.subplots(figsize=(10, 5))
                fig.patch.set_facecolor('#1c1c1c')

                plt.text(0.5, 0.5, f'{total_players:,} / {total_slots:,}\nPlayers Online', 
                         horizontalalignment='center', verticalalignment='center', 
                         fontsize=50, color='#4CAF50', fontweight='bold',
                         transform=ax.transAxes)

                ax.axis('off')
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
                buf.seek(0)
                await ctx.send(file=discord.File(fp=buf, filename='player_count.png'))
                plt.close(fig)
            else:
                await ctx.send("Error: Unable to fetch player data.")
        except Exception as e:
            logger.error(f"Error fetching player count: {e}")
            await ctx.send("Error fetching player count.")

# Command to display bot version
@client.command(name='version')
async def version(ctx):
    await ctx.send(f"Bot Version: {BOT_VERSION}")

# Command to test JSON reading
@client.command(name='json_test')
async def json_test(ctx):
    data = load_json_data(DATA_FILE)
    await ctx.send(f"JSON Data: {json.dumps(data, indent=4)}")

# Run the bot
client.run(BOT_TOKEN)
