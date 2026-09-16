"""Persistent "Continue in Thread" button for Grok responses.

When clicked, creates a Discord thread from the bot's response message so
the user can fork into a deeper conversation while preserving the xAI
server-side conversation chain for context continuity.
"""

import logging

import discord
from discord import Interaction, ui

from conversation_store import get_conversation


logger = logging.getLogger('GrokBot')

CONTINUE_THREAD_CUSTOM_ID = "grok_continue_thread"


class ContinueThreadView(ui.View):
    """Persistent view with a single button to fork the conversation into a thread."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="💬 Continue in Thread",
        style=discord.ButtonStyle.secondary,
        custom_id=CONTINUE_THREAD_CUSTOM_ID,
    )
    async def continue_in_thread(self, interaction: Interaction, button: ui.Button):
        """Create a thread from this response and invite the user to continue."""
        await interaction.response.defer(ephemeral=True)

        try:
            msg = interaction.message
            if not msg or not isinstance(msg.channel, discord.TextChannel):
                await interaction.followup.send(
                    "Threads can only be created from server text channels.",
                    ephemeral=True,
                )
                return

            # Look up the original query for a meaningful thread name
            stored = get_conversation(msg.id)
            original_query = ""
            if stored and stored.get('user_query'):
                original_query = stored['user_query']

            # Build a thread name (Discord caps at 100 chars)
            if original_query:
                thread_name = original_query[:80].strip()
                if len(original_query) > 80:
                    thread_name += "…"
            else:
                thread_name = "Grok conversation"

            # Create the thread from the bot's response message
            thread = await msg.create_thread(
                name=thread_name,
                auto_archive_duration=60,  # 1 hour of inactivity
            )

            # Send a context-setter message in the new thread
            welcome = (
                f"{interaction.user.mention} — continuing the conversation.\n"
                f"Just type your follow-up question here and I'll answer with "
                f"full context from this exchange."
            )
            if stored and stored.get('xai_response_id'):
                welcome += (
                    f"\n\n_💡 Server-side memory is active — I'll remember "
                    f"everything we discussed above._"
                )

            await thread.send(welcome)

            # Confirm to the user (ephemeral — only they see it)
            await interaction.followup.send(
                f"✅ Thread created: {thread.mention}",
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create threads in this channel.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error('Error creating continue thread: %s', e, exc_info=True)
            await interaction.followup.send(
                "❌ Couldn't create the thread. The channel may not support threads.",
                ephemeral=True,
            )
