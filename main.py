import discord
from discord.ext import commands
import os
from openai import OpenAI
from dotenv import load_dotenv
import logging
import re
from typing import Optional
from datetime import timezone
import pytz

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GrokBot')

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
XAI_KEY = os.getenv('XAI_API_KEY')

# Timezone for display (configurable, defaults to Central Time)
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'America/Chicago'))

# Model configuration (with defaults)
GROK_TEXT_MODEL = os.getenv('GROK_TEXT_MODEL', 'grok-4-fast')
GROK_VISION_MODEL = os.getenv('GROK_VISION_MODEL', 'grok-2-vision-1212')

# Search configuration (with defaults)
ENABLE_WEB_SEARCH = os.getenv('ENABLE_WEB_SEARCH', 'true').lower() == 'true'
MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '3'))
MAX_KEYWORD_SCAN = int(os.getenv('MAX_KEYWORD_SCAN', '10000'))

# Pricing configuration (with defaults based on current xAI pricing)
GROK_TEXT_INPUT_COST = float(os.getenv('GROK_TEXT_INPUT_COST', '0.20'))
GROK_TEXT_OUTPUT_COST = float(os.getenv('GROK_TEXT_OUTPUT_COST', '0.50'))
GROK_TEXT_CACHED_COST = float(os.getenv('GROK_TEXT_CACHED_COST', '0.05'))
GROK_VISION_INPUT_COST = float(os.getenv('GROK_VISION_INPUT_COST', '2.00'))
GROK_VISION_OUTPUT_COST = float(os.getenv('GROK_VISION_OUTPUT_COST', '10.00'))
GROK_SEARCH_COST = float(os.getenv('GROK_SEARCH_COST', '25.00'))

client = OpenAI(api_key=XAI_KEY, base_url="https://api.x.ai/v1")

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# Track search context for follow-up queries
search_context = {}  # {channel_id: {user_id: {searched_user: User, messages: [...], query: str}}}

# Track conversation history for context awareness
conversation_history = {}  # {channel_id: {user_id: [{"role": "user/assistant", "content": str}]}}

@bot.event
async def on_ready():
    logger.info(f'Bot logged in as {bot.user} (ID: {bot.user.id})')
    logger.info(f'Connected to {len(bot.guilds)} server(s)')

@bot.command(name='search')
async def search_history(ctx, *, query_text: str):
    """Search message history in this channel
    Usage: !search query text here (searches all messages)
    Usage: !search @user query text here (searches specific user)
    Usage: !search @user 2000 query (specify message limit)
    Usage: !search keyword:Python what are discussions about Python (pre-filter by keyword)
    Example: !search who mentioned Python
    Example: !search @john tell me about his projects
    Example: !search @john 5000 what are his opinions on AI
    Example: !search keyword:bot summarize bot discussions
    """
    if not query_text:
        await ctx.reply("❌ Please provide a search query. Usage: `!search query` or `!search @user query`")
        return
    
    # Check if a user is mentioned
    target_user = None
    if ctx.message.mentions:
        target_user = ctx.message.mentions[0]
        # Remove user mention from query
        query_text = query_text.replace(f'<@{target_user.id}>', '').replace(f'<@!{target_user.id}>', '').strip()
    
    # Parse optional limit, keyword filter, and query
    limit = 1000
    keyword_filter = None
    query = query_text
    
    # Check for keyword filter
    if query_text.startswith('keyword:'):
        parts = query_text.split(None, 1)
        keyword_filter = parts[0].replace('keyword:', '').lower()
        query = parts[1] if len(parts) > 1 else ""
        if not query:
            await ctx.reply("❌ Please provide a search query after the keyword filter.")
            return
    
    # Check if first word is a number (limit)
    if query:
        parts = query.split(None, 1)
        if parts[0].isdigit():
            limit = int(parts[0])
            query = parts[1] if len(parts) > 1 else ""
            if not query:
                await ctx.reply("❌ Please provide a search query after the limit.")
                return
    
    if target_user:
        logger.info(f'Search command by {ctx.author} for user {target_user} with query: {query}, limit: {limit}, keyword: {keyword_filter}')
    else:
        logger.info(f'Search command by {ctx.author} for ALL users with query: {query}, limit: {limit}, keyword: {keyword_filter}')
    
    # Send a "searching" message
    if keyword_filter:
        # Keyword search scans entire history
        if target_user:
            searching_msg = await ctx.reply(f"🔍 Searching {target_user.mention}'s message history for keyword `{keyword_filter}`...")
        else:
            searching_msg = await ctx.reply(f"🔍 Searching channel history for keyword `{keyword_filter}`...")
    else:
        # Regular search with limit
        if target_user:
            searching_msg = await ctx.reply(f"🔍 Searching {target_user.mention}'s message history (last {limit} messages)...")
        else:
            searching_msg = await ctx.reply(f"🔍 Searching channel message history (last {limit} messages)...")
    
    try:
        # Collect messages (history returns newest first)
        collected_messages = []
        messages_scanned = 0
        last_update = 0
        
        # For keyword filtering, scan much more to find filtered results
        # Otherwise just scan a bit more than the limit
        if keyword_filter:
            # Scan up to MAX_KEYWORD_SCAN messages for keyword searches
            max_scan = MAX_KEYWORD_SCAN
        else:
            max_scan = limit + 100
        
        # Pre-compute lowercase keyword for faster comparison
        keyword_lower = keyword_filter.lower() if keyword_filter else None
        
        async for msg in ctx.channel.history(limit=max_scan):
            # Skip the search command itself immediately
            if msg.id == ctx.message.id:
                continue
            
            messages_scanned += 1
            
            # Apply filters efficiently (short-circuit evaluation)
            # Check user filter first (faster than string operations)
            if target_user and msg.author != target_user:
                continue
            
            # Check bot filter for non-targeted searches
            if not target_user and msg.author.bot:
                continue
            
            # Apply keyword filter last (most expensive operation)
            if keyword_lower and keyword_lower not in msg.content.lower():
                continue
            
            # Message passed all filters
            collected_messages.append(msg)
            
            # Update progress message every 2000 messages scanned (even less frequent)
            if messages_scanned - last_update >= 2000:
                last_update = messages_scanned
                try:
                    if keyword_filter:
                        progress_pct = int((messages_scanned / max_scan) * 100) if max_scan > 0 else 0
                        if target_user:
                            await searching_msg.edit(content=f"🔍 Searching {target_user.mention}'s message history for keyword `{keyword_filter}`... ({progress_pct}% - scanned {messages_scanned:,}, found {len(collected_messages):,})")
                        else:
                            await searching_msg.edit(content=f"🔍 Searching channel history for keyword `{keyword_filter}`... ({progress_pct}% - scanned {messages_scanned:,}, found {len(collected_messages):,})")
                    else:
                        if target_user:
                            await searching_msg.edit(content=f"🔍 Searching {target_user.mention}'s message history... (scanned {messages_scanned:,}, found {len(collected_messages):,})")
                        else:
                            await searching_msg.edit(content=f"🔍 Searching channel message history... (scanned {messages_scanned:,}, found {len(collected_messages):,})")
                except:
                    pass  # Ignore errors updating status
            
            # For non-keyword searches, stop when we have enough
            if not keyword_filter and len(collected_messages) >= limit:
                break
        
        if not collected_messages:
            if target_user:
                await searching_msg.edit(content=f"❌ No messages found from {target_user.mention} in this channel.")
            else:
                await searching_msg.edit(content=f"❌ No messages found in this channel.")
            return
        
        if target_user:
            logger.info(f'Found {len(collected_messages)} messages from {target_user}' + (f' (filtered by "{keyword_filter}")' if keyword_filter else ''))
        else:
            logger.info(f'Found {len(collected_messages)} messages from all users' + (f' (filtered by "{keyword_filter}")' if keyword_filter else ''))
        
        # Store search context for follow-ups
        if ctx.channel.id not in search_context:
            search_context[ctx.channel.id] = {}
        search_context[ctx.channel.id][ctx.author.id] = {
            'searched_user': target_user,
            'messages': collected_messages,
            'last_query': query
        }
        
        # Build context for Grok (use up to 100 messages to stay within token limits)
        # Since collected_messages is in reverse chronological order (newest first),
        # we take the first N messages (most recent) and then reverse them for chronological order
        messages_to_analyze = min(len(collected_messages), 100)
        messages_for_context = collected_messages[:messages_to_analyze]
        
        if target_user:
            context_parts = [f"Search query: {query}\n\nUser {target_user.name}'s recent messages (showing {messages_to_analyze} of {len(collected_messages)} found, from oldest to newest):\n"]
        else:
            context_parts = [f"Search query: {query}\n\nChannel messages (showing {messages_to_analyze} of {len(collected_messages)} found, from oldest to newest):\n"]
        
        # Create a mapping of message numbers to message objects for later citation linking
        # Reverse to show chronological order (oldest to newest)
        message_number_map = {}
        for i, msg in enumerate(reversed(messages_for_context), 1):
            # Convert UTC timestamp to configured timezone
            timestamp_local = msg.created_at.astimezone(TIMEZONE)
            tz_abbr = timestamp_local.strftime("%Z")  # Get timezone abbreviation (CST, CDT, etc.)
            timestamp_str = timestamp_local.strftime(f"%Y-%m-%d %H:%M {tz_abbr}")
            author_name = msg.author.name if not target_user else ""
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            message_number_map[i] = msg  # Store mapping for later
            if target_user:
                context_parts.append(f"[{i}] [{timestamp_str}] {content}")
            else:
                context_parts.append(f"[{i}] [{timestamp_str}] {author_name}: {content}")
        
        context_parts.append(f"\n\nBased on these messages, {query}")
        context_parts.append("\n\nIMPORTANT: When referencing specific messages in your answer, cite them using the format [#N] where N is the message number. For example: 'In message [#5], they mentioned...' or 'See messages [#3], [#7], and [#12] for examples.'")
        context_parts.append("\n\nNote: Custom Discord emojis appear as <:emoji_name:emoji_id>. When quoting messages with emojis, preserve this exact format.")
        tz_name = TIMEZONE.zone  # e.g., "America/Chicago"
        context_parts.append(f"\n\nNote: All timestamps are in {tz_name} timezone.")
        full_prompt = "\n".join(context_parts)
        
        # Query Grok
        async with ctx.channel.typing():
            # Build request parameters
            request_params = {
                "model": GROK_TEXT_MODEL,
                "messages": [{"role": "user", "content": full_prompt}]
            }
            
            # Add search parameters if enabled
            if ENABLE_WEB_SEARCH:
                request_params["extra_body"] = {
                    "search_parameters": {
                        "mode": "auto",
                        "max_search_results": MAX_SEARCH_RESULTS
                    }
                }
            
            completion = client.chat.completions.create(**request_params)
            
            response = completion.choices[0].message.content
            
            # Parse citations from response and extract referenced message numbers
            # Match both individual citations [#N] and ranges [#N]-[M], [#N]-M, or [#N-M]
            citation_pattern = r'\[#(\d+)\]'
            range_pattern = r'\[#(\d+)(?:\]-?\[?|-)(\d+)\]?'  # Matches [#88]-[90], [#88]-90, or [#88-90]
            
            # Find individual citations (but not those that are part of ranges)
            cited_numbers = set()
            for match in re.finditer(citation_pattern, response):
                # Check if this is part of a range by looking at context
                pos = match.start()
                # Skip if preceded by a range pattern
                if pos > 0 and response[pos-1:pos] in ['-', ']']:
                    continue
                cited_numbers.add(int(match.group(1)))
            
            # Find and expand ranges
            for match in re.finditer(range_pattern, response):
                start_num = int(match.group(1))
                end_num = int(match.group(2))
                # Add all numbers in the range
                cited_numbers.update(range(start_num, end_num + 1))
            
            logger.info(f'Found {len(cited_numbers)} cited messages: {sorted(cited_numbers)}')
            
            # Replace ranges with individual linked citations (compact format)
            def replace_range(match):
                start_num = int(match.group(1))
                end_num = int(match.group(2))
                links = []
                for msg_num in range(start_num, end_num + 1):
                    if msg_num in message_number_map:
                        msg = message_number_map[msg_num]
                        msg_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{msg.id}"
                        links.append(f"[#{msg_num}]({msg_link})")
                    else:
                        links.append(f"[#{msg_num}]")
                return "-".join(links) if links else match.group(0)
            
            # Replace individual citations with Discord message links (not part of ranges, compact format)
            def replace_citation(match):
                # Skip if already a markdown link (check if followed by ]( )
                pos = match.start()
                after_pos = match.end()
                
                # Check if this is already inside a markdown link
                if after_pos < len(response) - 2 and response[after_pos:after_pos+2] == '](':
                    return match.group(0)  # Already linked, skip
                
                # Check if this citation is part of a range by looking at context
                if after_pos < len(response) and response[after_pos:after_pos+1] == '-':
                    return match.group(0)  # This is the start of a range, skip it
                # Check what comes before
                if pos > 0 and response[pos-1:pos] == '-':
                    return match.group(0)  # This is the end of a range, skip it
                    
                msg_num = int(match.group(1))
                if msg_num in message_number_map:
                    msg = message_number_map[msg_num]
                    msg_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{msg.id}"
                    return f"[#{msg_num}]({msg_link})"
                return match.group(0)  # Keep original if not found
            
            # First replace ranges, then individual citations
            response = re.sub(range_pattern, replace_range, response)
            response = re.sub(citation_pattern, replace_citation, response)
            
            # Convert custom Discord emoji references to actual emoji format
            # Pattern: <:emoji_name:emoji_id> or <a:emoji_name:emoji_id> for animated
            emoji_pattern = r'<(a?):([^:]+):(\d+)>'
            def render_emoji(match):
                animated = match.group(1)
                emoji_name = match.group(2)
                emoji_id = match.group(3)
                # Return proper Discord emoji format
                return f"<{animated}:{emoji_name}:{emoji_id}>"
            
            response = re.sub(emoji_pattern, render_emoji, response)
            
            # Calculate cost
            request_cost = 0
            usage_text = ""
            if hasattr(completion, 'usage') and completion.usage:
                if hasattr(completion.usage, 'prompt_tokens_details') and completion.usage.prompt_tokens_details:
                    cached = completion.usage.prompt_tokens_details.cached_tokens
                    uncached = completion.usage.prompt_tokens - cached
                    input_cost = (uncached / 1_000_000) * GROK_TEXT_INPUT_COST + (cached / 1_000_000) * GROK_TEXT_CACHED_COST
                else:
                    input_cost = (completion.usage.prompt_tokens / 1_000_000) * GROK_TEXT_INPUT_COST
                output_cost = (completion.usage.completion_tokens / 1_000_000) * GROK_TEXT_OUTPUT_COST
                request_cost = input_cost + output_cost
                usage_text = f"💵 ${request_cost:.6f} • {completion.usage.prompt_tokens} in / {completion.usage.completion_tokens} out"
            
            # Delete searching message
            await searching_msg.delete()
            
            # Create response embed
            if target_user:
                title = f"🔍 Search Results: {target_user.display_name}"
            else:
                title = "🔍 Search Results: Channel History"
            
            # Prepare additional fields
            messages_info = f"{len(collected_messages)} total (analyzed {messages_to_analyze})"
            if keyword_filter:
                messages_info += f"\nFiltered by: `{keyword_filter}`"
            if cited_numbers:
                messages_info += f"\n{len(cited_numbers)} messages cited"
            
            # Split response into chunks if needed (4096 char limit per embed description)
            # When splitting, ensure we don't break citations in the middle
            if len(response) <= 4096:
                # Single embed response
                embed = discord.Embed(
                    title=title,
                    description=response,
                    color=discord.Color.purple(),
                    timestamp=ctx.message.created_at
                )
                embed.set_author(
                    name="Grok Search",
                    icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg"
                )
                embed.add_field(
                    name="Query",
                    value=query[:1024],
                    inline=False
                )
                embed.add_field(
                    name="💡 Follow-up",
                    value="Reply to this message to ask more questions about this user's history",
                    inline=False
                )
                footer_text = f"Requested by {ctx.author.display_name}"
                if usage_text:
                    footer_text += f" • {usage_text}"
                embed.set_footer(text=footer_text, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                
                await ctx.reply(embed=embed)
            else:
                # Split into multiple embeds, but avoid breaking citations
                chunks = []
                current_chunk = ""
                
                # Split by sentences/paragraphs first to avoid breaking markdown links
                paragraphs = response.split('\n\n')
                
                for para in paragraphs:
                    # If adding this paragraph would exceed limit, start new chunk
                    if len(current_chunk) + len(para) + 2 > 4096:  # +2 for \n\n
                        if current_chunk:
                            chunks.append(current_chunk.rstrip())
                            current_chunk = para + '\n\n'
                        else:
                            # Paragraph itself is too long, need to split it more carefully
                            sentences = para.split('. ')
                            for sentence in sentences:
                                if len(current_chunk) + len(sentence) + 2 > 4096:
                                    if current_chunk:
                                        chunks.append(current_chunk.rstrip())
                                        current_chunk = sentence + '. '
                                    else:
                                        # Even a single sentence is too long, force split but try to avoid breaking links
                                        # Find a safe break point (space not inside a markdown link)
                                        safe_length = 4096
                                        chunk_text = sentence[:safe_length]
                                        
                                        # Check if we're in the middle of a markdown link
                                        last_bracket = chunk_text.rfind('[')
                                        last_paren = chunk_text.rfind('(')
                                        close_bracket = chunk_text.rfind(']')
                                        close_paren = chunk_text.rfind(')')
                                        
                                        # If we have an open bracket/paren without close, find a safer break
                                        if (last_bracket > close_bracket) or (last_paren > close_paren):
                                            # Find last complete space before the link started
                                            last_safe_space = chunk_text.rfind(' ', 0, last_bracket if last_bracket > last_paren else last_paren)
                                            if last_safe_space > 0:
                                                chunk_text = sentence[:last_safe_space]
                                        
                                        chunks.append(chunk_text)
                                        current_chunk = sentence[len(chunk_text):] + '. '
                                else:
                                    current_chunk += sentence + '. '
                    else:
                        current_chunk += para + '\n\n'
                
                # Add remaining chunk
                if current_chunk.strip():
                    chunks.append(current_chunk.rstrip())
                
                logger.info(f'Search response split into {len(chunks)} embeds')
                
                # Helper function to calculate total embed size
                def get_embed_size(embed):
                    size = 0
                    if embed.title:
                        size += len(embed.title)
                    if embed.description:
                        size += len(embed.description)
                    if embed.footer and embed.footer.text:
                        size += len(embed.footer.text)
                    if embed.author and embed.author.name:
                        size += len(embed.author.name)
                    for field in embed.fields:
                        if field.name:
                            size += len(field.name)
                        if field.value:
                            size += len(field.value)
                    return size
                
                for i, chunk in enumerate(chunks):
                    embed = discord.Embed(
                        title=f"{title} (Part {i+1}/{len(chunks)})" if i > 0 else title,
                        description=chunk,
                        color=discord.Color.purple(),
                        timestamp=ctx.message.created_at
                    )
                    embed.set_author(
                        name="Grok Search",
                        icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg"
                    )
                    
                    # Add fields only to first embed
                    if i == 0:
                        embed.add_field(
                            name="Query",
                            value=query[:1024],
                            inline=False
                        )
                    
                    # Add footer and follow-up only to last embed
                    if i == len(chunks) - 1:
                        embed.add_field(
                            name="💡 Follow-up",
                            value="Reply to this message to ask more questions about this user's history",
                            inline=False
                        )
                        footer_text = f"Requested by {ctx.author.display_name}"
                        if usage_text:
                            footer_text += f" • {usage_text}"
                        embed.set_footer(text=footer_text, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    
                    # Check if embed size exceeds limit (6000 chars total)
                    embed_size = get_embed_size(embed)
                    if embed_size > 5800:  # Leave some buffer
                        # Need to split this chunk further
                        logger.warning(f'Embed {i+1} size {embed_size} exceeds limit, splitting further')
                        # Split description in half
                        mid_point = len(chunk) // 2
                        # Find a good break point (paragraph or sentence)
                        break_point = chunk.rfind('\n\n', 0, mid_point)
                        if break_point == -1:
                            break_point = chunk.rfind('. ', 0, mid_point)
                        if break_point == -1:
                            break_point = chunk.rfind(' ', 0, mid_point)
                        if break_point == -1:
                            break_point = mid_point
                        
                        # Insert the second half back into chunks
                        first_half = chunk[:break_point].rstrip()
                        second_half = chunk[break_point:].lstrip()
                        chunks[i] = first_half
                        chunks.insert(i + 1, second_half)
                        
                        # Update embed with first half
                        embed.description = first_half
                        # Update title to reflect new total
                        if i > 0:
                            embed.title = f"{title} (Part {i+1}/{len(chunks)})"
                        
                        logger.info(f'Split embed into 2 parts, now have {len(chunks)} total chunks')
                    
                    await ctx.reply(embed=embed)
            
            logger.info(f'Search completed successfully')
            
    except Exception as e:
        logger.error(f'Error in search command: {e}', exc_info=True)
        try:
            await searching_msg.edit(content=f"❌ Error searching messages: {str(e)}")
        except:
            # If searching message was already deleted, send a new message
            await ctx.reply(f"❌ Error searching messages: {str(e)}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check if bot is mentioned OR if user is replying to bot's message
    is_bot_mentioned = bot.user in message.mentions
    is_replying_to_bot = False
    
    if message.reference:
        try:
            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            is_replying_to_bot = replied_msg.author == bot.user
        except:
            pass
    
    if is_bot_mentioned or is_replying_to_bot:
        if is_replying_to_bot:
            logger.info(f'Bot reply detected from {message.author} in #{message.channel}')
        else:
            logger.info(f'Bot mentioned by {message.author} in #{message.channel}')
        
        # Build context if this is a reply
        prompt = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
        
        # Check if this is a follow-up to a previous conversation
        is_search_followup = False
        conversation_context = []
        
        if is_replying_to_bot:
            try:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
                
                # Check if the replied message was a search result
                if replied_msg.embeds and replied_msg.embeds[0].title and "Search Results" in replied_msg.embeds[0].title:
                    if message.channel.id in search_context and message.author.id in search_context[message.channel.id]:
                        is_search_followup = True
                        logger.info(f'Detected search follow-up query')
                        
                        # Get stored search context
                        ctx_data = search_context[message.channel.id][message.author.id]
                        searched_user = ctx_data['searched_user']
                        user_messages = ctx_data['messages']
                        
                        # Build context with previous search data (same as in search command)
                        messages_to_analyze = min(len(user_messages), 100)
                        messages_for_context = user_messages[:messages_to_analyze]
                        
                        # Create message number mapping for citation linking
                        message_number_map = {}
                        context_parts = [
                            f"Previous search was about {'user ' + searched_user.name if searched_user else 'channel history'}.",
                            f"Follow-up query: {prompt}\n",
                            f"\n{'User ' + searched_user.name if searched_user else 'Channel'} messages (showing {messages_to_analyze} of {len(user_messages)} found, from oldest to newest):\n"
                        ]
                        
                        for i, msg in enumerate(reversed(messages_for_context), 1):
                            # Convert UTC timestamp to configured timezone
                            timestamp_local = msg.created_at.astimezone(TIMEZONE)
                            tz_abbr = timestamp_local.strftime("%Z")
                            timestamp_str = timestamp_local.strftime(f"%Y-%m-%d %H:%M {tz_abbr}")
                            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
                            message_number_map[i] = msg  # Store mapping for citation linking
                            context_parts.append(f"[{i}] [{timestamp_str}] {content}")
                        
                        context_parts.append(f"\n\nAnswer this follow-up question: {prompt}")
                        context_parts.append("\n\nIMPORTANT: When referencing specific messages in your answer, cite them using the format [#N] where N is the message number. For example: 'In message [#5], they mentioned...' or 'See messages [#3], [#7], and [#12] for examples.'")
                        context_parts.append("\n\nNote: Custom Discord emojis appear as <:emoji_name:emoji_id>. When quoting messages with emojis, preserve this exact format.")
                        tz_name = TIMEZONE.zone
                        context_parts.append(f"\n\nNote: All timestamps are in {tz_name} timezone.")
                        prompt = "\n".join(context_parts)
                        logger.info(f'Built search follow-up context with {len(user_messages)} messages')
                
                # Check if we have conversation history with this message
                elif replied_msg.id in conversation_history:
                    logger.info('Detected conversation follow-up with history')
                    prev_conv = conversation_history[replied_msg.id]
                    
                    # Build conversation history for context
                    conversation_context = [
                        {"role": "user", "content": prev_conv['user_query']},
                        {"role": "assistant", "content": prev_conv['bot_response']},
                        {"role": "user", "content": prompt}
                    ]
                    logger.info('Built conversation context with previous exchange')
            except Exception as e:
                logger.warning(f'Error fetching conversation context: {e}')
        
        # Get conversation history for this user (if replying to bot)
        conversation_messages = []
        use_conversation_history = False
        if is_replying_to_bot and not is_search_followup:
            # Initialize conversation history for this channel/user if needed
            if message.channel.id not in conversation_history:
                conversation_history[message.channel.id] = {}
            if message.author.id not in conversation_history[message.channel.id]:
                conversation_history[message.channel.id][message.author.id] = []
            
            # Get last 5 exchanges (10 messages max) to keep context window reasonable
            conversation_messages = conversation_history[message.channel.id][message.author.id][-10:]
            if conversation_messages:
                use_conversation_history = True
                logger.info(f'Using conversation history mode with {len(conversation_messages)} previous messages')
        logger.info(f'Extracted prompt: "{prompt}"')
        
        # Helper function to check if URL is a supported image type
        def is_supported_image(url):
            """Check if URL ends with supported image extensions"""
            supported_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            url_lower = url.lower().split('?')[0]  # Remove query params
            return any(url_lower.endswith(ext) for ext in supported_extensions)
        
        # Collect images from the current message
        image_urls = []
        unsupported_images = []
        
        # Check for direct attachments
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                if is_supported_image(attachment.url) or attachment.content_type in ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']:
                    image_urls.append(attachment.url)
                    logger.info(f'Found image attachment: {attachment.filename}')
                else:
                    unsupported_images.append(attachment.filename)
                    logger.warning(f'Unsupported image type: {attachment.filename} ({attachment.content_type})')
        
        # Check for image URLs in message content (links to images)
        image_url_pattern = r'https?://(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?\.(?:jpg|jpeg|png|webp)(?:\?[^\s]*)?'
        found_urls = re.findall(image_url_pattern, message.content, re.IGNORECASE)
        for url in found_urls:
            if url not in image_urls:
                image_urls.append(url)
                logger.info(f'Found image URL in message: {url}')
        
        # Check for Discord CDN embeds (when links auto-embed like Tenor, Giphy, etc.)
        for embed in message.embeds:
            # For gif/video embeds (Tenor, Giphy), prefer video/image in this order
            if embed.type in ['gifv', 'video', 'image', 'rich']:
                # Try to get the actual media URL
                media_url = None
                
                if embed.image and embed.image.url:
                    media_url = embed.image.url
                elif embed.video and embed.video.url:
                    media_url = embed.video.url
                elif embed.thumbnail and embed.thumbnail.url:
                    media_url = embed.thumbnail.url
                elif embed.url:
                    media_url = embed.url
                
                if media_url and media_url not in image_urls:
                    # Only add if it's a supported format
                    if is_supported_image(media_url):
                        image_urls.append(media_url)
                        logger.info(f'Found media in embed ({embed.type}): {media_url}')
                    else:
                        logger.warning(f'Skipping unsupported media format: {media_url}')
        
        # If replying to another message, get full context (unless using conversation history)
        if message.reference and not use_conversation_history:
            logger.info('Message is a reply, fetching conversation context...')
            try:
                # First, traverse the reply chain
                reply_chain = []
                current_message = message
                max_depth = 10
                depth = 0
                
                while current_message.reference and depth < max_depth:
                    try:
                        replied_message = await message.channel.fetch_message(current_message.reference.message_id)
                        reply_chain.insert(0, replied_message)
                        current_message = replied_message
                        depth += 1
                    except:
                        break
                
                logger.info(f'Found {len(reply_chain)} messages in reply chain')
                
                # Now get surrounding messages for additional context
                # Only include messages within 2 minutes of each other to stay relevant
                context_messages = []
                time_window_seconds = 120  # 2 minutes
                
                if reply_chain:
                    oldest_msg = reply_chain[0]
                    
                    # Get messages before the oldest message, but only if they're recent
                    try:
                        before_messages = []
                        async for msg in message.channel.history(limit=10, before=oldest_msg.created_at):
                            if msg.id != oldest_msg.id and not msg.author.bot:
                                # Check time difference
                                time_diff = (oldest_msg.created_at - msg.created_at).total_seconds()
                                if time_diff <= time_window_seconds:
                                    before_messages.append(msg)
                                else:
                                    # Stop when we hit a message too old
                                    break
                        before_messages.reverse()  # Chronological order
                        context_messages.extend(before_messages)
                        logger.info(f'Found {len(before_messages)} recent messages before reply chain (within 2 min)')
                    except:
                        pass
                    
                    # Add the reply chain
                    context_messages.extend(reply_chain)
                    
                    # Get messages after the last message in chain (if not the current message)
                    try:
                        newest_msg = reply_chain[-1]
                        after_messages = []
                        async for msg in message.channel.history(limit=10, after=newest_msg.created_at, oldest_first=True):
                            if msg.id != newest_msg.id and msg.id != message.id and not msg.author.bot:
                                # Check time difference
                                time_diff = (msg.created_at - newest_msg.created_at).total_seconds()
                                if time_diff <= time_window_seconds:
                                    after_messages.append(msg)
                                else:
                                    # Stop when we hit a message too far in the future
                                    break
                        context_messages.extend(after_messages)
                        logger.info(f'Found {len(after_messages)} messages after reply chain (within 2 min)')
                    except:
                        pass
                
                # Collect images from all context messages
                for msg in context_messages:
                    # Collect images from attachments
                    for attachment in msg.attachments:
                        if attachment.content_type and attachment.content_type.startswith('image/'):
                            if attachment.url not in image_urls:
                                if is_supported_image(attachment.url) or attachment.content_type in ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']:
                                    image_urls.append(attachment.url)
                                    logger.info(f'Found image in context: {attachment.filename}')
                                else:
                                    logger.warning(f'Skipping unsupported image in context: {attachment.filename}')
                    
                    # Collect image URLs from message content
                    found_urls = re.findall(image_url_pattern, msg.content, re.IGNORECASE)
                    for url in found_urls:
                        if url not in image_urls:
                            image_urls.append(url)
                            logger.info(f'Found image URL in context: {url}')
                    
                    # Collect images from embeds
                    for embed in msg.embeds:
                        if embed.type in ['gifv', 'video', 'image', 'rich']:
                            media_url = None
                            
                            if embed.image and embed.image.url:
                                media_url = embed.image.url
                            elif embed.video and embed.video.url:
                                media_url = embed.video.url
                            elif embed.thumbnail and embed.thumbnail.url:
                                media_url = embed.thumbnail.url
                            elif embed.url:
                                media_url = embed.url
                            
                            if media_url and media_url not in image_urls:
                                if is_supported_image(media_url):
                                    image_urls.append(media_url)
                                    logger.info(f'Found media in context embed ({embed.type}): {media_url}')
                                else:
                                    logger.warning(f'Skipping unsupported media in context: {media_url}')
                
                # Build context from all messages
                if context_messages:
                    context_parts = ["Here is the conversation context:\n"]
                    for i, msg in enumerate(context_messages, 1):
                        # Truncate very long messages to avoid token limits
                        content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                        context_parts.append(f"[{i}] {msg.author.name}: {content}")
                    context_parts.append(f"\nUser's question: {prompt}")
                    prompt = "\n".join(context_parts)
                    logger.info(f'Built context with {len(context_messages)} total messages')
                
            except Exception as e:
                logger.warning(f'Could not fetch conversation context: {e}')
        
        if not prompt and not image_urls:
            logger.warning('No prompt or images found')
            await message.reply("Please provide a question or image after mentioning me.")
            return
        
        # Notify user about unsupported images if any
        if unsupported_images and not image_urls:
            await message.reply(f"⚠️ Found unsupported image format(s): {', '.join(unsupported_images)}\n\nGrok only supports: JPEG, PNG, and WebP images.")
            return
        elif unsupported_images:
            logger.info(f'Proceeding with {len(image_urls)} supported images, ignoring {len(unsupported_images)} unsupported')
        
        # Query Grok
        try:
            async with message.channel.typing():
                # Determine model based on whether we have images
                model = GROK_VISION_MODEL if image_urls else GROK_TEXT_MODEL
                logger.info(f'Using model: {model} (images: {len(image_urls)})')
                
                # Build message content with conversation history
                if image_urls:
                    # For vision model, use the multi-part content format
                    # Vision model doesn't support conversation history with images well, so just send current message
                    content = [{"type": "text", "text": prompt or "What's in this image?"}]
                    for url in image_urls:
                        content.append({"type": "image_url", "image_url": {"url": url}})
                    
                    logger.info('Sending request to Grok with images...')
                    completion = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "user", "content": content}
                        ]
                    )
                else:
                    # For text-only, include conversation history
                    messages_to_send = []
                    
                    # Add conversation history if available
                    if conversation_messages:
                        messages_to_send.extend(conversation_messages)
                    
                    # Add current message
                    messages_to_send.append({"role": "user", "content": prompt})
                    
                    logger.info(f'Sending text-only request to Grok with {len(messages_to_send)} messages (history: {len(conversation_messages)})')
                    
                    # Build request parameters
                    request_params = {
                        "model": model,
                        "messages": messages_to_send
                    }
                    
                    # Add search parameters if enabled
                    if ENABLE_WEB_SEARCH:
                        request_params["extra_body"] = {
                            "search_parameters": {
                                "mode": "auto",  # Let Grok decide when to search
                                "max_search_results": MAX_SEARCH_RESULTS
                            }
                        }
                    
                    completion = client.chat.completions.create(**request_params)
                
                response = completion.choices[0].message.content
                logger.info(f'Received response from Grok ({len(response)} characters)')
                
                # Process citations if this is a search follow-up with message_number_map
                if is_search_followup and 'message_number_map' in locals():
                    # Parse citations from response and extract referenced message numbers
                    # Match both individual citations [#N] and ranges [#N]-[M], [#N]-M, or [#N-M]
                    citation_pattern = r'\[#(\d+)\]'
                    range_pattern = r'\[#(\d+)(?:\]-?\[?|-)(\d+)\]?'  # Matches [#88]-[90], [#88]-90, or [#88-90]
                    
                    # Find individual citations (but not those that are part of ranges)
                    cited_numbers = set()
                    for match in re.finditer(citation_pattern, response):
                        # Check if this is part of a range by looking at context
                        pos = match.start()
                        # Skip if preceded by a range pattern
                        if pos > 0 and response[pos-1:pos] in ['-', ']']:
                            continue
                        cited_numbers.add(int(match.group(1)))
                    
                    # Find and expand ranges
                    for match in re.finditer(range_pattern, response):
                        start_num = int(match.group(1))
                        end_num = int(match.group(2))
                        # Add all numbers in the range
                        cited_numbers.update(range(start_num, end_num + 1))
                    
                    logger.info(f'Found {len(cited_numbers)} cited messages in follow-up: {sorted(cited_numbers)}')
                    
                    # Replace ranges with individual linked citations (compact format)
                    def replace_range(match):
                        start_num = int(match.group(1))
                        end_num = int(match.group(2))
                        links = []
                        for msg_num in range(start_num, end_num + 1):
                            if msg_num in message_number_map:
                                msg = message_number_map[msg_num]
                                msg_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{msg.id}"
                                links.append(f"[#{msg_num}]({msg_link})")
                            else:
                                links.append(f"[#{msg_num}]")
                        return "-".join(links) if links else match.group(0)
                    
                    # Replace individual citations with Discord message links (not part of ranges, compact format)
                    def replace_citation(match):
                        # Skip if already a markdown link (check if followed by ]( )
                        pos = match.start()
                        after_pos = match.end()
                        
                        # Check if this is already inside a markdown link
                        if after_pos < len(response) - 2 and response[after_pos:after_pos+2] == '](':
                            return match.group(0)  # Already linked, skip
                        
                        # Check if this citation is part of a range by looking at context
                        if after_pos < len(response) and response[after_pos:after_pos+1] == '-':
                            return match.group(0)  # This is the start of a range, skip it
                        # Check what comes before
                        if pos > 0 and response[pos-1:pos] == '-':
                            return match.group(0)  # This is the end of a range, skip it
                            
                        msg_num = int(match.group(1))
                        if msg_num in message_number_map:
                            msg = message_number_map[msg_num]
                            msg_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{msg.id}"
                            return f"[#{msg_num}]({msg_link})"
                        return match.group(0)  # Keep original if not found
                    
                    # First replace ranges, then individual citations
                    response = re.sub(range_pattern, replace_range, response)
                    response = re.sub(citation_pattern, replace_citation, response)
                    
                    # Convert custom Discord emoji references to actual emoji format
                    emoji_pattern = r'<(a?):([^:]+):(\d+)>'
                    def render_emoji(match):
                        animated = match.group(1)
                        emoji_name = match.group(2)
                        emoji_id = match.group(3)
                        return f"<{animated}:{emoji_name}:{emoji_id}>"
                    
                    response = re.sub(emoji_pattern, render_emoji, response)
                    logger.info(f'Processed citations and emojis in follow-up response')
                
                # Convert Twitter/X usernames to clickable links
                # Match @username patterns (not already in URLs)
                twitter_pattern = r'(?<![:/\w])@([A-Za-z0-9_]{1,15})(?!\w)'
                response = re.sub(twitter_pattern, r'[@\1](https://x.com/\1)', response)
                logger.info(f'Converted Twitter mentions to links')
                
                # Store conversation history (only for non-search, text-only conversations)
                if is_replying_to_bot and not is_search_followup and not image_urls:
                    if message.channel.id not in conversation_history:
                        conversation_history[message.channel.id] = {}
                    if message.author.id not in conversation_history[message.channel.id]:
                        conversation_history[message.channel.id][message.author.id] = []
                    
                    # Add user message and assistant response
                    conversation_history[message.channel.id][message.author.id].append({"role": "user", "content": prompt})
                    conversation_history[message.channel.id][message.author.id].append({"role": "assistant", "content": response})
                    
                    # Keep only last 20 messages (10 exchanges)
                    conversation_history[message.channel.id][message.author.id] = conversation_history[message.channel.id][message.author.id][-20:]
                    logger.info(f'Stored conversation history ({len(conversation_history[message.channel.id][message.author.id])} messages)')
                
                # Track token usage and calculate cost
                request_cost = 0
                search_cost = 0
                usage_text = ""
                if hasattr(completion, 'usage') and completion.usage:
                    # Calculate token cost based on actual model used
                    model_used = completion.model
                    is_vision = 'vision' in model_used.lower()
                    vision_cost = 0
                    
                    if is_vision:
                        # Grok-vision pricing
                        input_cost = (completion.usage.prompt_tokens / 1_000_000) * GROK_VISION_INPUT_COST
                        output_cost = (completion.usage.completion_tokens / 1_000_000) * GROK_VISION_OUTPUT_COST
                        vision_cost = input_cost + output_cost
                    else:
                        # Grok text model pricing
                        # Account for cached tokens if available
                        if hasattr(completion.usage, 'prompt_tokens_details') and completion.usage.prompt_tokens_details:
                            cached = completion.usage.prompt_tokens_details.cached_tokens
                            uncached = completion.usage.prompt_tokens - cached
                            input_cost = (uncached / 1_000_000) * GROK_TEXT_INPUT_COST + (cached / 1_000_000) * GROK_TEXT_CACHED_COST
                        else:
                            input_cost = (completion.usage.prompt_tokens / 1_000_000) * GROK_TEXT_INPUT_COST
                        output_cost = (completion.usage.completion_tokens / 1_000_000) * GROK_TEXT_OUTPUT_COST
                    
                    # Calculate search cost if sources were used
                    num_sources = getattr(completion.usage, 'num_sources_used', 0)
                    if num_sources > 0:
                        search_cost = (num_sources / 1000) * GROK_SEARCH_COST
                        logger.info(f"Search usage - Sources used: {num_sources}, Cost: ${search_cost:.6f}")
                    
                    request_cost = input_cost + output_cost + search_cost
                    
                    # Build usage text with vision and search cost breakdowns
                    cost_str = f"💵 ${request_cost:.6f}"
                    indicators = []
                    
                    if is_vision:
                        indicators.append(f"👁️ ${vision_cost:.6f} vision")
                    if search_cost > 0:
                        indicators.append(f"🔍 ${search_cost:.6f} search")
                    
                    if indicators:
                        cost_str += f" ({', '.join(indicators)})"
                    
                    usage_text = f"{cost_str} • {completion.usage.prompt_tokens} in / {completion.usage.completion_tokens} out"
                    
                    logger.info(f"Token usage - Input: {completion.usage.prompt_tokens}, Output: {completion.usage.completion_tokens}, Search sources: {num_sources}, Total cost: ${request_cost:.6f}")
                
                # Create embed(s) for the response
                # Discord embed description limit is 4096 characters
                if len(response) <= 4096:
                    embed = discord.Embed(
                        description=response,
                        color=discord.Color.blue(),
                        timestamp=message.created_at
                    )
                    embed.set_author(
                        name="Grok Response",
                        icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg"
                    )
                    footer_text = f"Requested by {message.author.display_name}"
                    if usage_text:
                        footer_text += f" • {usage_text}"
                    embed.set_footer(text=footer_text, icon_url=message.author.avatar.url if message.author.avatar else None)
                    
                    # Send reply and store in conversation history
                    bot_message = await message.reply(embed=embed)
                    
                    # Store conversation for future context (keep original user prompt, not the full context)
                    original_prompt = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
                    conversation_history[bot_message.id] = {
                        'user_query': original_prompt,
                        'bot_response': response,
                        'model_used': model
                    }
                    logger.info(f'Stored conversation history for message {bot_message.id}')
                else:
                    # Split into multiple embeds if response is too long
                    chunks = [response[i:i+4096] for i in range(0, len(response), 4096)]
                    logger.info(f'Response split into {len(chunks)} embeds')
                    bot_message = None
                    for i, chunk in enumerate(chunks):
                        embed = discord.Embed(
                            description=chunk,
                            color=discord.Color.blue(),
                            timestamp=message.created_at
                        )
                        embed.set_author(
                            name=f"Grok Response (Part {i+1}/{len(chunks)})",
                            icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg"
                        )
                        if i == len(chunks) - 1:  # Only add footer to last embed
                            footer_text = f"Requested by {message.author.display_name}"
                            if usage_text:
                                footer_text += f" • {usage_text}"
                            embed.set_footer(text=footer_text, icon_url=message.author.avatar.url if message.author.avatar else None)
                        
                        # Only store the first message for conversation history
                        if i == 0:
                            bot_message = await message.reply(embed=embed)
                        else:
                            await message.reply(embed=embed)
                    
                    # Store conversation for future context
                    if bot_message:
                        original_prompt = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
                        conversation_history[bot_message.id] = {
                            'user_query': original_prompt,
                            'bot_response': response,
                            'model_used': model
                        }
                        logger.info(f'Stored conversation history for message {bot_message.id}')
                
                logger.info('Response sent successfully')
        except Exception as e:
            logger.error(f'Error querying Grok: {e}', exc_info=True)
            
            # Provide user-friendly error messages
            error_msg = str(e)
            if "412" in error_msg and "Unsupported content-type" in error_msg:
                await message.reply("❌ One or more images are in an unsupported format. Grok only accepts JPEG, PNG, and WebP images.\n\nPlease try again with supported image formats.")
            elif "401" in error_msg or "authentication" in error_msg.lower():
                await message.reply("❌ Authentication error. Please check the API key configuration.")
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                await message.reply("⏳ Rate limit reached. Please try again in a few moments.")
            elif "timeout" in error_msg.lower():
                await message.reply("⏳ Request timed out. Please try again.")
            else:
                await message.reply(f"❌ Error querying Grok: {error_msg}")
    
    await bot.process_commands(message)

bot.run(TOKEN)