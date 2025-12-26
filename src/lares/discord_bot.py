"""Discord bot interface for Lares."""

import os
from datetime import datetime

import discord
import structlog
from discord.ext import commands, tasks
from letta_client import Letta

from lares.config import Config
from lares.memory import MessageResponse, send_message, send_tool_result
from lares.response_parser import DiscordAction, parse_response
from lares.scheduler import get_scheduler
from lares.time_utils import get_time_context
from lares.tool_registry import ToolExecutor, handle_approval_reaction
from lares.tools import clear_discord_context, set_discord_context

log = structlog.get_logger()

# Perch time interval (default: 60 minutes)
PERCH_INTERVAL_MINUTES = int(os.getenv("LARES_PERCH_INTERVAL_MINUTES", "60"))


class LaresBot(commands.Bot):
    """Discord bot that interfaces with the Lares agent."""

    def __init__(self, config: Config, letta_client: Letta, agent_id: str):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.letta_client = letta_client
        self.agent_id = agent_id
        self.target_channel_id = config.discord.channel_id
        self.tool_executor = ToolExecutor(
            config.tools,
            letta_client=letta_client,
            agent_id=agent_id,
        )
        self._target_channel: discord.TextChannel | None = None

        # Maximum tool call iterations to prevent infinite loops
        # Load after config is initialized so .env is already loaded
        self.max_tool_iterations = int(os.getenv("LARES_MAX_TOOL_ITERATIONS", "10"))
        log.info("max_tool_iterations_configured", max_iterations=self.max_tool_iterations)

    def _get_time_context(self) -> str:
        """Get current time context string for message injection."""
        return get_time_context(self.config.user.timezone)

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        log.info("discord_bot_ready", user=str(self.user), channel_id=self.target_channel_id)
        print(f"Lares is online as {self.user}")

        # Set the Discord channel for tool approval requests
        channel = self.get_channel(self.target_channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            self._target_channel = channel
            self.tool_executor.set_channel(channel)

        # Initialize and start the job scheduler
        scheduler = get_scheduler()
        scheduler.set_callback(self._handle_scheduled_job)
        scheduler.start()

        # Start perch time loop
        if not self.perch_time.is_running():
            self.perch_time.start()
            log.info("perch_time_started", interval_minutes=PERCH_INTERVAL_MINUTES)

    async def _execute_actions(
        self,
        actions: list[DiscordAction],
        channel: discord.TextChannel,
        message: discord.Message | None = None,
    ) -> None:
        """
        Execute a list of Discord actions in order.

        Args:
            actions: List of DiscordAction objects to execute
            channel: The channel to send messages to
            message: Optional triggering message (for reactions/replies)
        """
        for action in actions:
            if action.type == "react" and message and action.emoji:
                try:
                    await message.add_reaction(action.emoji)
                    log.info("action_react", emoji=action.emoji)
                except discord.HTTPException as e:
                    log.warning("action_react_failed", emoji=action.emoji, error=str(e))

            elif action.type == "message" and action.content:
                await channel.send(action.content)
                log.info("action_message", preview=action.content[:50])

            elif action.type == "reply" and action.content:
                if message:
                    await message.reply(action.content)
                    log.info("action_reply", preview=action.content[:50])
                else:
                    # No message to reply to, send as regular message
                    await channel.send(action.content)
                    log.info("action_reply_as_message", preview=action.content[:50])

            elif action.type == "silent":
                log.info("action_silent")

    async def _handle_scheduled_job(self, job_id: str, prompt: str) -> None:
        """
        Handle a scheduled job firing.

        This is called by the scheduler when a job's time comes.
        We send the prompt to Letta and process any response.
        """
        log.info("scheduled_job_triggered", job_id=job_id)

        if not self._target_channel:
            log.error("scheduled_job_no_channel", job_id=job_id)
            return

        time_context = self._get_time_context()

        # Format the prompt with context
        full_prompt = f"""[SCHEDULED JOB: {job_id}]
{time_context}

{prompt}

(This message was triggered by a scheduled job you created. Respond naturally,
or use [silent] if no response is needed.)"""

        try:
            response = send_message(self.letta_client, self.agent_id, full_prompt)

            # Check if memory compaction was detected
            if response.needs_retry:
                log.info("memory_compaction_during_scheduled_job", job_id=job_id)
                # Send a friendly notification
                await self._target_channel.send("💭 *Reorganizing my thoughts...*")

                # Retry the message
                response = send_message(
                    self.letta_client,
                    self.agent_id,
                    full_prompt,
                    retry_on_compaction=False,
                )

            # Process response with streaming actions (no message to react to)
            await self._process_response_streaming(response, self._target_channel, message=None)

            log.info("scheduled_job_complete", job_id=job_id)

        except Exception as e:
            log.error("scheduled_job_failed", job_id=job_id, error=str(e))

    async def _process_response_streaming(
        self,
        response: MessageResponse,
        channel: discord.TextChannel,
        message: discord.Message | None = None,
    ) -> None:
        """
        Process a response, executing actions as they come in.

        This enables the 👀 → work → ✅ flow by executing actions
        from EACH response in the tool chain, not just the final one.

        Args:
            response: Initial response from Letta
            channel: Discord channel for messages
            message: Optional triggering message (for reactions/replies)
        """
        # Set Discord context for tools (discord_react, discord_send_message)
        set_discord_context(channel, self, message)

        try:
            iterations = 0

            # Process initial response text (might have 👀 reaction)
            if response.text:
                actions = parse_response(response.text)
                log.info(
                    "streaming_actions",
                    phase="initial",
                    count=len(actions),
                    actions=[(a.type, a.emoji) for a in actions],
                )
                await self._execute_actions(actions, channel, message)

            while response.pending_tool_calls and iterations < self.max_tool_iterations:
                iterations += 1

                log.info(
                    "tool_chain_iteration",
                    iteration=iterations,
                    pending_count=len(response.pending_tool_calls),
                    pending_tools=[
                        (tc.name, tc.tool_call_id[:20]) for tc in response.pending_tool_calls
                    ],
                )

                for tool_call in response.pending_tool_calls:
                    log.info(
                        "executing_tool",
                        tool=tool_call.name,
                        tool_call_id=tool_call.tool_call_id,
                    )

                    # Execute tool locally (errors are returned as strings)
                    result = await self.tool_executor.execute(
                        tool_call.name,
                        tool_call.arguments,
                    )

                    # Send result back to Letta
                    try:
                        response = send_tool_result(
                            self.letta_client,
                            self.agent_id,
                            tool_call.tool_call_id,
                            result,
                            "success",
                        )

                        # Check if memory compaction was detected during tool execution
                        if response.needs_retry:
                            log.info("memory_compaction_during_tool", tool=tool_call.name)
                            # Send a friendly notification
                            await channel.send("💭 *Reorganizing my thoughts...*")

                            # Retry sending the tool result
                            response = send_tool_result(
                                self.letta_client,
                                self.agent_id,
                                tool_call.tool_call_id,
                                result,
                                "success",
                                retry_on_compaction=False,  # Don't retry again
                            )

                    except Exception as e:
                        # Letta API error - notify user and abort tool chain
                        log.error(
                            "send_tool_result_failed",
                            tool=tool_call.name,
                            tool_call_id=tool_call.tool_call_id,
                            error=str(e),
                        )
                        args_preview = str(tool_call.arguments)[:100]
                        await channel.send(
                            f"⚠️ **Tool failed:** `{tool_call.name}`\n"
                            f"```\n{args_preview}\n```\n"
                            f"Error: {e}"
                        )
                        # Can't continue the tool chain - Letta state is inconsistent
                        return

                    # Execute any actions from this response immediately
                    if response.text:
                        actions = parse_response(response.text)
                        log.info(
                            "streaming_actions",
                            phase=f"after_tool_{iterations}",
                            count=len(actions),
                            actions=[(a.type, a.emoji) for a in actions],
                        )
                        await self._execute_actions(actions, channel, message)

                    # Always break after processing one tool call - the response has been
                    # updated, so we need to check the NEW response's pending_tool_calls
                    # in the while loop, not continue iterating over the old list
                    break

            if iterations >= self.max_tool_iterations:
                log.warning(
                    "max_tool_iterations_reached",
                    iterations=iterations,
                    max=self.max_tool_iterations,
                )

        finally:
            # Always clean up Discord context
            clear_discord_context()

    @tasks.loop(minutes=PERCH_INTERVAL_MINUTES)
    async def perch_time(self) -> None:
        """Autonomous tick - Lares wakes up to think, journal, and optionally act."""
        await self.wait_until_ready()

        log.info("perch_time_tick", timestamp=datetime.now().isoformat())

        channel = self.get_channel(self.target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            log.error("perch_time_channel_not_found", channel_id=self.target_channel_id)
            return

        # Include time context in perch prompt
        time_context = self._get_time_context()

        perch_prompt = f"""[PERCH TIME - {datetime.now().strftime("%Y-%m-%d %H:%M")}]
{time_context}

This is your autonomous perch time tick. You have {PERCH_INTERVAL_MINUTES} minutes between ticks.

Available tools:
- discord_react(emoji): React to messages with emoji (👀, ✅, 👍, etc.)
- discord_send_message(content, reply): Send messages to Discord
- run_command(command, working_dir): Execute shell commands (git, pytest, ruff, etc.)
- read_file(path): Read files from allowed paths
- write_file(path, content): Write/create files in allowed paths
- schedule_job(job_id, prompt, schedule, description): Schedule reminders/tasks
- remove_job(job_id): Remove a scheduled job
- list_jobs(): See all scheduled jobs
- read_rss_feed(url, max_entries): Read RSS/Atom feeds for news and updates
- read_bluesky_user(handle, limit): Read posts from a BlueSky user
- search_bluesky(query, limit): Search BlueSky posts
- post_to_bluesky(text): Post to BlueSky (requires approval)
- search_obsidian_notes(query, max_results): Search notes in Obsidian vault
- read_obsidian_note(path): Read a specific note from Obsidian
- restart_lares(): Restart yourself to apply updates or configuration changes
- create_tool(source_code): Create new tools to extend your capabilities (requires approval)

Take a moment to:
1. Reflect on recent interactions and update your memory if needed
2. Check your ideas/roadmap and consider what you could work on
3. Use your tools to make progress on a task (git operations, code changes, etc.)
4. Optionally send a message to Daniele if you have something to share

You can respond with:
- A message to send to Discord (I'll post it)
- Just "[silent]" if you prefer to stay quiet this tick
- Or "[thinking]" followed by your reflections (I won't post these)

What would you like to do?"""

        try:
            response = send_message(self.letta_client, self.agent_id, perch_prompt)

            # Check if memory compaction was detected
            if response.needs_retry:
                log.info("memory_compaction_during_perch_time")
                # Send a friendly notification
                await channel.send("💭 *Reorganizing my thoughts...*")

                # Retry the message - crucial for perch time to complete its tasks
                response = send_message(
                    self.letta_client,
                    self.agent_id,
                    perch_prompt,
                    retry_on_compaction=False,
                )

            # Process response with streaming actions (no message to react to)
            await self._process_response_streaming(response, channel, message=None)

            log.info("perch_time_complete")

        except Exception as e:
            log.error("perch_time_failed", error=str(e))

    @perch_time.before_loop
    async def before_perch_time(self) -> None:
        """Wait for bot to be ready before starting perch time."""
        await self.wait_until_ready()

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Ignore our own messages
        if message.author == self.user:
            return

        # Only respond in the configured channel
        if message.channel.id != self.target_channel_id:
            return

        # Ignore bot commands (let commands extension handle them)
        if message.content.startswith("!"):
            await self.process_commands(message)
            return

        log.info(
            "received_message",
            author=str(message.author),
            content_preview=message.content[:50],
        )

        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return

        # Show typing indicator while processing
        async with channel.typing():
            try:
                # Include time context in message
                time_context = self._get_time_context()

                formatted_message = (
                    f"{time_context}\n\n"
                    f"[Discord message from {message.author.display_name}]: {message.content}"
                )

                response = send_message(
                    self.letta_client,
                    self.agent_id,
                    formatted_message,
                )

                # Check if memory compaction was detected
                if response.needs_retry:
                    log.info("memory_compaction_during_message")
                    # Send a friendly notification
                    await channel.send("💭 *Reorganizing my thoughts...*")

                    # Retry the message
                    response = send_message(
                        self.letta_client,
                        self.agent_id,
                        formatted_message,
                        retry_on_compaction=False,  # Don't retry again
                    )

                # Process response with streaming actions
                await self._process_response_streaming(response, channel, message)

            except Exception as e:
                log.error("message_processing_failed", error=str(e))
                await message.add_reaction("❌")

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        """Handle reaction additions for approval workflow."""
        if user == self.user:
            return

        if reaction.message.channel.id != self.target_channel_id:
            return

        # Check if this is an approval reaction
        result = await handle_approval_reaction(
            reaction.message.id,
            str(reaction.emoji),
            user,
        )

        if result is not None:
            approved, command = result
            if approved:
                log.info("command_approval_granted", command=command, user=str(user))
            else:
                log.info("command_approval_denied", command=command, user=str(user))

    async def close(self) -> None:
        """Clean up when bot is closing."""
        # Shutdown scheduler
        scheduler = get_scheduler()
        scheduler.shutdown()
        await super().close()


def create_bot(config: Config, letta_client: Letta, agent_id: str) -> LaresBot:
    """Create and configure the Discord bot."""
    return LaresBot(config, letta_client, agent_id)
