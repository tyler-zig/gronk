# Grok Discord Bot

A Discord bot that integrates with xAI's Grok API to answer questions, with advanced message search, image support, live web search, and conversation memory.

> **⚠️ Important:** This bot requires an xAI Grok API key, which is a **paid service**. You will be charged based on token usage and web search requests. See the [Cost Information](#cost-information) section below for pricing details.

> **🎨 Vibecoded Notice:** This project was developed entirely through AI-assisted coding (even this readme). No formal testing, validation, or quality assurance was performed. Features may break unexpectedly, edge cases are probably unhandled, and bugs are likely lurking. Use at your own risk and expect the occasional chaos. PRs welcome if you find something broken! 🚀

## Features

- 🤖 **AI Responses**: Powered by Grok-4-fast for text and Grok-2-vision for images
- 🔎 **Advanced Message Search**: Search and analyze message history with inline citations
  - Search by user or entire channel
  - Keyword filtering for targeted searches
  - Clickable citations linking directly to referenced messages
  - Real-time progress updates for large scans
- 🖼️ **Image Analysis**: Upload images or paste image URLs for vision analysis
- 🔍 **Live Web Search**: Real-time web searches with automatic citations
- 💬 **Conversation Memory**: Remembers context when you reply to Gronk
-  **Cost Transparency**: Shows exact cost per request including search
- 🌍 **Timezone Support**: Configurable timezone for accurate timestamps

## Requirements

- Python 3.11 or higher
- pip (Python package manager)

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** and give it a name (e.g., "Gronk")
3. Go to the **"Bot"** tab in the left sidebar
4. Click **"Add Bot"** and confirm
5. Under the bot's username, click **"Reset Token"** and copy your bot token (save this for later)
6. Scroll down to **"Privileged Gateway Intents"** and enable:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
7. Click **"Save Changes"**

### 2. Invite the Bot to Your Server

1. In the Discord Developer Portal, go to the **"OAuth2"** tab
2. Click on **"URL Generator"** in the left sidebar
3. Under **"Scopes"**, select:
   - ✅ `bot`
4. Under **"Bot Permissions"**, select:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Send Messages in Threads
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Read Message History
   - ✅ Mention Everyone (optional, for @mentions)
   - ✅ Add Reactions (optional)
   - ✅ Use Slash Commands (optional)
5. Copy the generated URL at the bottom and open it in your browser
6. Select the server you want to add the bot to and click **"Authorize"**

### 3. Get an xAI API Key

1. Go to https://x.ai/api
2. Sign up or log in to your xAI account
3. Navigate to the API Keys section
4. Create a new API key and copy it (save this for later)

### 4. Configure the Bot

1. Copy `.env.example` to `.env`:
   ```powershell
   cp .env.example .env
   ```
2. Edit `.env` and add your tokens:
   ```
   DISCORD_TOKEN=your_discord_token_here
   XAI_API_KEY=your_xai_api_key_here
   ```
3. **(Optional)** Customize model, search, timezone, and pricing settings:
   ```
   # Model Configuration (Optional - defaults shown)
   GROK_TEXT_MODEL=grok-4-fast
   GROK_VISION_MODEL=grok-2-vision-1212
   
   # Timezone Configuration (Optional - defaults to America/Chicago)
   # Use IANA timezone names: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
   # Examples: America/New_York, America/Los_Angeles, Europe/London, Asia/Tokyo
   TIMEZONE=America/Chicago
   
   # Search Configuration (Optional - defaults shown)
   ENABLE_WEB_SEARCH=true
   MAX_SEARCH_RESULTS=3
   # Maximum messages to scan for keyword searches (default: 10000)
   # Higher values = more thorough search but slower performance
   MAX_KEYWORD_SCAN=10000
   
   # Pricing Configuration (Optional - defaults based on current xAI pricing)
   GROK_TEXT_INPUT_COST=0.20
   GROK_TEXT_OUTPUT_COST=0.50
   GROK_TEXT_CACHED_COST=0.05
   GROK_VISION_INPUT_COST=2.00
   GROK_VISION_OUTPUT_COST=10.00
   GROK_SEARCH_COST=25.00
   ```
   - **GROK_TEXT_MODEL**: Model used for text-only responses
   - **GROK_VISION_MODEL**: Model used when analyzing images
   - **TIMEZONE**: Timezone for message timestamps (defaults to Central Time)
   - **ENABLE_WEB_SEARCH**: Enable/disable live web search (true/false)
   - **MAX_SEARCH_RESULTS**: Number of web sources to fetch (1-10, higher = more cost)
   - **MAX_KEYWORD_SCAN**: Maximum messages to scan for keyword searches (affects performance)
   - **Pricing variables**: Cost per 1M tokens (text/vision input/output, cached) and per 1K search sources

### 5. Install and Run

1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Run the bot:
   ```powershell
   python main.py
   ```
3. The bot should now be online in your Discord server!

## Usage

### Basic Interaction
- **Mention the bot**: `@Gronk what's the weather?`
- **Reply to Gronk**: Reply to any of Gronk's messages without mentioning (conversation memory)
- **Upload images**: Attach images or paste image URLs for visual analysis
- **Reply chains**: Gronk sees full conversation context in reply threads

### Search Command

**`!search [options] <query>`** - Search and analyze message history

**Basic Usage:**
```
!search what did people say about AI?              # Search all users
!search @john what are his thoughts on Python?     # Search specific user
```

**Advanced Options:**
```
!search @user 5000 query                           # Specify message limit (default: 1000)
!search keyword:Python summarize Python discussions # Pre-filter by keyword
!search @user keyword:bot 2000 what about bots?    # Combine user, keyword, and limit
```

**Features:**
- 🔗 **Inline Citations**: Grok cites specific messages as `[#5]` which become clickable links
- 📊 **Progress Updates**: Real-time scan progress for large searches (updates every 2000 messages)
- 🔄 **Follow-up Queries**: Reply to search results to ask follow-up questions with same context
- 🎯 **Range Citations**: Supports ranges like `[#58-59]` or `[#68-70]` for multiple messages
- 😀 **Emoji Support**: Custom Discord emojis are preserved and rendered correctly
- 🕐 **Smart Timestamps**: All timestamps converted to your configured timezone

**Search Behavior:**
- **Regular search**: Scans last N messages (default: 1000, configurable per query)
- **Keyword search**: Scans entire channel history up to `MAX_KEYWORD_SCAN` (default: 10,000)
- **Analysis limit**: Analyzes up to 100 most recent messages (token limit)
- **Message length**: Each message truncated to 300 characters in analysis
- **Bot filtering**: Bot messages excluded from channel-wide searches
- **Response splitting**: Automatic splitting for long responses with citation preservation

### Cost Information
- **Grok-4-fast**: $0.20/1M input tokens, $0.50/1M output tokens
- **Grok-2-vision**: $2.00/1M input tokens, $10.00/1M output tokens
- **Web Search**: $25.00 per 1,000 sources (currently limited to 3 sources per search)
- **Cached tokens**: $0.05/1M (75% discount on repeated context)

> **Note:** Pricing and models are subject to change by xAI. Check [x.ai/api](https://x.ai/api) for current pricing. To update models, edit `GROK_TEXT_MODEL` and `GROK_VISION_MODEL` in your `.env` file. To adjust web search depth, modify `MAX_SEARCH_RESULTS` (higher values increase costs).

> **Cost Calculations:** The bot displays estimated costs on each response card based on pricing values configured in your `.env` file. These calculations use the pricing rates shown above by default. If xAI changes their pricing, simply update the `GROK_*_COST` variables in your `.env` file to reflect the new rates.

## Architecture

- **Models**: Grok-4-fast (text), Grok-2-vision-1212 (images)
- **Web Search**: Live Search API with auto mode (3 sources max by default)
- **Message Search**: Optimized scanning with progress tracking, citation linking, and timezone conversion
- **Memory**: Per-user, per-channel conversation history (last 10 messages)
- **Image Support**: JPEG, PNG, WebP (attachments, URLs, embeds)
- **Context**: Reply chain traversal + time-aware message history (2-minute window)
- **Citation System**: Regex-based detection of individual citations `[#N]` and ranges `[#N-M]` with Discord link conversion
- **Timezone**: pytz-based timezone conversion with automatic DST handling

## Troubleshooting

- **Bot doesn't respond**: Check that Message Content Intent is enabled in Discord Developer Portal
- **Image errors**: Only JPEG, PNG, and WebP formats are supported
- **High costs**: Reduce `MAX_SEARCH_RESULTS` or disable `ENABLE_WEB_SEARCH` in `.env`
- **Slow keyword searches**: Reduce `MAX_KEYWORD_SCAN` in `.env` (default: 10,000)
- **Wrong timestamps**: Set correct `TIMEZONE` in `.env` using IANA timezone names
- **Citations not linking**: Ensure messages are in the analyzed set (last 100 messages)
- **Embed size errors**: Automatically handled by splitting into multiple embeds