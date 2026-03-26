"""MIT License

Copyright (c) 2023 - present Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional

import discord
import voicelink

from discord import app_commands
from discord.ext import commands
from function import (
    TempCtx,
    cooldown_check,
    get_aliases,
    get_settings,
    get_user,
    send,
    settings,
    time as ctime,
    truncate_string,
    update_settings,
    update_user,
)


RADIO_STATIONS = {
    "lofi": {
        "url": "https://ice2.somafm.com/groovesalad-128-mp3",
        "label": "Groove Salad",
        "description": "Ambient and lofi-style chill stream.",
    },
    "jazz": {
        "url": "https://ice2.somafm.com/sonicuniverse-128-mp3",
        "label": "Sonic Universe",
        "description": "Modern and groove-heavy jazz radio.",
    },
    "spy": {
        "url": "https://ice5.somafm.com/secretagent-128-mp3",
        "label": "Secret Agent",
        "description": "Downtempo and cinematic lounge radio.",
    },
}

SOUNDBOARD_PRESETS = {
    "airhorn": "airhorn sound effect",
    "sadviolin": "sad violin sound effect",
    "bruh": "bruh sound effect",
    "clap": "applause sound effect",
    "drumroll": "drum roll sound effect",
}

AUDIO_PRESETS = {
    "bass+": voicelink.Equalizer.bass_medium,
    "heavybass": voicelink.Equalizer.bass_heavy,
    "treble": voicelink.Equalizer.treble,
    "flat": voicelink.Equalizer.flat,
}

AUDIO_PRESET_LABELS = {
    "bass+": "Bass+",
    "heavybass": "Heavy Bass",
    "treble": "Treble",
    "flat": "Flat",
}


@dataclass
class QuizSession:
    guild_id: int
    channel_id: int
    track_title: str
    track_author: str
    started_by: int
    ends_at: float
    revealed: bool = False

    @property
    def answers(self) -> set[str]:
        variants = {
            normalize_text(self.track_title),
            normalize_text(f"{self.track_author} {self.track_title}"),
            normalize_text(f"{self.track_title} {self.track_author}"),
        }
        return {value for value in variants if value}


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


async def ensure_player(ctx: commands.Context) -> voicelink.Player:
    player: voicelink.Player = ctx.guild.voice_client
    if not player:
        player = await voicelink.connect_channel(ctx)
    return player


async def ensure_access(ctx: commands.Context) -> voicelink.Player:
    player: voicelink.Player = ctx.guild.voice_client
    if not player:
        raise voicelink.VoicelinkException("There is no active player in this server.")

    if not player.is_user_join(ctx.author):
        raise voicelink.VoicelinkException(
            player.get_msg("notInChannel").format(ctx.author.mention, player.channel.mention)
        )
    return player


class Advanced(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.description = "Advanced music utilities such as radio, sleep timer, quiz, favorites, and Spotify activity."
        self.sleep_tasks: dict[int, asyncio.Task] = {}
        self.quiz_sessions: dict[int, QuizSession] = {}
        self.spotify_activity_cache: dict[tuple[int, int], tuple[str, float]] = {}

    def cog_unload(self) -> None:
        for task in self.sleep_tasks.values():
            task.cancel()

    async def radio_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        matches = []
        current = current.lower()
        for key, data in RADIO_STATIONS.items():
            if current and current not in key and current not in data["label"].lower():
                continue
            matches.append(app_commands.Choice(name=f"{data['label']} ({key})", value=key))
        return matches[:25]

    async def soundboard_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        matches = []
        current = current.lower()
        for key in SOUNDBOARD_PRESETS:
            if current and current not in key:
                continue
            matches.append(app_commands.Choice(name=key, value=key))
        return matches[:25]

    async def audio_preset_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        matches = []
        current = current.lower()
        for key, label in AUDIO_PRESET_LABELS.items():
            if current and current not in key and current not in label.lower():
                continue
            matches.append(app_commands.Choice(name=label, value=key))
        return matches[:25]

    def _cancel_sleep_timer(self, guild_id: int) -> bool:
        task = self.sleep_tasks.pop(guild_id, None)
        if task:
            task.cancel()
            return True
        return False

    async def _start_sleep_timer(self, ctx: commands.Context, player: voicelink.Player, minutes: int) -> None:
        self._cancel_sleep_timer(ctx.guild.id)
        trigger_at = time.time() + (minutes * 60)
        player.settings["sleep_timer"] = {"ends_at": trigger_at, "channel_id": ctx.channel.id}

        async def runner():
            try:
                await asyncio.sleep(minutes * 60)
                live_player: voicelink.Player = ctx.guild.voice_client
                if live_player and live_player.channel:
                    await send(ctx, f"Sleep timer finished after {minutes} minutes. Disconnecting from voice.")
                    await live_player.teardown()
            except asyncio.CancelledError:
                raise
            finally:
                current_player: voicelink.Player = ctx.guild.voice_client
                if current_player:
                    current_player.settings.pop("sleep_timer", None)
                self.sleep_tasks.pop(ctx.guild.id, None)

        self.sleep_tasks[ctx.guild.id] = self.bot.loop.create_task(runner())

    async def _play_query(
        self,
        ctx: commands.Context,
        query: str,
        *,
        at_front: bool = False,
        announce: Optional[str] = None,
    ) -> None:
        player = await ensure_player(ctx)
        if not player.is_user_join(ctx.author):
            await send(ctx, "notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)
            return

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            await send(ctx, "noTrackFound", ephemeral=True)
            return

        if isinstance(tracks, voicelink.Playlist):
            amount = await player.add_track(tracks.tracks, at_front=at_front)
            await send(ctx, announce or f"Loaded `{tracks.name}` with `{amount}` tracks.")
        else:
            track = tracks[0]
            position = await player.add_track(track, at_front=at_front)
            if announce:
                await send(ctx, announce)
            else:
                await send(
                    ctx,
                    f"Queued **{track.title}** by **{track.author}**"
                    + (" at the front of the queue." if at_front else ".")
                )
            if position == 1 and not player.is_playing:
                await player.do_next()
                return

        if not player.is_playing:
            await player.do_next()

    async def _get_spotify_activity(self, member: discord.Member) -> Optional[discord.Spotify]:
        for activity in member.activities:
            if isinstance(activity, discord.Spotify):
                return activity
        return None

    async def _queue_spotify_activity(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        at_front: bool = False,
    ) -> bool:
        activity = await self._get_spotify_activity(member)
        if not activity:
            await send(ctx, f"{member.mention} does not have a Spotify activity right now.", ephemeral=True)
            return False

        query = f"{activity.title} {', '.join(activity.artists)}"
        await self._play_query(
            ctx,
            query,
            at_front=at_front,
            announce=f"Queued Spotify activity: **{activity.title}** by **{', '.join(activity.artists)}**.",
        )
        return True

    @commands.hybrid_command(name="voteskip", aliases=get_aliases("voteskip"))
    @app_commands.describe(index="Optional queue index to skip to.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def voteskip(self, ctx: commands.Context, index: int = 0):
        "Cast a vote to skip the current song."
        player = await ensure_access(ctx)

        if not player.is_playing:
            return await send(ctx, "skipError", ephemeral=True)

        if player.is_privileged(ctx.author):
            if index:
                player.queue.skipto(index)
            await send(ctx, "skipped", ctx.author)
            if player.queue._repeat.mode == voicelink.LoopType.TRACK:
                await player.set_repeat(voicelink.LoopType.OFF)
            return await player.stop()

        if ctx.author == player.current.requester:
            if index:
                player.queue.skipto(index)
            await send(ctx, "skipped", ctx.author)
            if player.queue._repeat.mode == voicelink.LoopType.TRACK:
                await player.set_repeat(voicelink.LoopType.OFF)
            return await player.stop()

        if ctx.author in player.skip_votes:
            return await send(ctx, "voted", ephemeral=True)

        player.skip_votes.add(ctx.author)
        required = player.required()
        if len(player.skip_votes) < required:
            return await send(
                ctx,
                f"Vote skip registered: `{len(player.skip_votes)}/{required}` votes. Use `/voteskip` to help skip this song."
            )

        if index:
            player.queue.skipto(index)

        await send(ctx, f"Vote threshold reached with `{len(player.skip_votes)}/{required}` votes. Skipping now.")
        if player.queue._repeat.mode == voicelink.LoopType.TRACK:
            await player.set_repeat(voicelink.LoopType.OFF)
        await player.stop()

    @commands.hybrid_group(
        name="sleep",
        aliases=get_aliases("sleep"),
        invoke_without_command=True,
    )
    @app_commands.describe(minutes="Set minutes before the bot disconnects. Leave empty to view status.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def sleep(self, ctx: commands.Context, minutes: int = None):
        "Configure the sleep timer for the current player."
        player = await ensure_access(ctx)
        timer_data = player.settings.get("sleep_timer")

        if minutes is None:
            if not timer_data:
                return await send(ctx, "There is no active sleep timer in this server.")

            remaining = max(0, int(timer_data["ends_at"] - time.time()))
            return await send(ctx, f"Sleep timer ends in `{ctime(remaining * 1000)}`.")

        if minutes <= 0:
            cancelled = self._cancel_sleep_timer(ctx.guild.id)
            player.settings.pop("sleep_timer", None)
            return await send(ctx, "Sleep timer cancelled." if cancelled else "There is no active sleep timer to cancel.")

        await self._start_sleep_timer(ctx, player, minutes)
        await send(ctx, f"Sleep timer set for `{minutes}` minutes.")

    @sleep.command(name="cancel", aliases=get_aliases("sleepcancel"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def sleep_cancel(self, ctx: commands.Context):
        "Cancel the active sleep timer."
        player = await ensure_access(ctx)
        cancelled = self._cancel_sleep_timer(ctx.guild.id)
        player.settings.pop("sleep_timer", None)
        await send(ctx, "Sleep timer cancelled." if cancelled else "There is no active sleep timer to cancel.")

    @commands.hybrid_command(name="announcechannel", aliases=get_aliases("announcechannel"))
    @app_commands.describe(channel="Channel used for song start announcements. Leave empty to disable.")
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def announcechannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        "Set or disable the text channel used for song announcements."
        if channel:
            await update_settings(ctx.guild.id, {"$set": {"song_announcement_channel_id": channel.id}})
            await send(ctx, f"Song announcements will now be sent in {channel.mention}.")
            return

        await update_settings(ctx.guild.id, {"$unset": {"song_announcement_channel_id": None}})
        await send(ctx, "Song announcements have been disabled.")

    @commands.hybrid_command(name="audiopreset", aliases=get_aliases("audiopreset"))
    @app_commands.describe(preset="Quick EQ preset for the current player.")
    @app_commands.autocomplete(preset=audio_preset_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def audiopreset(self, ctx: commands.Context, preset: str):
        "Apply Bass+, Heavy Bass, Treble, or Flat audio presets."
        player = await ensure_access(ctx)

        if not player.is_privileged(ctx.author):
            return await send(ctx, "missingFunctionPerm", ephemeral=True)

        preset_key = normalize_text(preset)
        if preset_key not in AUDIO_PRESETS:
            return await send(ctx, "Unknown audio preset. Choose Bass+, Heavy Bass, Treble, or Flat.", ephemeral=True)

        try:
            await player.reset_filter(requester=ctx.author)
        except Exception:
            pass

        effect = AUDIO_PRESETS[preset_key]()
        await player.add_filter(effect, requester=ctx.author)
        await send(ctx, f"Applied audio preset **{AUDIO_PRESET_LABELS[preset_key]}**.")

    @commands.hybrid_command(name="radio", aliases=get_aliases("radio"))
    @app_commands.describe(station="Preset station name such as lofi, jazz, or spy.")
    @app_commands.autocomplete(station=radio_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def radio(self, ctx: commands.Context, *, station: str):
        "Play an online radio station."
        station_key = station.lower().strip()
        station_data = RADIO_STATIONS.get(station_key)
        if station_data:
            return await self._play_query(
                ctx,
                station_data["url"],
                announce=f"Streaming **{station_data['label']}**: {station_data['description']}",
            )

        await self._play_query(
            ctx,
            station,
            announce="Attempting to stream your custom radio input.",
        )

    @commands.hybrid_command(name="soundboard", aliases=get_aliases("soundboard"))
    @app_commands.describe(sound="Preset sound effect name like airhorn or sadviolin.")
    @app_commands.autocomplete(sound=soundboard_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def soundboard(self, ctx: commands.Context, sound: str):
        "Play a short sound effect by pushing it to the front of the queue."
        query = SOUNDBOARD_PRESETS.get(sound.lower().strip(), sound)
        await self._play_query(
            ctx,
            query,
            at_front=True,
            announce=f"Soundboard preset queued: **{sound}**.",
        )

    @commands.hybrid_group(
        name="favorites",
        aliases=get_aliases("favorites"),
        invoke_without_command=True,
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.user)
    async def favorites(self, ctx: commands.Context):
        "Show your saved favorite songs."
        user = await get_user(ctx.author.id, "playlist")
        tracks = user["200"]["tracks"]

        if not tracks:
            return await send(ctx, "Your favorites list is empty.")

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Favorites",
            color=settings.embed_color,
            description="",
        )

        lines = []
        for index, track_id in enumerate(tracks[:10], start=1):
            track = voicelink.decode(track_id)
            lines.append(
                f"`{index}.` [{truncate_string(track.get('title', 'Unknown'), 60)}]({track.get('uri', 'https://discord.com')})"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Total tracks: {len(tracks)}")
        await send(ctx, embed)

    @favorites.command(name="add", aliases=get_aliases("favoriteadd"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.user)
    async def favorites_add(self, ctx: commands.Context):
        "Save the currently playing song to your favorites."
        player = await ensure_access(ctx)
        track = player.current
        if not track:
            return await send(ctx, "noTrackPlaying", ephemeral=True)
        if track.is_stream:
            return await send(ctx, "playlistAddError", ephemeral=True)

        user = await get_user(ctx.author.id, "playlist")
        if track.track_id in user["200"]["tracks"]:
            return await send(ctx, "playlistRepeated", ephemeral=True)

        await update_user(ctx.author.id, {"$push": {"playlist.200.tracks": track.track_id}})
        await send(ctx, f"Added **{track.title}** to your favorites.")

    @favorites.command(name="play", aliases=get_aliases("favoriteplay"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.user)
    async def favorites_play(self, ctx: commands.Context):
        "Queue every song from your favorites."
        user = await get_user(ctx.author.id, "playlist")
        stored_tracks = user["200"]["tracks"]
        if not stored_tracks:
            return await send(ctx, "Your favorites list is empty.", ephemeral=True)

        player = await ensure_player(ctx)
        tracks = [
            voicelink.Track(track_id=track_id, info=voicelink.decode(track_id), requester=ctx.author)
            for track_id in stored_tracks
        ]
        amount = await player.add_track(tracks)
        await send(ctx, f"Queued `{amount}` favorite tracks.")
        if not player.is_playing:
            await player.do_next()

    @favorites.command(name="remove", aliases=get_aliases("favoriteremove"))
    @app_commands.describe(index="Favorite index to remove.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.user)
    async def favorites_remove(self, ctx: commands.Context, index: int):
        "Remove a song from your favorites by index."
        user = await get_user(ctx.author.id, "playlist")
        stored_tracks = user["200"]["tracks"]
        if not 0 < index <= len(stored_tracks):
            return await send(ctx, "Favorite index is out of range.", ephemeral=True)

        track_id = stored_tracks[index - 1]
        track = voicelink.decode(track_id)
        await update_user(ctx.author.id, {"$pull": {"playlist.200.tracks": track_id}})
        await send(ctx, f"Removed **{track.get('title', 'Unknown')}** from your favorites.")

    @commands.hybrid_command(name="musicquiz", aliases=get_aliases("musicquiz"))
    @app_commands.describe(duration="How many seconds users have to answer.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def musicquiz(self, ctx: commands.Context, duration: int = 30):
        "Start a music quiz using the song that is currently playing."
        player = await ensure_access(ctx)
        if not player.current:
            return await send(ctx, "noTrackPlaying", ephemeral=True)

        if ctx.guild.id in self.quiz_sessions:
            return await send(ctx, "A music quiz is already running in this server.", ephemeral=True)

        track = player.current
        duration = max(10, min(duration, 120))
        session = QuizSession(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            track_title=track.title,
            track_author=track.author,
            started_by=ctx.author.id,
            ends_at=time.time() + duration,
        )
        self.quiz_sessions[ctx.guild.id] = session
        await send(
            ctx,
            f"Music quiz started. Guess the title from the current snippet in `{duration}` seconds."
        )
        self.bot.loop.create_task(self._finish_quiz(ctx.guild.id))

    async def _finish_quiz(self, guild_id: int) -> None:
        session = self.quiz_sessions.get(guild_id)
        if not session:
            return

        wait_time = max(0.0, session.ends_at - time.time())
        await asyncio.sleep(wait_time)

        session = self.quiz_sessions.pop(guild_id, None)
        if not session or session.revealed:
            return

        guild = self.bot.get_guild(guild_id)
        channel = guild and guild.get_channel(session.channel_id)
        if channel:
            await channel.send(
                f"Time's up. The answer was **{session.track_title}** by **{session.track_author}**."
            )

    @commands.hybrid_group(
        name="spotifyactivity",
        aliases=get_aliases("spotifyactivity"),
        invoke_without_command=True,
    )
    @app_commands.describe(member="Member whose Spotify activity should be queued.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def spotifyactivity(self, ctx: commands.Context, member: discord.Member = None):
        "Queue the current Spotify activity from you or another member."
        member = member or ctx.author
        await self._queue_spotify_activity(ctx, member)

    @spotifyactivity.command(name="toggle", aliases=get_aliases("spotifyactivitytoggle"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def spotifyactivity_toggle(self, ctx: commands.Context):
        "Toggle auto-play from Spotify activities when the player is idle."
        guild_settings = await get_settings(ctx.guild.id)
        enabled = not guild_settings.get("spotify_activity_enabled", False)
        await update_settings(ctx.guild.id, {"$set": {"spotify_activity_enabled": enabled}})
        await send(
            ctx,
            f"Spotify Activity auto-play has been {'enabled' if enabled else 'disabled'}."
        )

    @spotifyactivity.command(name="status", aliases=get_aliases("spotifyactivitystatus"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def spotifyactivity_status(self, ctx: commands.Context):
        "Show the current Spotify Activity auto-play status."
        guild_settings = await get_settings(ctx.guild.id)
        enabled = guild_settings.get("spotify_activity_enabled", False)
        await send(ctx, f"Spotify Activity auto-play is currently **{'enabled' if enabled else 'disabled'}**.")

    @commands.Cog.listener()
    async def on_voicelink_track_start(self, player: voicelink.Player, track, _):
        settings_data = await get_settings(player.guild.id)
        channel_id = settings_data.get("song_announcement_channel_id")
        if not channel_id:
            return

        channel = player.guild.get_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title="Now Playing",
            description=f"[{track.title}]({track.uri})",
            color=settings.embed_color,
        )
        embed.add_field(name="Artist", value=track.author, inline=True)
        embed.add_field(name="Length", value="Live" if track.is_stream else track.formatted_length, inline=True)
        embed.set_footer(text=f"Requested by {track.requester.display_name}")
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        session = self.quiz_sessions.get(message.guild.id)
        if not session or message.channel.id != session.channel_id:
            return

        if normalize_text(message.content) in session.answers:
            session.revealed = True
            self.quiz_sessions.pop(message.guild.id, None)
            await message.channel.send(
                f"{message.author.mention} guessed it. The answer was **{session.track_title}** by **{session.track_author}**."
            )

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.bot or not after.guild:
            return

        guild_settings = await get_settings(after.guild.id)
        if not guild_settings.get("spotify_activity_enabled", False):
            return

        player: voicelink.Player = after.guild.voice_client
        if not player or not player.channel or player.is_playing or not player.queue.is_empty:
            return

        if not after.voice or after.voice.channel.id != player.channel.id:
            return

        activity = await self._get_spotify_activity(after)
        if not activity:
            return

        cache_key = (after.guild.id, after.id)
        current_key = f"{activity.title}|{'|'.join(activity.artists)}"
        cached = self.spotify_activity_cache.get(cache_key)
        if cached and cached[0] == current_key and (time.time() - cached[1]) < 180:
            return

        self.spotify_activity_cache[cache_key] = (current_key, time.time())
        text_channel = player.context.channel if getattr(player.context, "channel", None) else None
        if not text_channel:
            return
        ctx = TempCtx(after, text_channel)

        try:
            await self._play_query(
                ctx,
                f"{activity.title} {', '.join(activity.artists)}",
                announce=f"Spotify Activity auto-play queued **{activity.title}** by **{', '.join(activity.artists)}**.",
            )
        except Exception:
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Advanced(bot))
