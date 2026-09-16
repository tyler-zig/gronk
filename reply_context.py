"""Reply-chain and thread-native context gathering for Grok prompts."""

import logging

import discord

from media_utils import collect_attachment_media, collect_embed_media, collect_image_urls_from_text


logger = logging.getLogger('GrokBot')

# How many thread messages to include as context (most recent first).
MAX_THREAD_CONTEXT = 20


async def _gather_reply_chain_context(message, image_urls) -> list[discord.Message]:
    """Walk the reply chain backwards and collect context messages.

    Returns context messages in chronological order.
    """
    reply_chain: list[discord.Message] = []
    current = message
    depth = 0
    max_depth = 10

    while current.reference and depth < max_depth:
        try:
            replied = await message.channel.fetch_message(current.reference.message_id)
            reply_chain.insert(0, replied)
            current = replied
            depth += 1
        except Exception:
            break

    if not reply_chain:
        return []

    logger.info('Found %d messages in reply chain', len(reply_chain))

    context_msgs: list[discord.Message] = []
    time_window = 120  # seconds

    # Messages just before the chain
    oldest = reply_chain[0]
    try:
        before: list[discord.Message] = []
        async for msg in message.channel.history(limit=10, before=oldest.created_at):
            if msg.id != oldest.id and not msg.author.bot:
                if (oldest.created_at - msg.created_at).total_seconds() <= time_window:
                    before.append(msg)
                else:
                    break
        before.reverse()
        context_msgs.extend(before)
        logger.info('Found %d recent messages before reply chain (within 2 min)', len(before))
    except Exception:
        pass

    context_msgs.extend(reply_chain)

    # Messages just after the chain
    newest = reply_chain[-1]
    try:
        after: list[discord.Message] = []
        async for msg in message.channel.history(limit=10, after=newest.created_at, oldest_first=True):
            if msg.id != newest.id and msg.id != message.id and not msg.author.bot:
                if (msg.created_at - newest.created_at).total_seconds() <= time_window:
                    after.append(msg)
                else:
                    break
        context_msgs.extend(after)
        logger.info('Found %d messages after reply chain (within 2 min)', len(after))
    except Exception:
        pass

    # Collect media from context
    for msg in context_msgs:
        collect_attachment_media(msg, image_urls, context_label='context')
        collect_image_urls_from_text(msg.content, image_urls, context_label='context')
        collect_embed_media(msg.embeds, image_urls, context_label='context')

    return context_msgs


async def _gather_thread_context(message, image_urls) -> list[discord.Message]:
    """Gather recent message history from a Discord thread.

    Returns messages in chronological order (oldest first), excluding the
    triggering message itself.
    """
    if not isinstance(message.channel, discord.Thread):
        return []

    logger.info('Message is in a thread (%s) — gathering thread context', message.channel.name)

    thread_msgs: list[discord.Message] = []
    try:
        # Collect up to MAX_THREAD_CONTEXT recent messages before the trigger,
        # walking backwards then reversing for chronological order.
        async for msg in message.channel.history(limit=MAX_THREAD_CONTEXT + 1, before=message.created_at):
            if msg.id != message.id:
                thread_msgs.append(msg)
        thread_msgs.reverse()
    except Exception:
        logger.warning('Could not fetch thread history', exc_info=True)

    if thread_msgs:
        logger.info('Found %d messages in thread history', len(thread_msgs))
        for msg in thread_msgs:
            collect_attachment_media(msg, image_urls, context_label='thread')
            collect_image_urls_from_text(msg.content, image_urls, context_label='thread')
            collect_embed_media(msg.embeds, image_urls, context_label='thread')

    return thread_msgs


def _format_context_messages(messages: list[discord.Message], label: str) -> list[str]:
    """Format a list of messages into context prompt parts."""
    if not messages:
        return []
    parts = [f"Here is the {label} context:\n"]
    for i, msg in enumerate(messages, 1):
        content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
        parts.append(f"[{i}] {msg.author.name}: {content}")
    return parts


async def add_reply_context(message, prompt, image_urls, previous_xai_response_id):
    """Fetch nearby conversation context and prepend it to the prompt.

    Priority order:
    1. If we have a server-side xAI response ID, skip local context entirely.
    2. If the message is inside a Discord thread, use thread history.
    3. Otherwise, walk the reply chain.
    """
    if previous_xai_response_id:
        logger.info(
            'Skipping context fetch — using xAI server-side history (response ID: %s)',
            previous_xai_response_id)
        return prompt

    # --- Thread-native context ---
    thread_msgs = await _gather_thread_context(message, image_urls)

    # --- Reply-chain context (only if not already in a thread) ---
    reply_msgs: list[discord.Message] = []
    if not thread_msgs and message.reference:
        logger.info('Message is a reply, fetching conversation context...')
        reply_msgs = await _gather_reply_chain_context(message, image_urls)

    # --- Build prompt ---
    context_msgs = thread_msgs or reply_msgs
    if not context_msgs:
        return prompt

    context_label = "thread" if thread_msgs else "conversation"
    parts = _format_context_messages(context_msgs, context_label)
    parts.append(f"\nUser's question: {prompt}")

    logger.info('Built context with %d total messages (%s)', len(context_msgs), context_label)
    return "\n".join(parts)
