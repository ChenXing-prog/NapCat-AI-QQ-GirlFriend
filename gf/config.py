"""Configuration management for the AI Girlfriend bot.

Loads from .env file with sensible defaults. All settings are accessible
as module-level constants after calling load_config().
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from project root (gf/ directory)
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # fallback to current working directory


@dataclass
class LLMConfig:
    """Configuration for the LLM API (Kimi — OpenAI-compatible + Vision)."""
    provider: str = "kimi"
    api_key: str = ""
    base_url: str = "https://api.moonshot.cn/v1"
    model: str = "moonshot-v1-8k"
    vision_model: str = "moonshot-v1-8k-vision-preview"
    max_tokens: int = 512
    temperature: float = 0.9

    def __post_init__(self):
        self.provider = os.getenv("LLM_PROVIDER", self.provider)
        self.api_key = os.getenv("LLM_API_KEY", self.api_key)
        self.base_url = os.getenv("LLM_BASE_URL", self.base_url)
        self.model = os.getenv("LLM_MODEL", self.model)
        self.vision_model = os.getenv("LLM_VISION_MODEL", self.vision_model)
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(self.max_tokens)))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", str(self.temperature)))


@dataclass
class NapCatConfig:
    """Configuration for the NapCatQQ connection."""
    base_url: str = "http://127.0.0.1:3000"
    ws_url: str = "ws://127.0.0.1:3001"
    access_token: str = ""

    def __post_init__(self):
        self.base_url = os.getenv("NAPCAT_BASE_URL", self.base_url)
        self.ws_url = os.getenv("NAPCAT_WS_URL", self.ws_url)
        self.access_token = os.getenv("NAPCAT_ACCESS_TOKEN", self.access_token)


@dataclass
class BotConfig:
    """Bot identity and behavior configuration."""
    bot_qq: str = ""
    bot_name: str = "小暖"
    sticker_probability: float = 0.4
    thinking_delay_min: float = 1.0
    thinking_delay_max: float = 4.0

    def __post_init__(self):
        self.bot_qq = os.getenv("BOT_QQ", self.bot_qq)
        self.bot_name = os.getenv("BOT_NAME", self.bot_name)
        self.sticker_probability = float(
            os.getenv("STICKER_PROBABILITY", str(self.sticker_probability))
        )
        self.thinking_delay_min = float(
            os.getenv("THINKING_DELAY_MIN", str(self.thinking_delay_min))
        )
        self.thinking_delay_max = float(
            os.getenv("THINKING_DELAY_MAX", str(self.thinking_delay_max))
        )


@dataclass
class ServerConfig:
    """Web server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self):
        self.host = os.getenv("HOST", self.host)
        self.port = int(os.getenv("PORT", str(self.port)))


@dataclass
class SchedulerConfig:
    """Configuration for the proactive messaging scheduler."""
    # Enable proactive messaging
    enabled: bool = True
    # Default clinginess for new users: clingy | normal | chill
    default_clinginess: str = "normal"
    # Morning greeting window (hours, local time)
    morning_start: int = 7
    morning_end: int = 10
    # Evening greeting window (hours, local time)
    evening_start: int = 21
    evening_end: int = 0
    # Minutes between scheduler checks
    check_interval_seconds: int = 60
    # Minimum hours between any two proactive messages
    min_interval_hours: int = 1

    def __post_init__(self):
        self.enabled = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
        self.default_clinginess = os.getenv("DEFAULT_CLINGINESS", self.default_clinginess)
        self.morning_start = int(os.getenv("MORNING_START", str(self.morning_start)))
        self.morning_end = int(os.getenv("MORNING_END", str(self.morning_end)))
        self.evening_start = int(os.getenv("EVENING_START", str(self.evening_start)))
        self.evening_end = int(os.getenv("EVENING_END", str(self.evening_end)))


@dataclass
class AppConfig:
    """Top-level application configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    napcat: NapCatConfig = field(default_factory=NapCatConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    data_dir: Path = Path("./data")
    stickers_dir: Path = Path("./stickers")
    admin_qq: str = ""
    sticker_frequency: float = 0.4  # Base probability

    def __post_init__(self):
        data = os.getenv("DATA_DIR", "./data")
        stickers = os.getenv("STICKERS_DIR", "./stickers")
        self.data_dir = Path(data)
        self.stickers_dir = Path(stickers)
        self.admin_qq = os.getenv("ADMIN_QQ", "")
        self.sticker_frequency = float(os.getenv("STICKER_FREQUENCY", "0.4"))
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Global config instance — initialize once at startup
_config: Optional[AppConfig] = None


def load_config() -> AppConfig:
    """Load and return the application configuration.

    Call this once at application startup. Subsequent calls return
    the cached instance.
    """
    global _config
    if _config is None:
        _config = AppConfig()
        _validate_config(_config)
    return _config


def get_config() -> AppConfig:
    """Get the current configuration (must call load_config first)."""
    global _config
    if _config is None:
        raise RuntimeError("Config not loaded. Call load_config() first.")
    return _config


def _validate_config(cfg: AppConfig):
    """Validate that required configuration is present."""
    if not cfg.llm.api_key or cfg.llm.api_key == "your-api-key-here":
        raise ValueError(
            "LLM_API_KEY is not set. Copy .env.example to .env and fill in your API key."
        )
    if not cfg.bot.bot_qq:
        raise ValueError("BOT_QQ is not set. Set your bot's QQ number in .env")
