import subprocess
import sys

# List of essential libraries to install
libraries = [
    'aiohttp',
    'pyyaml',
    'loguru',
    'discord.py',
    'matplotlib',
]

def install(package):
    """Install a package using pip."""
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

def main():
    for library in libraries:
        try:
            __import__(library.replace('-', '_'))  # Check if the package is installed
            print(f"{library} is already installed.")
        except ImportError:
            print(f"{library} not found. Installing...")
            install(library)
            print(f"{library} installed successfully.")

if __name__ == "__main__":
    main()
