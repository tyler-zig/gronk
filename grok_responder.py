import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import discord
from xai_sdk.chat import file as xai_file
from xai_sdk.chat import system as xai_system
from xai_sdk.chat import user as xai_user

from config import (
    ENABLE_WEB_SEARCH,
    GROK_ANALYSIS_REASONING_EFFORT,
    GROK_DOCUMENT_MODEL,
    GROK_REASONING_EFFORT,
    GROK_TEXT_MODEL,
    GROK_VISION_MODEL,
)
from conversation_store import store_conversation
from continue_thread import ContinueThreadView
from cost_utils import format_cost
from document_utils import delete_grok_files, upload_documents_to_grok
from grok_client import (
    build_cache_conversation_id,
    normalize_sdk_reasoning_effort,
    sdk_chat_request,
)
from grok_schemas import GrokAnswer
from persona_manager import get_active_persona
from verbosity import resolve_verbosity, verbosity_prompt_modifier


logger = logging.getLogger('GrokBot')


@dataclass
class _ResponseData:
    """Internal container for Grok response content and usage info.

    Replaces the previous MockCompletion / SdkMockUsage / DocumentMockUsage
    classes so that all three code paths (SDK vision, SDK document, SDK text)
    produce the same well-defined shape consumed by the embed builder.
    """
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    tool_invocations: int = 0
    has_images: bool = False

    @property
    def usage_text(self) -> str:
        if not self.prompt_tokens and not self.completion_tokens:
            return ""
        return format_cost(
            self.model, self.prompt_tokens, self.completion_tokens,
            self.cached_tokens, self.tool_invocations,
            has_images=self.has_images,
        )


def _extract_answer_and_sources(response: str) -> tuple[str, list]:
    """Parse Grok JSON response into (answer, sources).  Falls back to raw text."""
    json_str = response.strip()
    # Strip optional code-fence wrapper
    m = re.match(r'^```(?:json)?\s*\n?([\s\S]*?)\n?```$', json_str, re.DOTALL)
    if m:
        json_str = m.group(1).strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning('Grok returned non-JSON content; using raw response text')
        return response.strip(), []

    return data.get("answer", "(No answer)"), data.get("sources", [])


def _add_sources(embed: discord.Embed, sources: list) -> None:
    """Append a Sources field to the embed, filtering internal xAI citations."""
    if not sources:
        return

    formatted: list[str] = []
    for src in sources:
        if re.match(r'^(post:\d+|X User Result \d+|x_\w+|web_search|code_execution)',
                    src, re.IGNORECASE):
            continue
        m = re.match(r"\[.*?\]\((https?://[^)]+)\)", src)
        if m:
            formatted.append(m.group(1))
        elif re.match(r"https?://", src):
            formatted.append(src)
        else:
            m = re.search(r"(https?://\S+)", src)
            if m:
                formatted.append(m.group(1))

    if formatted:
        embed.add_field(name="Sources", value="\n".join(formatted), inline=False)


def _apply_persona(system_prompt: str, persona: Optional[dict],
                   verbosity_mod: str = "") -> str:
    if persona:
        system_prompt = (
            f"{system_prompt}\n\n"
            f"Active persona for this Discord channel: {persona['name']}.\n"
            f"Persona summary: {persona.get('summary', '')}\n"
            f"Persona system prompt:\n{persona['system_prompt']}"
        )
    if verbosity_mod:
        system_prompt = f"{system_prompt}\n\n{verbosity_mod}"
    return system_prompt


async def handle_grok_query(message: discord.Message, bot: discord.Client,
                            prompt: str, image_urls: list[str],
                            document_attachments: list,
                            conversation_messages: list[dict],
                            previous_xai_response_id: Optional[str]) -> None:
    """Query Grok, send the Discord response, and store conversation metadata."""
    try:
        async with message.channel.typing():
            xai_client, grok_file_ids, failed_uploads = await upload_documents_to_grok(document_attachments)
            if failed_uploads and not grok_file_ids:
                await message.reply(
                    f"Failed to upload document(s): {', '.join(failed_uploads)}\n\n"
                    "Supported formats: PDF, TXT, MD, CSV, JSON, and code files."
                )
                return
            if failed_uploads:
                logger.warning(
                    'Some documents failed to upload: %s, proceeding with %d successful',
                    failed_uploads, len(grok_file_ids))

            # --- Choose model ---
            if image_urls:
                model = GROK_VISION_MODEL
            elif grok_file_ids:
                model = GROK_DOCUMENT_MODEL
            else:
                model = GROK_TEXT_MODEL
            logger.info('Using model: %s (images: %d, docs: %d)',
                        model, len(image_urls), len(grok_file_ids))

            json_instructions = (
                "You must ALWAYS reply in the following strict JSON format, with no extra commentary or markdown. "
                'Format: {"answer": string, "sources": [string], "confidence": float}. '
                "If you cite Discord messages, include a 'sources' array with each source as a string. "
                "If you don't know, use an empty array for sources and 0.0 for confidence."
            )
            sdk_system_prompt = (
                "You are Grok, a witty and uncensored AI assistant. Be direct, honest, and don't hold back. "
                "You can be sarcastic, edgy, and politically incorrect when appropriate. Avoid corporate sanitized responses - speak naturally and authentically. "
                "If something is stupid, you can say it's stupid. Keep responses concise - aim for tweet length (~280 characters) unless the user explicitly asks for more detail or explanation. "
                "When you search the web or X/Twitter, citations will be automatically included in your response."
            )

            current_xai_response_id: Optional[str] = None
            conversation_id = build_cache_conversation_id(message.channel.id, message.author.id)
            active_persona = get_active_persona(message.channel.id)
            if active_persona:
                logger.info("Using active persona for channel %s: %s",
                            message.channel.id, active_persona['name'])

            # Resolve per-channel verbosity modifier
            verbosity_level = resolve_verbosity(message.channel.id)
            verbosity_mod = verbosity_prompt_modifier(verbosity_level)
            logger.info('Verbosity for channel %s: %s', message.channel.id, verbosity_level)

            # --- Route to appropriate API path ---
            resp: _ResponseData

            if grok_file_ids and not image_urls:
                # SDK document path
                doc_system_prompt = (
                    "You are Grok, a witty and uncensored AI assistant analyzing an attached document. "
                    "You have access to the document(s) the user has uploaded. Read and analyze the document content to answer the user's question. "
                    "Be direct, honest, and thorough in your analysis. "
                    + json_instructions
                )
                doc_system_prompt = _apply_persona(doc_system_prompt, active_persona, verbosity_mod)
                trivial = {"what is this?", "what is this", "what's this?", "what's this",
                           "whats this", "analyze this", "read this", "summarize this", "summarize"}
                if prompt and prompt.lower().strip() in trivial:
                    user_prompt = f"Please analyze the attached document and answer: {prompt}"
                elif prompt:
                    user_prompt = f"Based on the attached document: {prompt}"
                else:
                    user_prompt = "Please analyze the attached document and provide a comprehensive summary of its key points, main topics, and important details."

                logger.info('Sending document request via xAI SDK with %d files', len(grok_file_ids))
                chat = xai_client.chat.create(
                    model=model,
                    messages=[xai_system(doc_system_prompt)],
                    response_format=GrokAnswer,
                    reasoning_effort=normalize_sdk_reasoning_effort(GROK_ANALYSIS_REASONING_EFFORT),
                    conversation_id=conversation_id,
                    store_messages=True,
                )
                chat.append(xai_user(user_prompt, *[xai_file(fid) for fid in grok_file_ids]))
                sdk_response, parsed_response = await chat.parse(GrokAnswer)
                if sdk_response and hasattr(sdk_response, 'id'):
                    current_xai_response_id = sdk_response.id
                    logger.info('Document analysis response ID: %s', current_xai_response_id)

                sdk_usage = sdk_response.usage if sdk_response and hasattr(sdk_response, 'usage') else None
                resp = _ResponseData(
                    content=(parsed_response.model_dump_json()
                             if hasattr(parsed_response, 'model_dump_json')
                             else parsed_response.json()),
                    model=model,
                    prompt_tokens=sdk_usage.prompt_tokens if sdk_usage else 0,
                    completion_tokens=sdk_usage.completion_tokens if sdk_usage else 0,
                )
                await delete_grok_files(xai_client, grok_file_ids)

            else:
                # SDK chat path: text and/or native image understanding
                sdk_system = _apply_persona(sdk_system_prompt, active_persona, verbosity_mod)
                if image_urls:
                    logger.info('Sending request to Grok with %d image(s)', len(image_urls))
                elif previous_xai_response_id:
                    logger.info('Continuing conversation with xAI response ID: %s (server-side memory)',
                                previous_xai_response_id)
                else:
                    logger.info('Sending text-only request to Grok via SDK (history: %d)',
                                len(conversation_messages))

                response, sdk_usage, _, new_response_id = await sdk_chat_request(
                    model=model,
                    system_prompt=sdk_system,
                    user_prompt=prompt,
                    conversation_history=(
                        conversation_messages
                        if image_urls or not previous_xai_response_id
                        else None
                    ),
                    include_search=ENABLE_WEB_SEARCH,
                    previous_response_id=None if image_urls else previous_xai_response_id,
                    response_format=GrokAnswer,
                    reasoning_effort=(
                        GROK_ANALYSIS_REASONING_EFFORT if image_urls else GROK_REASONING_EFFORT
                    ),
                    conversation_id=conversation_id,
                    image_urls=image_urls or None,
                )
                # Image turns are not stored on xAI, so don't chain later requests from this ID.
                current_xai_response_id = None if image_urls else new_response_id
                resp = _ResponseData(
                    content=response,
                    model=model,
                    prompt_tokens=sdk_usage.get('prompt_tokens', 0) if sdk_usage else 0,
                    completion_tokens=sdk_usage.get('completion_tokens', 0) if sdk_usage else 0,
                    cached_tokens=sdk_usage.get('cached_tokens', 0) if sdk_usage else 0,
                    tool_invocations=sdk_usage.get('tool_invocations', 0) if sdk_usage else 0,
                    has_images=bool(image_urls),
                )
                if grok_file_ids:
                    await delete_grok_files(xai_client, grok_file_ids)

            # --- Parse and build embed ---
            logger.info('Received response from Grok (%d characters)', len(resp.content))
            try:
                answer, sources = _extract_answer_and_sources(resp.content)
            except Exception as e:
                logger.error('Failed to parse Grok JSON: %s\nRaw response: %s', e, resp.content)
                await message.reply("❌ Grok did not return valid JSON. Please try again.")
                return

            embed = discord.Embed(description=answer, color=discord.Color.blue())
            embed.set_author(
                name="Grok Response",
                icon_url="https://pbs.twimg.com/profile_images/1683899100922511378/5lY42eHs_400x400.jpg"
            )
            _add_sources(embed, sources)

            footer_parts = [f"Requested by {message.author.display_name}"]
            usage_str = resp.usage_text
            if usage_str:
                footer_parts.append(usage_str)
            if active_persona:
                footer_parts.append(f"Persona: {active_persona['name']}")
            embed.set_footer(
                text=" • ".join(footer_parts),
                icon_url=message.author.avatar.url if message.author.avatar else None,
            )

            bot_message = await message.reply(embed=embed, view=ContinueThreadView())
            original_prompt = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
            store_conversation(
                message_id=bot_message.id,
                channel_id=message.channel.id,
                author_id=message.author.id,
                user_query=original_prompt,
                bot_response=answer,
                model_used=model,
                xai_response_id=current_xai_response_id,
            )
            logger.info('Stored conversation history for bot message %s (asked by user %s)',
                        bot_message.id, message.author.id)
            logger.info('Response sent successfully')

    except Exception as e:
        logger.error('Error querying Grok: %s', e, exc_info=True)

        error_msg = str(e)
        if "412" in error_msg and "Unsupported content-type" in error_msg:
            await message.reply(
                "❌ One or more images are in an unsupported format. "
                "Grok only accepts JPEG, PNG, and WebP images.\n\n"
                "Please try again with supported image formats."
            )
        elif "401" in error_msg or "authentication" in error_msg.lower():
            await message.reply("❌ Authentication error. Please check the API key configuration.")
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            await message.reply("⏳ Rate limit reached. Please try again in a few moments.")
        elif "timeout" in error_msg.lower():
            await message.reply("⏳ Request timed out. Please try again.")
        else:
            await message.reply(f"❌ Error querying Grok: {error_msg}")
