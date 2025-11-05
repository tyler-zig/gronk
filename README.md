# Grok Discord Bot

A Discord bot that integrates with xAI's Grok API to answer questions, with image support, live web search, and conversation memory.

## Features

- 🤖 **AI Responses**: Powered by Grok-4-fast for text and Grok-2-vision for images
- 🖼️ **Image Analysis**: Upload images or paste image URLs for vision analysis
- 🔍 **Live Web Search**: Real-time web searches with automatic citations
- 💬 **Conversation Memory**: Remembers context when you reply to Grok
- 📊 **Usage Tracking**: `!usage` command shows token usage and costs
- 🔎 **Message Search**: `!search` command to analyze message history
- 💵 **Cost Transparency**: Shows exact cost per request including search

## Requirements

- Python 3.11 or higher
- pip (Python package manager)

## Setup

1. Create a Discord bot at https://discord.com/developers/applications
   - Enable all Privileged Gateway Intents (Presence, Server Members, Message Content)
   - Get the bot token
2. Get an xAI API key at https://x.ai/api-keys
3. Copy `.env.example` to `.env` and fill in your tokens:
   ```
   DISCORD_TOKEN=your_discord_token_here
   XAI_API_KEY=your_xai_api_key_here
   ```
4. Install dependencies: `pip install -r requirements.txt`
5. Run the bot: `python main.py`

## Usage

### Basic Interaction
- **Mention the bot**: `@Gronk what's the weather?`
- **Reply to Gronk**: Reply to any of Gronk's messages without mentioning (conversation memory)
- **Upload images**: Attach images or paste image URLs for visual analysis
- **Reply chains**: Gronk sees full conversation context in reply threads

### Commands
- **`!usage`**: Check token usage statistics and costs
- **`!search @user [keywords] <query>`**: Search a user's message history
  - Example: `!search @john keyword:python what did he say about testing?`
  - Omit username for channel-wide search

### Cost Information
- **Grok-4-fast**: $0.20/1M input tokens, $0.50/1M output tokens
- **Grok-2-vision**: $2.00/1M input tokens, $10.00/1M output tokens
- **Web Search**: $25.00 per 1,000 sources (currently limited to 3 sources per search)
- **Cached tokens**: $0.05/1M (75% discount on repeated context)

## Architecture

- **Models**: Grok-4-fast (text), Grok-2-vision-1212 (images)
- **Search**: Live Search API with auto mode (3 sources max)
- **Memory**: Per-user, per-channel conversation history (last 10 messages)
- **Image Support**: JPEG, PNG, WebP (attachments, URLs, embeds)
- **Context**: Reply chain traversal + time-aware message history (2-minute window)

## Troubleshooting

- **Bot doesn't respond**: Check that Message Content Intent is enabled in Discord Developer Portal
- **Image errors**: Only JPEG, PNG, and WebP formats are supported
- **High costs**: Reduce `max_search_results` in `main.py` or set search mode to `"never"`