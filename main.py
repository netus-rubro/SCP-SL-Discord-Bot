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
BOT_VERSION = "v2.2.1"

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

@client.event
async def on_ready():
    logger.info("The bot is running.")
    
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
                        save_data_to_json(data, 'data.json')

                        player_count = data["Servers"][SERVER_INDEX]["Players"]
                        total_players, total_slots = map(int, player_count.split("/"))

                        if ENABLE_STATUS:
                            status = (discord.Status.idle if total_players == 0 else 
                                      discord.Status.dnd if total_players == total_slots else 
                                      discord.Status.online)
                            activity_message = f"{total_players}/{total_slots} players online"
                            await client.change_presence(status=status, activity=discord.Game(name=activity_message))
                            logger.info(f"Player count: {activity_message}")
                    else:
                        logger.error(f"API Error: {data.get('Error')}")
                        activity_message = "0/0 players online (Check your config?)"
                        await client.change_presence(status=discord.Status.idle, activity=discord.Game(name=activity_message))
                        logger.info(f"Player count: {activity_message}")
            except Exception as e:
                logger.error(f"Error: {e}")
                activity_message = f"Error: {e}"
                await client.change_presence(status=discord.Status.idle, activity=discord.Game(name=activity_message))
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
            "`!version` - Displays the bot's current version.\n"
            "`!json_test` - Test reading from the JSON file.\n"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@client.command(name='players')
async def player_count(ctx):
    try:
        data = load_json_data('data.json')
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
            raise Exception("No player count data found.")
    except Exception as e:
        logger.error(f"Error: {e}")
        embed = discord.Embed(
            title="Error",
            description="Unable to fetch player count information.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

@client.command(name='info')
async def info(ctx):
    embed = discord.Embed(
        title="Bot Information",
        description=(
            f"**Bot Version:** {BOT_VERSION}\n"
            f"**System:** {platform.system()} {platform.release()}\n"
            f"**CPU Usage:** {psutil.cpu_percent()}%\n"
            f"**Memory Usage:** {psutil.virtual_memory().percent}%\n"
            f"**Uptime:** {datetime.now() - datetime.fromtimestamp(psutil.boot_time())}\n"
        ),
        color=discord.Color.purple()
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

@client.command(name='json_test')
async def json_test(ctx):
    try:
        # Load data from the JSON file
        data = load_json_data('data.json')
        
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
            description=f"Data loaded from JSON file:\n{json.dumps(censored_data, indent=4)}",
            color=discord.Color.green()
        )
    except Exception as e:
        embed = discord.Embed(
            title="JSON Test",
            description=f"Error: {e}",
            color=discord.Color.red()
        )
    
    await ctx.send(embed=embed)

client.run(BOT_TOKEN)