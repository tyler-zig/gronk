"""Discord-history intent detection, message scanning, and analysis via Grok."""

import json as _json
import logging
import re as _re
from typing import Optional, Tuple

import discord

from config import (
    DEFAULT_SEARCH_LIMIT,
    GROK_ANALYSIS_REASONING_EFFORT,
    GROK_TEXT_MODEL,
    MAX_KEYWORD_SCAN,
    MAX_MESSAGES_ANALYZED,
    TIMEZONE,
)
from cost_utils import format_cost
from discord_utils import convert_usernames_to_mentions
from grok_client import build_cache_conversation_id, sdk_chat_request
from grok_schemas import DiscordHistoryAnswer
from nlp_utils import advanced_nlp_parse


logger = logging.getLogger('GrokBot')


# ---------------------------------------------------------------------------
# Precompiled regex for Discord-history intent detection
# ---------------------------------------------------------------------------

BOT_PING_PHRASES = [
    "are you there", "are you working", "are you online", "are you up",
    "are you alive", "yo", "ping", "test", "hello", "hi", "hey",
    "you here", "up?", "working?", "online?", "alive?", "present?", "awake?"
]

_STRONG_SCOPE = _re.compile(
    r'\b(in|on|from|of|for)\s+(this|the|our)\s+(channel|server|discord|chat)\b'
    r'|\b(this|the|our)\s+(channel|server|discord|chat)\b'
    r'|\bhere\s+in\s+(this|the)\s+(channel|server|discord|chat)\b'
)
_WEAK_SCOPE = _re.compile(r'\bin\s+here\b')

_GENERAL_CONTEXT = _re.compile(
    r'\bin history\b|\bin the world\b|\bon (twitter|x\.com|x)\b'
    r'|\bin the news\b|\bglobally\b|\bworldwide\b'
    r'|\bscientists say\b|\bresearchers found\b|\bstudies show\b'
    r'|\baccording to\b|\bnews\b|\bcurrent events?\b'
)

_DISCORD_ANALYSIS = _re.compile(
    r'\bwho\s+(talks?|mentions?|discusses?|posts?|says?|said|chats?|sent|shared)\b'
    r'|\bwhat\s+(have|has|did|do)\s+(we|users?|people|members?)\s+(talk|say|said|discuss|mention|post|share|send)\b'
    r'|\b(summarize|summary|overview|recap)\b'
    r'|\b(most|least|top|bottom)\b'
    r'|\bhow\s+(often|many|much)\b'
    r'|\brank\s+(members?|users?|people)\b'
    r'|\b(search|scan|look through|check)\b'
)

_DISCORD_ACTIVITY = _re.compile(
    r'\b(talked|talks|mentioned|mentions|discussed|discusses'
    r'|posted|posts|sent|shared|said|chatted|messaged)\b'
)

_DISCORD_HISTORY_NOUN = _re.compile(
    r'\b(messages?|conversation|conversations|chat|history|threads?|posts?)\b'
)

_DISCORD_PRONOUN = _re.compile(r'\b(we|us|our)\b')

_GENERAL_QUESTION = _re.compile(
    r'\bwhat (is|are|was|were)\b'
    r'|\bhow (does|do|did|can|much|many|high|low|far)\b'
    r'|\bwhy (does|do|did|is|are)\b'
    r'|\bwhere (is|are|does|do)\b'
    r'|\bwhen (is|are|does|do|did)\b'
    r'|\bwho (is|are|was|were)\b'
    r'|\bexplain\b|\btell me about\b|\bdescribe\b'
)

_TIME_PERIODS = _re.compile(
    r'past\s*month|last\s*month|30\s*days'
    r'|past\s*week|last\s*week|7\s*days'
    r'|past\s*day|last\s*day|24\s*hours|today'
    r'|past\s*year|last\s*year'
    r'|recently'
)

_TOPIC_LEAD = _re.compile(r'\b(about|regarding|on|for)\s+(.+)$')

NON_MEANINGFUL_KEYWORDS = frozenset({
    "we", "us", "our", "discord", "chat", "talking", "about", "in", "the",
    "what", "are", "is", "on", "this", "server", "channel", "here", "people",
    "users", "members", "who", "they", "them", "he", "she", "it", "that",
    "these", "those", "message", "messages", "conversation", "conversations",
    "last week", "last month", "past week", "past month", "recently",
    "this channel", "this server", "this discord", "this chat",
    "our conversations", "rank members", "activity", "the top users", "top users"
})


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def _is_bot_ping(text: str) -> bool:
    return any(_re.search(rf'(?<!\w){_re.escape(p)}(?!\w)', text)
               for p in BOT_PING_PHRASES)


# Keep these module-level wrappers for external callers that import them.
# They wrap the precompiled patterns.

DISCORD_SCOPE_PATTERNS = [_STRONG_SCOPE.pattern] + [_WEAK_SCOPE.pattern]
DISCORD_STRONG_SCOPE_PATTERNS = [_STRONG_SCOPE.pattern]
DISCORD_WEAK_SCOPE_PATTERNS = [_WEAK_SCOPE.pattern]
GENERAL_CONTEXT_PATTERNS = [_GENERAL_CONTEXT.pattern]
DISCORD_ANALYSIS_PATTERNS = [_DISCORD_ANALYSIS.pattern]
DISCORD_ACTIVITY_PATTERNS = [_DISCORD_ACTIVITY.pattern]
DISCORD_HISTORY_NOUN_PATTERNS = [_DISCORD_HISTORY_NOUN.pattern]
DISCORD_PRONOUN_PATTERNS = [_DISCORD_PRONOUN.pattern]
GENERAL_QUESTION_PATTERNS = [_GENERAL_QUESTION.pattern]


async def should_search_discord_history(
    message_content: str, has_mentions: bool
) -> Tuple[bool, Optional[int], Optional[str]]:
    """Determine if the user query is asking to search Discord history."""
    text = message_content.lower()

    # 0. BOT STATUS CHECKS
    if has_mentions and _is_bot_ping(text):
        logger.info('Bot ping/status check detected, not a Discord search')
        return False, None, None

    has_strong = bool(_STRONG_SCOPE.search(text))
    has_scope = has_strong or bool(_WEAK_SCOPE.search(text))
    has_discord_pronoun = bool(_DISCORD_PRONOUN.search(text))
    has_analysis = bool(_DISCORD_ANALYSIS.search(text))
    has_activity = bool(_DISCORD_ACTIVITY.search(text))
    has_history_noun = bool(_DISCORD_HISTORY_NOUN.search(text))
    has_general_context = bool(_GENERAL_CONTEXT.search(text))

    if has_general_context and not has_scope:
        logger.info('General query detected: general context indicator found')
        return False, None, None

    # Mentions alone are usually "ask this person", not "search their history".
    if has_mentions:
        if has_strong or has_analysis or has_activity or has_history_noun:
            logger.info('Discord search detected: mention plus history cue')
            return True, extract_time_period(text), _extract_keywords(text)
        logger.info('Mention without history cue, treating as general query')
        return False, None, None

    # Explicit scope + analysis/activity cue
    if has_scope and (has_analysis or has_activity or has_discord_pronoun or has_history_noun):
        logger.info('Discord search detected: explicit scope with history cue')
        return True, extract_time_period(text), _extract_keywords(text)

    # "What have we discussed..." style
    if has_discord_pronoun and (has_analysis or has_activity or has_history_noun):
        logger.info('Discord search detected: pronoun with analysis/activity cue')
        return True, extract_time_period(text), _extract_keywords(text)

    if _GENERAL_QUESTION.search(text):
        logger.info('General query detected: general question pattern found')
    else:
        logger.info('No Discord history trigger found')
    return False, None, None


def extract_time_period(content_lower: str) -> Optional[int]:
    """Return DEFAULT_SEARCH_LIMIT if a time period is mentioned, else None."""
    if _TIME_PERIODS.search(content_lower):
        logger.debug('Time period mentioned, using DEFAULT_SEARCH_LIMIT')
        return DEFAULT_SEARCH_LIMIT
    return None


def _clean_keyword(keyword: str) -> Optional[str]:
    k = _re.sub(r'<@!?\d+>', ' ', keyword)
    k = _re.sub(r'@\w+', ' ', k)
    k = _re.sub(r'\b(in|on|from|of|for|this|the|our)\s+(channel|server|discord|chat)\b', ' ', k)
    k = _re.sub(r'\b(past|last|this)\s+(day|week|month|year)\b', ' ', k)
    k = _re.sub(r'\b(recently|today|yesterday)\b', ' ', k)
    k = _re.sub(r'[^a-z0-9_ .-]+', ' ', k.lower())
    k = _re.sub(r'\s+', ' ', k).strip(' .-')
    if not k or k in NON_MEANINGFUL_KEYWORDS or len(k) < 2:
        return None
    return k


def _extract_keywords(content_lower: str) -> Optional[str]:
    """Extract topic keywords and entities from the query using NLP."""
    m = _TOPIC_LEAD.search(content_lower)
    if m:
        topic = _clean_keyword(m.group(2))
        if topic:
            return topic

    nlp_results = advanced_nlp_parse(content_lower)
    keywords: list[str] = []
    if nlp_results['entities']:
        keywords.extend(ent[0] for ent in nlp_results['entities'])
    if nlp_results['topics']:
        keywords.extend(nlp_results['topics'])

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in keywords:
        c = _clean_keyword(item)
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)

    logger.info("NLP Extracted entities: %s, topics: %s, intent: %s",
                nlp_results['entities'], nlp_results['topics'], nlp_results['intent'])
    return ', '.join(cleaned) if cleaned else None


# ---------------------------------------------------------------------------
# Message collection
# ---------------------------------------------------------------------------

async def _collect_messages(
    message: discord.Message,
    max_scan: int,
    target_user: Optional[discord.User],
    use_keyword_filter: bool,
    keywords: Optional[str],
    searching_msg: discord.Message,
) -> list[discord.Message]:
    """Scan channel history and return filtered messages."""
    collected: list[discord.Message] = []
    scanned = 0
    last_update = 0

    async for msg in message.channel.history(limit=max_scan):
        if msg.id == message.id:
            continue
        scanned += 1

        if target_user and msg.author != target_user:
            continue
        if not target_user and msg.author.bot:
            continue
        if use_keyword_filter and keywords and keywords.lower() not in msg.content.lower():
            continue
        if not msg.content.strip():
            continue

        collected.append(msg)

        if scanned - last_update >= 2000:
            last_update = scanned
            try:
                pct = int((scanned / max_scan) * 100)
                await searching_msg.edit(
                    content=f"🔍 Analyzing... ({pct}% - scanned {scanned:,}, found {len(collected):,})")
            except Exception:
                pass

    return collected


# ---------------------------------------------------------------------------
# Prompt & response processing
# ---------------------------------------------------------------------------

def _build_history_prompt(
    query: str,
    messages_for_context: list[discord.Message],
    total_found: int,
    target_user: Optional[discord.User],
) -> Tuple[str, dict[int, discord.Message]]:
    """Build the full Grok prompt for Discord history analysis."""
    parts: list[str] = [
        (
            "SYSTEM: You are 'gronk', the AI assistant and Discord bot. 'gronk' is a Discord bot interface for interacting with Grok the AI. "
            "Any mention of 'gronk' or '@gronk' in the following messages refers to you, the AI, and NEVER the user. "
            "Never refer to the user as 'gronk' or '@gronk'. Always refer to yourself as 'gronk' or '@gronk' when those names are mentioned. "
            "You are the AI behind the 'gronk' Discord bot, and all responses from 'gronk' are from the AI assistant. "
            "When referring to users, use either their mention or their user ID, but not both in the same phrase. Avoid redundant references like '@username (user ID @123)'. "
            "NEVER output patterns like '@useridnumber (which appears to be @gronk)', '@useridnumber (which is @gronk)', or any similar construction. If a user is the bot, always use only '@gronk' and never the user ID or both together.\n"
        ),
        f"User query: {query}\n",
    ]

    analyze_count = len(messages_for_context)
    if target_user:
        parts.append(f"Analyzing user {target_user.name}'s messages (showing {analyze_count} of {total_found} found, oldest to newest):\n")
    else:
        parts.append(f"Analyzing channel messages (showing {analyze_count} of {total_found} found, oldest to newest):\n")

    msg_map: dict[int, discord.Message] = {}
    for i, msg in enumerate(reversed(messages_for_context), 1):
        ts = msg.created_at.astimezone(TIMEZONE)
        tz_abbr = ts.strftime("%Z")
        ts_str = ts.strftime(f"%Y-%m-%d %H:%M {tz_abbr}")
        content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
        msg_map[i] = msg
        if target_user:
            parts.append(f"[{i}] [{ts_str}] {content}")
        else:
            parts.append(f"[{i}] [{ts_str}] {msg.author.name}: {content}")

    # Message metadata mapping for Grok citations
    parts.append("\n\nMessage Metadata Mapping:")
    for i, msg in enumerate(reversed(messages_for_context), 1):
        excerpt = msg.content[:80].replace('\\', ' ').replace('"', "'")
        parts.append(
            f"{i}: {{'message_id': '{msg.id}', 'channel_id': '{msg.channel.id}', "
            f"'user_id': '{msg.author.id}', 'excerpt': '{excerpt}', "
            f"'link': 'https://discord.com/channels/{msg.guild.id}/{msg.channel.id}/{msg.id}'}}"
        )

    parts.append(
        "\n\nBased on these messages, reply ONLY with a single JSON object in the following format. "
        "Do NOT include any natural language or commentary before or after the JSON. "
        "Only cite the most meaningful and relevant messages (typically 3-6), and do NOT cite every message. "
        "For each citation in your answer, use the metadata from the mapping above for the corresponding number in the 'sources' field.\n"
    )
    parts.append("""
{
    \"answer\": \"<your answer, with inline citations like [#N] ONLY. Do NOT include channel names, emojis, or any extra formatting in the citations. Use only [#N] for each citation.>\",
    \"sources\": {
        \"N\": {
            \"message_id\": \"<discord message id from mapping>\",
            \"channel_id\": \"<discord channel id from mapping>\",
            \"user_id\": \"<discord user id from mapping>\",
            \"excerpt\": \"<short excerpt from the message>\",
            \"link\": \"<discord message link from mapping>\"
        },
        ...
    },
    \"confidence\": <float between 0 and 1>
}
""")
    parts.append("\nIMPORTANT: For every citation, use ONLY the format [#N] with no channel name, emoji, or extra formatting. Example: [#1], [#2], etc.\n")
    return "\n".join(parts), msg_map


def _process_history_response(
    response: str, sources: dict, message: discord.Message
) -> str:
    """Parse Grok response, replace citations with links, and clean up mentions."""
    # Extract JSON
    m = _re.search(r'\{[\s\S]*\}$', response)
    if m:
        try:
            data = _json.loads(m.group(0))
            answer = data.get("answer", "")
            sources = data.get("sources", {})
        except Exception:
            answer = response
    else:
        answer = response

    # Replace [#N] with clickable links
    def _replace_citation(match: _re.Match) -> str:
        num = match.group(1)
        if sources and num in sources:
            link = sources[num].get("link")
            if link and link.startswith("https://discord.com/channels/"):
                return f"[#{num}](<{link}>)"
        return f"[#{num}]"

    answer = _re.sub(r'\[#(\d+)\]', _replace_citation, answer)
    answer = _re.sub(r'(\]\[)', '] [', answer)  # spacing between adjacent citations

    # Build user-id / username lookup
    uid_to_mention: dict[str, str] = {}
    uname_to_mention: dict[str, str] = {}
    for src in sources.values():
        uid = src.get("user_id")
        if uid:
            uid_to_mention[uid] = f'<@{uid}>'
        if uid and message.guild:
            member = message.guild.get_member(int(uid))
            if member:
                uname_to_mention[member.name] = f'<@{uid}>'
                uname_to_mention[member.display_name] = f'<@{uid}>'

    # Bot mention
    bot_mention = None
    bot_uid = None
    if message.guild:
        bot_member = message.guild.get_member(message.guild.me.id)
        if bot_member:
            bot_mention = bot_member.mention
            bot_uid = str(bot_member.id)

    if bot_mention:
        answer = _re.sub(r'(?<!<@)@?gronk(?!>)', bot_mention, answer, flags=_re.IGNORECASE)

    for uid, mention in uid_to_mention.items():
        if bot_uid and uid == bot_uid:
            continue
        answer = answer.replace(uid, mention)

    for uname, mention in uname_to_mention.items():
        if uname.lower() != 'gronk':
            answer = _re.sub(rf'(?<!<@){_re.escape(uname)}(?!>)', mention, answer)

    # Remove redundant patterns
    if bot_mention and bot_uid:
        answer = _re.sub(rf'{_re.escape(bot_mention)} ?\(user ID ?<?@!?{bot_uid}>?\)', bot_mention, answer)
        answer = _re.sub(rf'{_re.escape(bot_mention)} ?\(user ID ?{bot_uid}\)', bot_mention, answer)

    answer = convert_usernames_to_mentions(answer, message.guild)
    answer = _re.sub(r'(\<@!?\d+\>) ?\(user ID \1\)', r'\1', answer)
    answer = _re.sub(r'(\<@!?\d+\>) ?\(which is \1\)', r'\1', answer)
    answer = _re.sub(r'(\<@!?\d+\>) ?\(user ID @\d+\)', r'\1', answer)
    answer = _re.sub(r'(@\d+) ?\(which is \<@!?\d+\>\)', r'\1', answer)

    return answer


# ---------------------------------------------------------------------------
# Embed building
# ---------------------------------------------------------------------------

def _build_history_embeds(
    answer: str,
    title: str,
    messages_for_context: list[discord.Message],
    collected_count: int,
    messages_analyzed: int,
    usage_text: str,
    message: discord.Message,
) -> list[discord.Embed]:
    """Build one or more Discord embeds, splitting if the answer exceeds 4096 chars."""
    embeds: list[discord.Embed] = []

    if len(answer) <= 4096:
        embed = discord.Embed(
            title=title, description=answer,
            color=discord.Color.purple(), timestamp=message.created_at,
        )
        embed.set_author(
            name="Grok Analysis",
            icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg",
        )
        analyzed_text = f"{messages_analyzed} messages analyzed"
        if collected_count > messages_analyzed:
            analyzed_text += f" ({collected_count} found)"
        if messages_for_context:
            oldest = messages_for_context[-1]
            oldest_dt = oldest.created_at.astimezone(TIMEZONE)
            analyzed_text += f" • Oldest: {oldest_dt.strftime('%Y-%m-%d %H:%M %Z')}"
        footer = f"Requested by {message.author.display_name}"
        if usage_text:
            footer += f" • {usage_text}"
        embed.set_footer(text=footer, icon_url=message.author.avatar.url if message.author.avatar else None)
        embeds.append(embed)
    else:
        # Split into multiple embeds by paragraphs
        paragraphs = answer.split('\n\n')
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > 4096:
                if current:
                    chunks.append(current.rstrip())
                    current = ""
                if len(para) > 4096:
                    for i in range(0, len(para), 4096):
                        chunks.append(para[i:i+4096])
                else:
                    current = para + '\n\n'
            else:
                current += para + '\n\n'
        if current.strip():
            chunks.append(current.rstrip())

        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"{title} (Part {i+1}/{len(chunks)})" if i > 0 else title,
                description=chunk,
                color=discord.Color.purple(),
                timestamp=message.created_at,
            )
            embed.set_author(
                name="Grok Analysis",
                icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg",
            )
            if i == len(chunks) - 1:
                analyzed_text = f"{messages_analyzed} messages analyzed"
                if collected_count > messages_analyzed:
                    analyzed_text += f" ({collected_count} found)"
                if messages_for_context:
                    oldest = messages_for_context[-1]
                    oldest_dt = oldest.created_at.astimezone(TIMEZONE)
                    analyzed_text += f"\nOldest: {oldest_dt.strftime('%Y-%m-%d %H:%M %Z')}"
                footer = f"Requested by {message.author.display_name}"
                if usage_text:
                    footer += f" • {usage_text}"
                embed.set_footer(text=footer, icon_url=message.author.avatar.url if message.author.avatar else None)
            embeds.append(embed)

    return embeds


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def perform_discord_history_search(
    message: discord.Message,
    query: str,
    time_limit: Optional[int] = None,
    keywords: Optional[str] = None,
    target_user: Optional[discord.User] = None,
) -> None:
    """Search Discord history and analyze with Grok."""
    use_keyword_filter = keywords is not None

    if use_keyword_filter:
        if time_limit is None:
            time_limit = DEFAULT_SEARCH_LIMIT
        max_scan = min(time_limit, MAX_KEYWORD_SCAN)
    else:
        max_scan = MAX_MESSAGES_ANALYZED
        time_limit = max_scan

    # Send progress message
    if target_user:
        if use_keyword_filter:
            searching_msg = await message.reply(
                f"🔍 Analyzing {target_user.mention}'s messages about `{keywords}` (scanning up to {time_limit:,} messages)...")
        else:
            searching_msg = await message.reply(
                f"🔍 Analyzing {target_user.mention}'s message history (last {max_scan:,} messages)...")
    else:
        if use_keyword_filter:
            searching_msg = await message.reply(
                f"🔍 Analyzing channel messages about `{keywords}` (scanning up to {time_limit:,} messages)...")
        else:
            searching_msg = await message.reply(
                f"🔍 Analyzing channel message history (last {max_scan:,} messages)...")

    try:
        # --- Collect messages ---
        collected = await _collect_messages(
            message, max_scan, target_user, use_keyword_filter, keywords, searching_msg)

        if not collected:
            await searching_msg.edit(content="❌ No messages found matching your criteria.")
            return

        logger.info('Found %d messages for analysis', len(collected))

        # --- Build prompt ---
        analyze_count = min(len(collected), MAX_MESSAGES_ANALYZED)
        context_msgs = collected[:analyze_count]
        full_prompt, _ = _build_history_prompt(query, context_msgs, len(collected), target_user)

        # --- Query Grok ---
        async with message.channel.typing():
            system_prompt = "You are a helpful assistant analyzing Discord message history. Follow JSON output format exactly."
            response, usage, _, _ = await sdk_chat_request(
                model=GROK_TEXT_MODEL,
                system_prompt=system_prompt,
                user_prompt=full_prompt,
                include_search=False,
                response_format=DiscordHistoryAnswer,
                reasoning_effort=GROK_ANALYSIS_REASONING_EFFORT,
                conversation_id=build_cache_conversation_id('history', message.channel.id, message.author.id),
            )

            # --- Process response ---
            sources: dict = {}
            answer = _process_history_response(response, sources, message)

            # --- Format cost ---
            usage_text = ""
            if usage:
                usage_text = format_cost(
                    GROK_TEXT_MODEL,
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                )

            # --- Build and send embeds ---
            await searching_msg.delete()

            title = "🔍 Discord History Analysis"
            if target_user:
                title += f": {target_user.display_name}"

            embeds = _build_history_embeds(
                answer, title, context_msgs, len(collected), analyze_count, usage_text, message)
            for embed in embeds:
                await message.reply(embed=embed)

        logger.info('Discord history analysis completed')

    except Exception as e:
        logger.error('Error in Discord history search: %s', e, exc_info=True)
        try:
            await searching_msg.edit(content=f"❌ Error analyzing messages: {str(e)}")
        except Exception:
            await message.reply(f"❌ Error analyzing messages: {str(e)}")
