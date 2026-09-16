import logging
import os

import pytz
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GrokBot')


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    logger.info(f'Loading environment from {dotenv_path}')
    load_dotenv(dotenv_path)
else:
    logger.info('.env file not found, using environment variables')
    load_dotenv()


TOKEN = os.getenv('DISCORD_TOKEN')
XAI_KEY = os.getenv('XAI_API_KEY')

if TOKEN:
    logger.info(f'DISCORD_TOKEN loaded (length: {len(TOKEN)})')
else:
    logger.error('DISCORD_TOKEN not found in environment!')

if XAI_KEY:
    logger.info(f'XAI_API_KEY loaded (length: {len(XAI_KEY)})')
else:
    logger.error('XAI_API_KEY not found in environment!')


TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'America/Chicago'))

# Retired slugs that still appear in older .env files. Current Grok chat models
# accept images natively, so dedicated vision IDs are no longer needed.
_RETIRED_MODELS = {
    'grok-2-vision': 'grok-4.3',
    'grok-2-vision-1212': 'grok-4.3',
    'grok-vision-beta': 'grok-4.3',
    'grok-2': 'grok-4.3',
    'grok-2-1212': 'grok-4.3',
    'grok-3': 'grok-4.3',
    'grok-3-mini': 'grok-4.3',
    'grok-4-1-fast-reasoning': 'grok-4.3',
    'grok-4-1-fast-non-reasoning': 'grok-4.3',
    'grok-4-fast-reasoning': 'grok-4.3',
    'grok-4-fast-non-reasoning': 'grok-4.3',
    'grok-imagine-image-pro': 'grok-imagine-image-2.0',
}


def _resolve_model(env_name: str, default: str) -> str:
    raw = os.getenv(env_name, default)
    mapped = _RETIRED_MODELS.get((raw or '').strip().lower(), raw)
    if mapped != raw:
        logger.warning('Configured %s=%s is retired; using %s', env_name, raw, mapped)
    return mapped


# grok-4.3 is the cheapest current general model and already accepts image input.
# grok-4.6 is newer/smarter but costs more ($2/$6 vs $1.25/$2.50 per 1M tokens).
GROK_TEXT_MODEL = _resolve_model('GROK_TEXT_MODEL', 'grok-4.3')
GROK_VISION_MODEL = _resolve_model('GROK_VISION_MODEL', GROK_TEXT_MODEL)
GROK_DOCUMENT_MODEL = _resolve_model('GROK_DOCUMENT_MODEL', GROK_TEXT_MODEL)
GROK_IMAGE_MODEL = _resolve_model('GROK_IMAGE_MODEL', 'grok-imagine-image-2.0')
logger.info(
    'Grok models: text=%s vision=%s document=%s image=%s',
    GROK_TEXT_MODEL, GROK_VISION_MODEL, GROK_DOCUMENT_MODEL, GROK_IMAGE_MODEL,
)

ENABLE_WEB_SEARCH = os.getenv('ENABLE_WEB_SEARCH', 'true').lower() == 'true'
ENABLE_X_SEARCH = os.getenv('ENABLE_X_SEARCH', 'false').lower() == 'true'
ENABLE_CODE_EXECUTION = os.getenv('ENABLE_CODE_EXECUTION', 'false').lower() == 'true'
ENABLE_NL_HISTORY_SEARCH = os.getenv('ENABLE_NL_HISTORY_SEARCH', 'true').lower() == 'true'
ENABLE_PROMPT_CACHE_HINTS = os.getenv('ENABLE_PROMPT_CACHE_HINTS', 'true').lower() == 'true'

GROK_REASONING_EFFORT = os.getenv('GROK_REASONING_EFFORT', 'low').lower()
GROK_ANALYSIS_REASONING_EFFORT = os.getenv('GROK_ANALYSIS_REASONING_EFFORT', 'high').lower()

MAX_KEYWORD_SCAN = int(os.getenv('MAX_KEYWORD_SCAN', '10000'))
MAX_MESSAGES_ANALYZED = int(os.getenv('MAX_MESSAGES_ANALYZED', '500'))
DEFAULT_SEARCH_LIMIT = int(os.getenv('DEFAULT_SEARCH_LIMIT', '5000'))

GROK_TEXT_INPUT_COST = float(os.getenv('GROK_TEXT_INPUT_COST', '1.25'))
GROK_TEXT_OUTPUT_COST = float(os.getenv('GROK_TEXT_OUTPUT_COST', '2.50'))
GROK_TEXT_CACHED_COST = float(os.getenv('GROK_TEXT_CACHED_COST', '0.20'))
GROK_VISION_INPUT_COST = float(os.getenv('GROK_VISION_INPUT_COST', '1.25'))
GROK_VISION_OUTPUT_COST = float(os.getenv('GROK_VISION_OUTPUT_COST', '2.50'))
GROK_IMAGE_OUTPUT_COST = float(os.getenv('GROK_IMAGE_OUTPUT_COST', '0.04'))
GROK_TOOL_COST = float(os.getenv('GROK_TOOL_COST', '5.00'))

DB_PATH = os.getenv('CONVERSATION_DB_PATH', 'data/conversation_history.db')
CONVERSATION_RETENTION_HOURS = int(os.getenv('CONVERSATION_RETENTION_HOURS', '24'))
PERSONA_STORE_PATH = os.getenv('PERSONA_STORE_PATH', 'data/personas.json')
