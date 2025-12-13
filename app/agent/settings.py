import logging

from dotenv import load_dotenv

from ..common.config import load_app_config, load_prompts_config


# Load .env early so environment variables are available even if main is not imported.
load_dotenv()

logger = logging.getLogger(__name__)

APP_CONFIG = load_app_config()
PROMPTS_CONFIG = load_prompts_config()

# Strict configuration - no defaults here
DEFAULT_SYSTEM_PROMPT = PROMPTS_CONFIG["system"]
DEFAULT_MODEL = APP_CONFIG["default_model"]
AVAILABLE_MODELS = APP_CONFIG["available_models"]
DEFAULT_REASONING = APP_CONFIG["reasoning_effort"]
DEFAULT_VERBOSITY = APP_CONFIG["text_verbosity"]
DEFAULT_MAX_OUTPUT_TOKENS = APP_CONFIG["max_output_tokens"]
REASONING_OPTIONS = APP_CONFIG["reasoning_effort_options"]
