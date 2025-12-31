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
- 🧠 **Natural Language History Analysis**: Ask questions about Discord history naturally
  - "who talks about Python the most in the past month?"
  - "what have we discussed about AI recently?"
  - "summarize our conversations from last week"
  - Automatically detects when to search Discord vs. general questions
- 🖼️ **Image Analysis**: Upload images or paste image URLs for vision analysis
- 📄 **Document Analysis**: Upload PDFs, DOCX, or TXT files for Grok-powered answers (files are sent directly to Grok via the files API)
- 🔍 **Live Web Search**: Real-time web searches with automatic citations
- 💬 **Conversation Memory (Memory Bank)**: Persistent SQLite storage remembers full conversation threads and acts as a memory bank
  - Stores every user query and bot response for context and follow-up
  - Automatic cleanup of old conversations (configurable retention period)
  - Survives bot restarts
  - Thread-aware context tracking
  - Used for follow-up questions and context-aware responses
- 💵 **Cost Transparency**: Shows exact cost per request including search
- 🌍 **Timezone Support**: Configurable timezone for accurate timestamps

## Requirements

### System Requirements
- **Python 3.11 or higher** (tested on 3.11+)
- **pip** (Python package manager)
- **Internet connection** (for API calls to xAI and Discord)

### API Keys Required
- **Discord Bot Token** (free - from Discord Developer Portal)
- **xAI API Key** (paid - from https://x.ai/api)

### Python Dependencies
All dependencies are listed in `requirements.txt`:
- `discord.py` - Discord bot framework
- `openai` - OpenAI-compatible client for xAI Grok API
- `python-dotenv` - Environment variable management
- `pytz` - Timezone handling for accurate timestamps
- `spacy` - Advanced NLP for entity and topic extraction
- `torch` - Required for transformer-based intent classification
- `transformers` - Hugging Face zero-shot intent classification

### Optional
- **Docker** - For containerized deployment (includes all NLP dependencies and spaCy model)
- **Git** - For cloning the repository and version control

## Advanced NLP Features (NEW!)
-
## Document Support (NEW!)

You can now upload PDF, DOCX, or TXT files as Discord attachments when mentioning the bot or replying to it. The bot will upload these files directly to Grok via the files API and include them in the analysis. This enables:

- 📄 **PDF, DOCX, TXT support**: Ask questions about the contents of attached documents
- 🔗 **Multi-file support**: Attach multiple supported documents in a single message
- 🚫 **Unsupported files**: Other file types are ignored (user is notified if only unsupported files are attached)

**Example Usage:**
```
@Gronk summarize the attached PDF
@Gronk what are the main points in this DOCX?
@Gronk extract all TODOs from the attached .txt file
```

**Supported file types:**
- PDF (.pdf)
- Word Document (.docx)
- Plain Text (.txt)

**How it works:**
- The bot detects supported document attachments
- Files are uploaded to Grok's files API
- The file references are included in the Grok chat completion request
- The bot responds with answers based on the document content

The bot now uses state-of-the-art NLP for deeper understanding of queries:

- 🏷️ **Entity Extraction**: Uses spaCy to extract people, dates, organizations, and topics from queries
- 🧠 **Topic Detection**: Identifies key topics and noun phrases for more accurate search and filtering
- 🎯 **Intent Classification**: Uses Hugging Face transformers (zero-shot) to classify query intent (e.g., Discord history, general knowledge, user search, topic summary)
- 🔬 **Multi-word & Contextual Keywords**: Supports complex queries like "What did @john say about crypto between January and March?"
- 🌐 **Multilingual Ready**: spaCy and transformers can be extended for other languages

**Example Queries:**
```
Who mentioned Python and AI the most in the last year?
What did @john say about crypto between January and March?
Summarize our discussions about machine learning in this channel.
Who are the most active users here in the past week?
What topics did @role members talk about last Friday?
Who is the most famous AI researcher in the world?
Summarize news from last week.
```

**Testing Advanced NLP:**
Run the test script to see entity, topic, and intent extraction:
```powershell
python test_advanced_nlp.py "Who talked about AI and crypto in the last year?"
```
Output will show extracted entities, topics, and intent.

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
  GROK_IMAGE_MODEL=grok-2-image-1212
   
   # Timezone Configuration (Optional - defaults to America/Chicago)
   # Use IANA timezone names: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
   # Examples: America/New_York, America/Los_Angeles, Europe/London, Asia/Tokyo
   TIMEZONE=America/Chicago
   
   # Search Configuration (Optional - defaults shown)
   ENABLE_WEB_SEARCH=true
   MAX_SEARCH_RESULTS=3
   MAX_KEYWORD_SCAN=10000
   MAX_MESSAGES_ANALYZED=500
   ENABLE_NL_HISTORY_SEARCH=true
   
  # Pricing Configuration (Optional - defaults based on current xAI pricing)
  GROK_TEXT_INPUT_COST=0.20
  GROK_TEXT_OUTPUT_COST=0.50
  GROK_TEXT_CACHED_COST=0.05
  GROK_VISION_INPUT_COST=2.00
  GROK_VISION_OUTPUT_COST=10.00
  GROK_IMAGE_OUTPUT_COST=0.50
  GROK_SEARCH_COST=25.00
   ```
   
   **Configuration Options:**
   - **GROK_TEXT_MODEL**: Model used for text-only responses (default: grok-4-fast)
  - **GROK_VISION_MODEL**: Model used when analyzing images (default: grok-2-vision-1212)
  - **GROK_IMAGE_MODEL**: Model used for image generation (default: grok-2-image-1212)
   - **TIMEZONE**: Timezone for message timestamps (default: America/Chicago)
   - **ENABLE_WEB_SEARCH**: Enable/disable live web search (default: true)
   - **MAX_SEARCH_RESULTS**: Number of web sources to fetch, 1-10 (default: 3, higher = more cost)
   - **MAX_KEYWORD_SCAN**: Maximum messages to scan for keyword searches (default: 10,000)
   - **MAX_MESSAGES_ANALYZED**: Maximum messages sent to Grok for analysis (default: 500, higher = better analysis but more cost)
   - **ENABLE_NL_HISTORY_SEARCH**: Enable natural language history detection (default: true)
  - **Pricing variables**: Cost per 1M tokens (text/vision input/output, cached), per image, and per 1K search sources

### 5. Install and Run

1. Install dependencies:
  ```powershell
  pip install -r requirements.txt
  ```
  This will install all required NLP libraries (spaCy, torch, transformers). The first run will download the spaCy English model automatically.

2. Run the bot:
  ```powershell
  python main.py
  ```
  The bot will be online in your Discord server.

3. (Optional) Test advanced NLP extraction:
  ```powershell
  python test_advanced_nlp.py "Who talked about AI and crypto in the last year?"
  ```
  This will print extracted entities, topics, and intent for your query.

### Docker Support

The Docker image now includes all advanced NLP dependencies and downloads the spaCy English model at build time. To build and run:
```sh
docker build -t gronk-bot .
docker run --env-file .env gronk-bot
```
This ensures all NLP features work out of the box in containers.

## Usage


### Image Generation (NEW!)

You can generate AI images directly in Discord using the `!imagine` command:

**Usage:**
```
!imagine <your prompt here>
```

**Example:**
```
!imagine a futuristic city skyline at sunset, vibrant colors, ultra detailed
```

- The bot will reply with an AI-generated image based on your prompt.
- Click "Generate More Versions" to get 4 new variations of your prompt (costs scale per image).
- To adjust or iterate, reply to the image embed with a new prompt or additional details—the bot will combine your new text with the original prompt for the next generation.

**Cost:** Each generated image is billed at the rate set in your `.env` (`GROK_IMAGE_OUTPUT_COST`, default: $0.50 per image). Generating more versions multiplies the cost (e.g., 4 images = $2.00).

**Supported Models:** Uses the model set in `GROK_IMAGE_MODEL` (default: `grok-2-image-1212`).

**Note:** Image generation requires an xAI API key with image generation enabled. See the [Cost Information](#cost-information) section for details.

---

### Basic Interaction
- **Mention the bot**: `@Gronk what's the weather?`
- **Reply to Gronk**: Reply to any of Gronk's messages without mentioning (conversation memory)
- **Upload images**: Attach images or paste image URLs for visual analysis
- **Reply chains**: Gronk sees full conversation context in reply threads

### Natural Language History Analysis (NEW! 🧠)

Simply mention Gronk and ask questions about your Discord history naturally:

```
@Gronk who talks about Python the most in the past month?
@Gronk what have we discussed about AI recently?
@Gronk summarize our conversations from last week
@Gronk @john what are his opinions on crypto?
@Gronk who mentions gaming the most here?
```

**How it works:**
- 🎯 **Smart Detection**: Automatically determines if you're asking about Discord history or general questions
- 🔍 **Hybrid Classification**: Uses keyword patterns + Grok AI classification for ambiguous queries
- ⏱️ **Time Recognition**: Recognizes temporal phrases like "past month", "last week", "recently"
- 🏷️ **Topic Extraction**: Detects keywords like "about Python", "regarding AI", etc. for filtering
- 📊 **Same Power**: Uses the same analysis engine as `!search` with citations and timestamps
- 🚀 **Efficient Scanning**: Automatically scans only `MAX_MESSAGES_ANALYZED` for general queries (fast!)

**What triggers Discord search:**
- ✅ Mentioning a user: `@Gronk @john what did he say?`
- ✅ Discord scope words: "here", "in this channel", "this server"
- ✅ Discord pronouns: "we", "us", "our"
- ✅ Time + analysis patterns: "who talked about X recently?"
- ✅ Activity verbs: "who posted about X?"

**What stays as general queries:**
- ❌ General knowledge: `@Gronk who invented Python?`
- ❌ World context: `@Gronk what's happening in the news?`
- ❌ No Discord indicators: `@Gronk explain quantum computing`

**Configuration:**
- Set `ENABLE_NL_HISTORY_SEARCH=false` in `.env` to disable this feature
- Fallback to explicit `!search` command if disabled

### Search Command

**`!search [options] <query>`** - Explicit search command for advanced control

**Basic Usage:**
```
!search what did people say about AI?              # Search all users
!search @john what are his thoughts on Python?     # Search specific user
```

**Advanced Options:**
```
!search @user 5000 query                           # Specify message limit (used with keywords)
!search keyword:Python summarize Python discussions # Pre-filter by keyword (scans more history)
!search @user keyword:bot 2000 what about bots?    # Combine user, keyword, and limit
```

**Note:** Without a keyword filter, the bot automatically limits scanning to `MAX_MESSAGES_ANALYZED` for efficiency, since that's all it can send to Grok anyway. Use keyword filters to search deeper history.

**Features:**
- 🔗 **Inline Citations**: Grok cites specific messages as `[#5]` which become clickable links
- 📊 **Progress Updates**: Real-time scan progress for large searches (updates every 2000 messages)
- 🔄 **Follow-up Queries**: Reply to search results to ask follow-up questions with same context
- 🎯 **Range Citations**: Supports ranges like `[#58-59]` or `[#68-70]` for multiple messages
- 😀 **Emoji Support**: Custom Discord emojis are preserved and rendered correctly
- 🕐 **Smart Timestamps**: All timestamps converted to your configured timezone

**Search Behavior:**
- **General search (no keyword)**: Scans only up to `MAX_MESSAGES_ANALYZED` (default: 500-1000)
  - Fast and efficient since we only scan what can be analyzed
  - Perfect for recent history analysis
- **Keyword search**: Scans up to `MAX_KEYWORD_SCAN` (default: 10,000) to find matching messages
  - ⚠️ **Performance Warning**: Keyword searches can take 10-30+ seconds depending on `MAX_KEYWORD_SCAN` value
  - With `MAX_KEYWORD_SCAN=10000`: ~10-20 seconds
  - With `MAX_KEYWORD_SCAN=25000`: ~30-60 seconds
  - With `MAX_KEYWORD_SCAN=50000`: ~60-120+ seconds
  - Progress updates shown every 2000 messages to indicate the bot is still working
  - Reduce `MAX_KEYWORD_SCAN` in `.env` for faster searches at the cost of less history coverage
- **Analysis limit**: Only the most recent `MAX_MESSAGES_ANALYZED` messages are sent to Grok (default: 500)
  - Increase for deeper analysis: `MAX_MESSAGES_ANALYZED=1000` or even higher
  - 100 msgs ≈ $0.002-0.005, 500 msgs ≈ $0.01-0.025, 1000 msgs ≈ $0.02-0.05
  - This is the actual limit on what Grok sees, not what we scan
- **Message length**: Each message truncated to 300 characters in analysis
- **Bot filtering**: Bot messages excluded from channel-wide searches
- **Response splitting**: Automatic splitting for long responses with citation preservation

### Cost Information
- **Grok-4-fast**: $0.20/1M input tokens, $0.50/1M output tokens
- **Grok-2-vision**: $2.00/1M input tokens, $10.00/1M output tokens
- **Grok-2-image-1212**: $0.50 per image (update as needed)
- **Web Search**: $25.00 per 1,000 sources (currently limited to 3 sources per search)
- **Cached tokens**: $0.05/1M (75% discount on repeated context)

> **Note:** Pricing and models are subject to change by xAI. Check [x.ai/api](https://x.ai/api) for current pricing. To update models, edit `GROK_TEXT_MODEL`, `GROK_VISION_MODEL`, and `GROK_IMAGE_MODEL` in your `.env` file. To adjust web search depth, modify `MAX_SEARCH_RESULTS` (higher values increase costs).

> **Cost Calculations:** The bot displays estimated costs on each response card based on pricing values configured in your `.env` file. These calculations use the pricing rates shown above by default. If xAI changes their pricing, simply update the `GROK_*_COST` variables in your `.env` file to reflect the new rates.

## Architecture

- **Models**: Grok-4-fast (text), Grok-2-vision-1212 (images)
- **Web Search**: Live Search API with auto mode (3 sources max by default)
- **Natural Language Detection**: 3-tier hybrid system (keywords → pattern scoring → Grok classification)
- **Message Search**: Optimized scanning with progress tracking, citation linking, and timezone conversion
- **Memory (Memory Bank)**: SQLite persistent storage with thread-aware context
  - Stores every user query and bot response (conversation history) as a memory bank
  - Used for follow-up questions, context-aware responses, and persistent memory
  - Traverses full reply chains (up to 10 messages deep) to build complete thread context
  - Automatic cleanup of conversations older than 24 hours (configurable)
  - Survives bot restarts and container rebuilds
  - Database persisted via volume mounts in Docker deployments
  - No semantic search or vector memory (yet) – all memory is message-based
- **Image Support**: JPEG, PNG, WebP (attachments, URLs, embeds)
- **Context**: Reply chain traversal + time-aware message history (2-minute window)
- **Citation System**: Selective citations (3-6 per response) with individual message linking `[#N]` (no ranges)
- **Timezone**: pytz-based timezone conversion with automatic DST handling
- **Query Routing**: 90% instant keyword detection, 10% Grok-assisted classification for ambiguous cases

## Troubleshooting

### General Issues
- **Bot doesn't respond**: Check that Message Content Intent is enabled in Discord Developer Portal
- **Image errors**: Only JPEG, PNG, and WebP formats are supported
- **High costs**: Reduce `MAX_SEARCH_RESULTS` or disable `ENABLE_WEB_SEARCH` in `.env`
- **Slow keyword searches**: Reduce `MAX_KEYWORD_SCAN` in `.env` (default: 10,000)
- **Wrong timestamps**: Set correct `TIMEZONE` in `.env` using IANA timezone names
- **Citations not linking**: Ensure messages are in the analyzed set (limited by `MAX_MESSAGES_ANALYZED`)
- **Embed size errors**: Automatically handled by splitting into multiple embeds
- **Want more detailed analysis**: Increase `MAX_MESSAGES_ANALYZED` in `.env` (costs scale linearly)

### Natural Language History Analysis
- **Bot searches Discord when I ask general questions**: 
  - Check your phrasing for Discord indicators ("we", "here", "this channel")
  - Add world context: "in history", "globally", "in the world"
  - Example: Change "who is the smartest?" to "who is the smartest in history?"
  
- **Bot doesn't search Discord when I want it to**:
  - Add Discord indicators: "here", "in this channel", "what have WE discussed"
  - Mention a user: `@Gronk @john what did he say?`
  - Use explicit `!search` command for full control
  
- **Disable natural language detection**:
  - Set `ENABLE_NL_HISTORY_SEARCH=false` in `.env`
  - All history searches will require explicit `!search` command

### Testing
Run the test script to verify natural language detection:
```powershell
python test_nl_detection.py
```