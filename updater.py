import os
import sys
import aiohttp
import zipfile
import shutil
import yaml
from loguru import logger

# Function to load the config file
def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yml')  # Get full path
    logger.info(f"Looking for config file at: {config_path}")
    
    if not os.path.isfile(config_path):
        logger.error(f"Config file not found: {config_path}. Using default settings.")
        return {'auto_update': True}  # Default settings
    
    try:
        with open(config_path, 'r') as config_file:
            return yaml.safe_load(config_file) or {'auto_update': True}  # Default if file is empty
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {'auto_update': True}  # Default settings on error

# Function to update the bot code from GitHub
async def update_bot_code(download_url):
    try:
        repo_path = os.path.dirname(os.path.abspath(__file__))  # Path to the repo
        
        # Download the zip file
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    # Accept any binary response as a valid zip
                    content_type = response.headers.get('Content-Type')
                    logger.info(f"Response content type: {content_type}")

                    zip_file_path = os.path.join(repo_path, "update.zip")
                    with open(zip_file_path, "wb") as zip_file:
                        zip_file.write(await response.read())
                    logger.info("Downloaded zip file.")

                    # Extract the zip file
                    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                        extracted_folder = zip_ref.namelist()[0].split('/')[0]  # Get the first folder in the zip
                        zip_ref.extractall(repo_path)
                    logger.info("Extracted zip file.")

                    # Delete old main.py
                    old_main_path = os.path.join(repo_path, "main.py")
                    if os.path.exists(old_main_path):
                        os.remove(old_main_path)
                        logger.info("Deleted old main.py.")

                    # Move the new main.py to the current directory
                    new_main_path = os.path.join(repo_path, extracted_folder, "main.py")
                    if os.path.exists(new_main_path):
                        shutil.move(new_main_path, os.path.join(repo_path, "main.py"))
                        logger.info("Updated main.py.")
                    else:
                        logger.error("New main.py not found after extraction.")

                    # Clean up
                    shutil.rmtree(os.path.join(repo_path, extracted_folder))  # Remove the extracted folder
                    os.remove(zip_file_path)  # Remove the zip file
                    logger.info("Cleaned up temporary files.")

                    # Restart the bot
                    logger.info("Restarting the bot...")
                    os.execv(sys.executable, ['python'] + sys.argv)

                else:
                    logger.error(f"Failed to download zip: {response.status} - {response.reason}")

    except Exception as e:
        logger.error(f"Error updating bot code: {e}")


# Function to check for updates
async def check_for_updates(bot_version, version_suffix):
    config = load_config()  # Load config to check auto update setting
    if not config.get('auto_update', True):
        logger.info("Auto-update is disabled in the config. Skipping update.")
        return  # Skip update process if auto_update is set to false

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.github.com/repos/Josephfallen/SCP-SL-Discord-Bot/releases/latest") as response:
                if response.status == 200:
                    release_info = await response.json()
                    latest_version = release_info['tag_name']
                    logger.info(f"Fetched latest release: {latest_version}")

                    # Check if there's a new version by comparing only the version number part
                    if latest_version != bot_version:
                        logger.info(f"A new version is available: {latest_version}. Would you like to update? (Y/N)")
                        user_input = input("Update now? (Y/N): ").strip().upper()
                        if user_input == 'Y':
                            download_url = next((asset['browser_download_url'] for asset in release_info['assets'] if asset['name'].endswith('.zip')), None)
                            if download_url:
                                await update_bot_code(download_url)
                            else:
                                logger.error("No valid download URL found for the new version.")
                        else:
                            logger.info("Update skipped.")
                    else:
                        logger.info("You are running the latest version.")
                else:
                    logger.error(f"Failed to fetch latest release: {response.status} - {response.reason}")

    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
