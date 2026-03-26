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
import discord
import function as func
import re

from typing import Optional

LRC_PATTERN = re.compile(r"^\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\](.*)$")

def chunk_lyrics(text: str, lines_per_page: int = 22) -> list[str]:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ["Lyrics unavailable."]

    chunks = []
    for index in range(0, len(lines), lines_per_page):
        chunks.append("\n".join(lines[index:index + lines_per_page]))
    return chunks

def parse_synced_lyrics(text: str) -> list[dict[str, int | str]]:
    lines = []
    for raw_line in (text or "").splitlines():
        match = LRC_PATTERN.match(raw_line.strip())
        if not match:
            continue

        minutes, seconds, millis, lyric_text = match.groups()
        lyric_text = lyric_text.strip()
        if not lyric_text:
            continue

        millis = (millis or "0").ljust(3, "0")[:3]
        time_ms = (int(minutes) * 60 + int(seconds)) * 1000 + int(millis)
        lines.append({"time_ms": time_ms, "text": lyric_text})

    return lines

class LyricsDropdown(discord.ui.Select):
    def __init__(self, langs: list[str]) -> None:
        self.view: LyricsView

        super().__init__(
            placeholder="Select A Lyrics Translation",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=lang) for lang in langs], 
            custom_id="selectLyricsLangs"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.lang = self.values[0]
        self.view.current_page = 1
        self.view.follow_player = True
        if self.view.lang == "synced" and self.view.synced_source:
            self.view.synced_index = self.view._get_live_synced_index()
            self.view.pages = len(self.view.synced_source)
        else:
            self.view.pages = len(self.view.source.get(self.values[0], ["Lyrics unavailable."]))
        await interaction.response.edit_message(embed=self.view.build_embed())

class LyricsView(discord.ui.View):
    def __init__(self, name: str, source: dict, author: discord.Member, player = None) -> None:
        super().__init__(timeout=180)

        self.name: str = name
        self.author: discord.Member = author
        self.player = player

        self.source: dict[str, list[str]] = {
            key: chunk_lyrics(value)
            for key, value in source.items()
            if key != "synced" and value
        }
        self.synced_source = parse_synced_lyrics(source.get("synced", ""))

        options = list(self.source.keys())
        if self.synced_source:
            options.insert(0, "synced")

        self.lang: str = options[0] if options else "default"
        self.author: discord.Member = author

        self.response: discord.Message = None
        self.pages: int = len(self.source.get(self.lang, ["Lyrics unavailable."])) if self.lang != "synced" else max(len(self.synced_source), 1)
        self.current_page: int = 1
        self.follow_player: bool = True
        self.synced_index: int = 0
        self._sync_task = None
        self.add_item(LyricsDropdown(options))

    def start_auto_sync(self) -> None:
        if self.lang != "synced" or not self.synced_source or not self.player:
            return

        if self._sync_task and not self._sync_task.done():
            return

        async def runner():
            try:
                while not self.is_finished():
                    await asyncio.sleep(3)
                    if not self.response or not self.follow_player:
                        continue
                    try:
                        await self.response.edit(embed=self.build_embed(), view=self)
                    except:
                        break
            except:
                return

        self._sync_task = asyncio.create_task(runner())

    def _get_live_synced_index(self) -> int:
        if not self.synced_source:
            return 0

        if not self.player or not getattr(self.player, "current", None):
            return self.synced_index

        position = int(getattr(self.player, "position", 0))
        index = 0

        for offset, entry in enumerate(self.synced_source):
            if entry["time_ms"] > position:
                break
            index = offset

        return index

    def _build_synced_embed(self) -> discord.Embed:
        if self.follow_player:
            self.synced_index = self._get_live_synced_index()

        current_index = min(max(self.synced_index, 0), len(self.synced_source) - 1)
        start = max(current_index - 3, 0)
        end = min(current_index + 4, len(self.synced_source))

        rendered_lines = []
        for index in range(start, end):
            line = self.synced_source[index]["text"]
            if index == current_index:
                rendered_lines.append(f"> **{line}**")
            else:
                rendered_lines.append(line)

        timestamp = func.time(self.synced_source[current_index]["time_ms"]) if self.synced_source else "00:00"
        embed = discord.Embed(
            description="\n".join(rendered_lines) or "Synced lyrics unavailable.",
            color=func.settings.embed_color
        )
        embed.set_author(name=f"Karaoke Lyrics: {self.name}", icon_url=self.author.display_avatar.url)
        embed.set_footer(
            text=f"Line {current_index + 1}/{len(self.synced_source)} | At {timestamp} | {'Live' if self.follow_player else 'Manual'}"
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
        try:
            await self.response.edit(view=self)
        except:
            pass
    
    async def on_error(self, error, item, interaction) -> None:
        return

    def build_embed(self) -> discord.Embed:
        if self.lang == "synced" and self.synced_source:
            return self._build_synced_embed()

        chunk = self.source.get(self.lang)[self.current_page - 1]
        embed=discord.Embed(description=chunk, color=func.settings.embed_color)
        embed.set_author(name=f"Searching Query: {self.name}", icon_url=self.author.display_avatar.url)
        embed.set_footer(text=f"Page: {self.current_page}/{self.pages}")
        return embed

    @discord.ui.button(label='<<', style=discord.ButtonStyle.grey)
    async def fast_back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.lang == "synced" and self.synced_source:
            self.follow_player = False
            self.synced_index = 0
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)

        if self.current_page != 1:
            self.current_page = 1
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.response.defer()

    @discord.ui.button(label='Back', style=discord.ButtonStyle.blurple)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.lang == "synced" and self.synced_source:
            self.follow_player = False
            if self.synced_index > 0:
                self.synced_index -= 1
                return await interaction.response.edit_message(embed=self.build_embed(), view=self)
            return await interaction.response.defer()

        if self.current_page > 1:
            self.current_page -= 1
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.response.defer()

    @discord.ui.button(label='Next', style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.lang == "synced" and self.synced_source:
            self.follow_player = False
            if self.synced_index < len(self.synced_source) - 1:
                self.synced_index += 1
                return await interaction.response.edit_message(embed=self.build_embed(), view=self)
            return await interaction.response.defer()

        if self.current_page < self.pages:
            self.current_page += 1
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.response.defer()

    @discord.ui.button(label='>>', style=discord.ButtonStyle.grey)
    async def fast_next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.lang == "synced" and self.synced_source:
            self.follow_player = False
            self.synced_index = len(self.synced_source) - 1
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)

        if self.current_page != self.pages:
            self.current_page = self.pages
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.response.defer()

    @discord.ui.button(label='Live', style=discord.ButtonStyle.green)
    async def live_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.lang != "synced" or not self.synced_source:
            return await interaction.response.defer()

        self.follow_player = True
        self.synced_index = self._get_live_synced_index()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(emoji='🗑️', style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.response.delete()
        self.stop()
