import os
import sys
import asyncio
import discord
from discord.ext import commands
import aiohttp
import json
import logging
import matplotlib.pyplot as plt
import io
import time
import importlib.util

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
BOT_VERSION = "v4.2.0"

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
                
                # Save the data to a file
                save_data_to_json(data, DATA_FILE)
            else:
                logger.error(f"API Error: {data.get('Error')}")
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name="Error fetching player data"))

    except Exception as e:
        logger.error(f"Error fetching status from API: {e}")
        await client.change_presence(status=discord.Status.idle, activity=discord.Game(name=f"Error: {e}"))

# Reconnect logic with exponential backoff
async def reconnect_with_backoff(max_retries=5):
    retry_delay = 1  # Start with a 1-second delay
    for attempt in range(max_retries):
        try:
            await client.connect(reconnect=True)
            return
        except Exception as e:
            logger.error(f"Reconnect attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("Max reconnect attempts reached, giving up.")
                break

# Restart the bot
async def restart_bot():
    logger.warning("Restarting the bot due to connection issues...")
    os.execv(sys.executable, ['python'] + sys.argv)

# Event: When the bot is ready
@client.event
async def on_ready():
    logger.info("The bot is running.")
    
    async with aiohttp.ClientSession() as session:
        while True:
            await set_bot_status(session)
            await asyncio.sleep(WAIT_TIME)

# Event: Bot disconnects
@client.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord.")
    await restart_bot()

# Event: Bot resumes connection
@client.event
async def on_resumed():
    logger.info("Bot reconnected to Discord.")
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
            # Read data from the file
            data = load_json_data(DATA_FILE)
            if data.get("Success"):
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
                embed = discord.Embed(
                    title="Player Count",
                    description=f"Failed to fetch player count from the API. Please try again later.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error fetching player count: {e}")
    else:
        embed = discord.Embed(
            title="Player Count",
            description=f"Please wait {QUERY_INTERVAL} seconds between queries.",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed)

@client.command(name='json_test')
async def json_test(ctx):
    try:
        # Load data from the JSON file
        data = load_json_data(DATA_FILE)
        
        # Function to censor sensitive information
        def censor_sensitive_info(data):
            if isinstance(data, dict):
                # Remove or obscure sensitive information
                data = {k: (v if k not in ["port", "ID"] else "REDACTED") for k, v in data.items()}
                # Recursively process nested dictionaries
                for key, value in data.items():
                    if isinstance(value, dict):
                        data[key] = censor_sensitive_info(value)
                    elif isinstance(value, list):
                        data[key] = [censor_sensitive_info(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(data, list):
                data = [censor_sensitive_info(item) if isinstance(item, dict) else item for item in data]
            return data
        
        # Censor the sensitive information
        censored_data = censor_sensitive_info(data)
        
        # Create an embed with the censored data
        embed = discord.Embed(
            title="JSON Test",
            description=f"Data loaded from JSON file:\n```json\n{json.dumps(censored_data, indent=4)}```",
            color=discord.Color.green()
        )
    except Exception as e:
        embed = discord.Embed(
            title="JSON Test",
            description=f"Error: {e}",
            color=discord.Color.red()
        )
    
    await ctx.send(embed=embed)

@client.command(name='version')
async def version(ctx):
    embed = discord.Embed(
        title="Bot Version",
        description=f"**Current Version:** {BOT_VERSION}",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    try:
        client.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start the bot: {e}")
        asyncio.run(reconnect_with_backoff())
