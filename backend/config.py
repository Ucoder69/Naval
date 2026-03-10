import json
import os

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json"
)

DEFAULT_CONFIG = {
    "username": None,
    "mode": "Balanced"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)

        for key in DEFAULT_CONFIG:
            if key not in data:
                data[key] = DEFAULT_CONFIG[key]

        return data

    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()

def save_config(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_username():
    return load_config().get("username")

def set_username(username: str):
    config = load_config()
    config["username"] = username
    save_config(config)

def get_mode():
    return load_config().get("mode")

def set_mode(mode: str):
    config = load_config()
    config["mode"] = mode
    save_config(config)