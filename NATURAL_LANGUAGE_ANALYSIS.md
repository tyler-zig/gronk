# Natural Language Discord History Analysis

## Overview

This feature enables users to ask Gronk questions about Discord message history using natural language, without needing to use the explicit `!search` command.

## Examples

### ✅ Discord History Queries (Auto-detected)
```
@Gronk who talks about Python the most in the past month?
@Gronk what have we discussed about AI recently?
@Gronk summarize our conversations from last week
@Gronk @john what are his opinions on crypto?
@Gronk who mentions gaming the most here?
@Gronk what did people say in this channel about bots?
```

### ❌ General Knowledge Queries (Normal Grok response)
```
@Gronk who was the smartest person in history?
@Gronk what have scientists said about climate change?
@Gronk what did Elon Musk tweet recently?
@Gronk who is the best programmer in the world?
```

## How It Works

### 1. Hybrid Detection System

The bot uses a **three-tier detection system** to determine if a query is about Discord history or general knowledge:

#### Tier 1: Fast Keyword Detection (No API Cost)
- **User mentions**: If a user is @mentioned, it's definitely Discord
- **Discord scope keywords**: "here", "in this channel", "this server"
- **General indicators**: "in history", "in the world", "on twitter", "in the news"

#### Tier 2: Pattern Scoring (No API Cost)
Analyzes multiple signals and assigns points:
- **Discord pronouns** (+2): "we", "us", "our"
- **Temporal + Analysis** (+2): "past month" + "who talks"
- **Activity verbs** (+1): "posted", "messaged", "said here"

Score thresholds:
- **≥3 points**: Discord search
- **1-2 points**: Ambiguous, use Grok classification
- **0 points**: General query

#### Tier 3: Grok Classification (Small API Cost)
For ambiguous cases (score 1-2), uses Grok to classify:
```
User query: "who talks about Python the most?"
Grok: "DISCORD" or "GENERAL"
```
Cost: ~$0.0001 per classification

### 2. Parameter Extraction

When Discord search is detected, the bot automatically extracts:

#### Time Period
Maps natural language to message scan limits:
- "past month" / "30 days" → 5,000 messages
- "past week" / "7 days" → 2,000 messages
- "past day" / "today" → 500 messages
- "recently" → 1,000 messages
- "past year" → 10,000 messages

#### Keywords
Extracts topic from patterns:
- "about Python" → keyword: "python"
- "regarding AI" → keyword: "ai"
- "discussed crypto" → keyword: "crypto"

#### Target User
If a user is mentioned, searches only their messages.

### 3. Discord History Search

Once detected, performs the same analysis as `!search`:
1. Scans Discord message history (filtered by time/keyword/user)
2. Collects relevant messages
3. Sends to Grok for analysis
4. Returns results with clickable citations

## Configuration

### Enable/Disable Feature

In `.env`:
```bash
# Enable natural language Discord history analysis (default: true)
ENABLE_NL_HISTORY_SEARCH=true
```

Set to `false` to disable and require explicit `!search` command.

### Adjust Scan Limits

```bash
# Maximum messages to scan for keyword searches (default: 10000)
MAX_KEYWORD_SCAN=10000
```

## Implementation Details

### New Functions

1. **`should_search_discord_history(message_content, has_mentions)`**
   - Main detection function
   - Returns: `(should_search: bool, time_limit: int, keywords: str)`
   - Implements 3-tier detection system

2. **`extract_time_period(content_lower)`**
   - Parses natural language time expressions
   - Returns message count limit

3. **`extract_keywords(content_lower)`**
   - Extracts topic keywords from query
   - Returns keyword string for filtering

4. **`classify_with_grok(message_content)`**
   - Uses Grok API to classify ambiguous queries
   - Returns `True` for Discord, `False` for general

5. **`perform_discord_history_search(...)`**
   - Executes the actual Discord search and analysis
   - Reuses search logic from `!search` command

### Integration Point

In `on_message()` handler, before normal response:
```python
if ENABLE_NL_HISTORY_SEARCH:
    target_user = message.mentions[0] if message.mentions else None
    should_search, time_limit, keywords = await should_search_discord_history(prompt, target_user is not None)
    
    if should_search:
        await perform_discord_history_search(...)
        return  # Don't process as normal query
```

## Performance Considerations

### Fast Path (90% of queries)
- Keyword detection: Instant
- Pattern scoring: <1ms
- No API calls for clear Discord/general queries

### Slow Path (10% of queries)
- Grok classification: 100-300ms
- Cost: ~$0.0001 per ambiguous query
- Only triggered for borderline cases

### Discord Search (When detected)
- Message scanning: 1-30 seconds (depends on `MAX_KEYWORD_SCAN`)
- Grok analysis: 2-5 seconds
- Total cost: $0.001-0.01 per search (depends on message count)

## Testing

Run `test_nl_detection.py` to verify detection logic:
```bash
python test_nl_detection.py
```

Sample output:
```
✅ DISCORD - Query: who talks about Python the most in the past month?
✅ DISCORD - Query: what have we discussed about AI recently?
❌ GENERAL - Query: who was the smartest person in history?
⚠️ AMBIGUOUS - Query: summarize news from last week
```

## Edge Cases

### Handled
- ✅ User mentions bypass all detection
- ✅ Scope keywords ("here", "this channel") trigger Discord
- ✅ General indicators ("in history", "in the world") prevent Discord
- ✅ Ambiguous queries classified by Grok

### Known Limitations
- ⚠️ "summarize news from last week" - Could be channel news or world news (Grok decides)
- ⚠️ "who talks about X the most" - Without location/time, could be Discord or world (Grok decides)
- ⚠️ Very creative phrasings might not be detected (fallback: use `!search`)

## Future Enhancements

Potential improvements:
1. **Learn from user corrections** - If user says "no, I meant Discord", train on pattern
2. **Per-server configuration** - Some servers might prefer always Discord, others general
3. **Confidence scores** - Show "I think you're asking about Discord history (85% confident)"
4. **Multi-channel search** - "what have we discussed across all channels?"
5. **Date range parsing** - "between January and March"
6. **User group queries** - "what have @role members discussed?"

## Cost Analysis

### Per Query Breakdown

**Discord search detected immediately** (user mention, scope keyword):
- Classification: $0 (skipped)
- Search + Analysis: ~$0.002-0.01
- Total: ~$0.002-0.01

**Ambiguous query** (needs Grok classification):
- Classification: ~$0.0001
- Search + Analysis (if Discord): ~$0.002-0.01
- Total: ~$0.0001-0.01

**General query**:
- Classification: $0 (skipped)
- Normal response: ~$0.0001-0.001
- Total: ~$0.0001-0.001

### Cost Savings vs Always Searching

Without NL detection, every query would need Discord search, wasting:
- API calls on general questions
- Time scanning messages unnecessarily
- User confusion about why bot is slow

With NL detection:
- 90% of queries route correctly instantly
- 10% use cheap classification ($0.0001)
- Net savings: ~50-90% on misdirected searches

## Troubleshooting

### Bot searches Discord when I ask general questions
- Check for Discord indicators in your query ("we", "here", "this channel")
- Try rephrasing with world context ("in history", "globally")
- Use more specific phrasing ("in the world" vs "here")

### Bot doesn't search Discord when I want it to
- Add Discord indicators: "here", "in this channel", "what have WE discussed"
- Mention the user: `@Gronk @john what did he say?`
- Use explicit `!search` command for full control

### How to force Discord search?
Use the explicit `!search` command:
```
!search who talks about Python the most?
```

### How to force general query?
Add world context indicators:
```
@Gronk who is the best Python programmer in the world?
```
