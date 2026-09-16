# Gronk Discord Bot

Gronk is a Discord bot powered by xAI’s Grok API. Mention the bot or reply to one of its messages to ask questions, analyze images and documents, search the web, generate images, and explore Discord history.

## Features

- Grok text, vision, document analysis, and image generation
- Live web search, with optional X search and code execution
- Conversation memory for replies and threads
- Natural-language Discord history search with message citations
- Reusable, channel-specific personas
- Configurable usage-cost estimates

## Requirements

- Python 3.11+
- A Discord bot token
- An xAI API key (API usage is billed by xAI)

## Setup

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications). Enable the Message Content, Server Members, and Presence intents, then invite it with permission to view channels, read history, send messages, embed links, and attach files.
2. Create an [xAI API key](https://x.ai/api).
3. Configure and run the bot:

   ```powershell
   Copy-Item .env.example .env
   # Edit .env and set DISCORD_TOKEN and XAI_API_KEY
   python -m pip install -r requirements.txt
   python main.py
   ```

Conversation data is stored in `data/conversation_history.db`; personas are stored in `data/personas.json` by default.

## Configuration

`.env.example` contains all available settings. The most useful options are:

```dotenv
GROK_TEXT_MODEL=grok-4.3
GROK_VISION_MODEL=grok-4.3
GROK_DOCUMENT_MODEL=grok-4.3
GROK_IMAGE_MODEL=grok-imagine-image-2.0
TIMEZONE=America/Chicago
ENABLE_WEB_SEARCH=true
ENABLE_X_SEARCH=false
ENABLE_CODE_EXECUTION=false
ENABLE_NL_HISTORY_SEARCH=true
```

Set `ENABLE_WEB_SEARCH`, `ENABLE_X_SEARCH`, or `ENABLE_CODE_EXECUTION` to `false` to disable those features. Adjust the history limits and pricing variables in `.env` as needed.

## Usage

```text
@Gronk explain this
@Gronk summarize the attached PDF
@Gronk generate an image of a mountain cabin at sunset
@Gronk who mentioned Python most in this channel recently?
```

You can also attach JPEG, PNG, or WebP images, upload supported documents (`.pdf`, `.txt`, `.md`, `.csv`, `.json`, and common code files), or reply to a previous Gronk message to continue the conversation.

## Docker

```sh
docker build -t gronk-bot .
docker run --env-file .env -v "$(pwd)/data:/app/data" gronk-bot
```

## Testing

Run the test suite with:

```powershell
python -m pytest
```

The NLP routing helper can also be checked directly:

```powershell
python test_nl_detection.py
```

See [x.ai/api](https://x.ai/api) for current model and pricing information.
