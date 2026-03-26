"""MIT License

Copyright (c) 2023 - present Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os

from dotenv import load_dotenv
from typing import (
    Dict,
    List,
    Any,
    Union
)

load_dotenv()

def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None

def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if value in (None, ""):
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def _build_env_nodes() -> Dict[str, Dict[str, Union[str, int, bool]]]:
    host = os.getenv("LAVALINK_HOST")
    password = os.getenv("LAVALINK_PASSWORD")

    if not host or not password:
        return {}

    return {
        os.getenv("LAVALINK_IDENTIFIER", "DEFAULT"): {
            "host": host,
            "port": _to_int(os.getenv("LAVALINK_PORT"), 2333),
            "password": password,
            "secure": _to_bool(os.getenv("LAVALINK_SECURE"), False),
            "identifier": os.getenv("LAVALINK_IDENTIFIER", "DEFAULT"),
        }
    }

class Settings:
    def __init__(self, settings: Dict) -> None:
        self.token: str = _first_non_empty(settings.get("token"), os.getenv("TOKEN"))
        self.client_id: int = _to_int(_first_non_empty(settings.get("client_id"), os.getenv("CLIENT_ID")))
        self.genius_token: str = _first_non_empty(settings.get("genius_token"), os.getenv("GENIUS_TOKEN"))
        self.mongodb_url: str = _first_non_empty(settings.get("mongodb_url"), os.getenv("MONGODB_URL"))
        self.mongodb_name: str = _first_non_empty(settings.get("mongodb_name"), os.getenv("MONGODB_NAME"))
        
        self.invite_link: str = "https://discord.gg/wRCgB7vBQv"
        self.nodes: Dict[str, Dict[str, Union[str, int, bool]]] = settings.get("nodes") or _build_env_nodes()
        self.max_queue: int = settings.get("default_max_queue", 1000)
        self.bot_prefix: str = settings.get("prefix", "")
        self.activity: List[Dict[str, str]] = settings.get("activity", [{"listen": "/help"}])
        self.logging: Dict[Union[str, Dict[str, Union[str, bool]]]] = settings.get("logging", {})
        self.embed_color: str = int(settings.get("embed_color", "0xb3b3b3"), 16)
        self.bot_access_user: List[int] = settings.get("bot_access_user", [])
        self.sources_settings: Dict[Dict[str, str]] = settings.get("sources_settings", {})
        self.cooldowns_settings: Dict[str, List[int]] = settings.get("cooldowns", {})
        self.aliases_settings: Dict[str, List[str]] = settings.get("aliases", {})
        self.controller: Dict[str, Dict[str, Any]] = settings.get("default_controller", {})
        self.voice_status_template: str = settings.get("default_voice_status_template", "")
        self.lyrics_platform: str = settings.get("lyrics_platform", "A_ZLyrics").lower()
        ipc_settings = settings.get("ipc_client", {})
        self.ipc_client: Dict[str, Union[str, bool, int]] = {
            **ipc_settings,
            "host": _first_non_empty(ipc_settings.get("host"), os.getenv("IPC_HOST"), "127.0.0.1"),
            "port": _to_int(_first_non_empty(ipc_settings.get("port"), os.getenv("IPC_PORT")), 8000),
            "password": _first_non_empty(ipc_settings.get("password"), os.getenv("IPC_PASSWORD"), ""),
            "secure": _to_bool(_first_non_empty(ipc_settings.get("secure"), os.getenv("IPC_SECURE")), False),
            "enable": _to_bool(_first_non_empty(ipc_settings.get("enable"), os.getenv("IPC_ENABLE")), False),
            "heartbeat": _to_int(_first_non_empty(ipc_settings.get("heartbeat"), os.getenv("IPC_HEARTBEAT")), 30),
        }
        self.version: str = settings.get("version", "")
