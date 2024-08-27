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
import mysql.connector
from mysql.connector import Error
from key import SERVER_ID, API_KEY, BOT_TOKEN, MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE

# Fetch sensitive data directly
ID = SERVER_ID
API_KEY = API_KEY
BOT_TOKEN = BOT_TOKEN

# Configurable settings
ENABLE_STATUS = True
WAIT_TIME = 60  # How often the bot should query the API in seconds
ENABLE_SECONDARY_BOT = False
SERVER_INDEX = 0  # Change this if you want to display another server
BOT_VERSION = "v2.2.1"

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


def create_tables_if_not_exists():
    connection = create_mysql_connection()
    if connection:
        try:
            cursor = connection.cursor()
            # Create tables if they do not exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    success BOOLEAN NOT NULL,
                    players_info JSON NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_counts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    server_id INT NOT NULL,
                    total_players INT NOT NULL,
                    total_slots INT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            connection.commit()
            cursor.close()
            logger.info("Tables created or verified successfully.")
        except Error as e:
            logger.error(f"Error creating tables: {e}")
        finally:
            connection.close()
    else:
        logger.error("Failed to connect to the database to create tables.")


# Function to connect to MySQL database
def create_mysql_connection():
    try:
        connection = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        if connection.is_connected():
            logger.info("Connected to MySQL database.")
            return connection
    except Error as e:
        logger.error(f"Error while connecting to MySQL: {e}")
        return None


# Log API data to MySQL database
def log_api_data_to_db(data):
    connection = create_mysql_connection()
    if connection:
        try:
            cursor = connection.cursor()
            # Assuming `api_data` table has columns for success and players info
            success = data.get("Success", False)
            players_info = json.dumps(data.get("Servers", []))
            query = """INSERT INTO api_data (success, players_info, timestamp) 
                       VALUES (%s, %s, %s)"""
            cursor.execute(query, (success, players_info, datetime.now()))
            connection.commit()
            cursor.close()
            connection.close()
            logger.info("API data logged to database successfully.")
        except Error as e:
            logger.error(f"Error while logging data to MySQL: {e}")
    else:
        logger.error("No MySQL connection available to log data.")


@client.event
async def on_ready():
    logger.info("The bot is running.")
    create_tables_if_not_exists()  # Ensure tables are created

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
                        # Log API data to MySQL
                        log_api_data_to_db(data)

                        player_count = data["Servers"][SERVER_INDEX]["Players"]
                        total_players, total_slots = map(int, player_count.split("/"))

                        # Insert player count into MySQL
                        connection = create_mysql_connection()
                        if connection:
                            try:
                                cursor = connection.cursor()
                                query = """INSERT INTO player_counts (server_id, total_players, total_slots, timestamp) 
                                           VALUES (%s, %s, %s, %s)"""
                                cursor.execute(query, (ID, total_players, total_slots, datetime.now()))
                                connection.commit()
                                cursor.close()
                                logger.info("Player count data logged to database successfully.")
                            except Error as e:
                                logger.error(f"Error while logging player count data to MySQL: {e}")
                            finally:
                                connection.close()

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
            "`!mysql_test` - Test the connection to the MySQL database.\n"
        ),
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@client.command(name='players')
async def player_count(ctx):
    try:
        connection = create_mysql_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT total_players, total_slots, timestamp FROM player_counts ORDER BY timestamp DESC LIMIT 1"
            cursor.execute(query)
            result = cursor.fetchone()
            cursor.close()
            connection.close()

            if result:
                total_players = result['total_players']
                total_slots = result['total_slots']

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

        else:
            raise Exception("Database connection failed.")

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


@client.command(name='mysql_test')
async def mysql_test(ctx):
    try:
        connection = create_mysql_connection()
        if connection:
            embed = discord.Embed(
                title="MySQL Test",
                description="Successfully connected to the MySQL database!",
                color=discord.Color.green()
            )
            connection.close()
        else:
            embed = discord.Embed(
                title="MySQL Test",
                description="Failed to connect to the MySQL database.",
                color=discord.Color.red()
            )
    except Exception as e:
        embed = discord.Embed(
            title="MySQL Test",
            description=f"Error: {e}",
            color=discord.Color.red()
        )
    await ctx.send(embed=embed)


client.run(BOT_TOKEN)