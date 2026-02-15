import os
import json 
print(">>> STARTING config.py")

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "secrets")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

print(">>> FINISHED config.py")
