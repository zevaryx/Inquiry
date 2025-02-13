import asyncio
import csv
import logging
import json
from io import BytesIO, StringIO
from typing import TYPE_CHECKING

import yaml
import matplotlib.pyplot as plt
import numpy as np
from naff import (
    InteractionContext,
    SlashCommand,
    File,
    Timestamp,
    Permissions,
    AutocompleteContext,
)
from thefuzz import process

from extensions.shared import ExtensionBase, OPT_find_poll
from models.poll import PollData

if TYPE_CHECKING:
    from main import Bot

try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper

__all__ = ("setup", "PollUtils")

log = logging.getLogger("Inquiry")


class PollUtils(ExtensionBase):
    bot: "Bot"

    def __init__(self, bot) -> None:
        self.export_csv.autocomplete("poll")(self.poll_autocomplete)
        self.export_json.autocomplete("poll")(self.poll_autocomplete)
        self.export_yaml.autocomplete("poll")(self.poll_autocomplete)
        self.export_pie.autocomplete("poll")(self.poll_autocomplete)
        self.export_bar.autocomplete("poll")(self.poll_autocomplete)

    def get_user(self, user_id) -> str:
        try:
            user = self.bot.get_user(user_id)
            return user.username
        except Exception as e:
            pass
        return user_id

    async def poll_autocomplete(self, ctx: AutocompleteContext, poll) -> None:
        def predicate(_poll: PollData):
            if _poll.author_id == ctx.author.id:
                return True
            if ctx.author.has_permission(Permissions.MANAGE_MESSAGES):
                return True
            return False

        polls = await self.bot.poll_cache.get_polls_by_guild(ctx.guild_id)
        if polls:
            if not ctx.input_text:
                results = polls[:25]
            else:
                results = process.extract(
                    ctx.input_text, {p.message_id: p.title for p in polls if predicate(p)}, limit=25
                )
                results = [await self.bot.poll_cache.get_poll_by_message(p[2]) for p in results if p[1] > 50]

            await ctx.send(
                [
                    {
                        "name": f"{p.title} ({Timestamp.from_snowflake(p.message_id).ctime()})",
                        "value": str(p.message_id),
                    }
                    for p in results
                ]
            )

        else:
            await ctx.send([])

    export = SlashCommand(name="export", description="Export a poll into various formats")
    text = export.group(name="text", description="Export a poll into a text format")

    @text.subcommand(
        sub_cmd_name="csv",
        sub_cmd_description="Export a poll as a csv file",
        options=[OPT_find_poll],
    )
    async def export_csv(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                def rotate(input_list: list[list]) -> list[list]:
                    expected_len = max(map(len, input_list))
                    for sub_list in input_list:
                        if len(sub_list) < expected_len:
                            sub_list.extend([None] * (expected_len - len(sub_list)))

                    return list(zip(*input_list))  # type: ignore

                log.debug(f"Exporting {_poll.message_id} to csv")
                buffer = []
                for option in poll.poll_options:
                    buffer.append([option.text] + [self.get_user(v) for v in option.voters])

                buffer = rotate(buffer)
                f = StringIO()

                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerows(buffer)
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.csv"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @text.subcommand(
        sub_cmd_name="json",
        sub_cmd_description="Export a poll as a json file",
        options=[OPT_find_poll],
    )
    async def export_json(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to json")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = StringIO()

                json.dump(buffer, f)
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.json"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @text.subcommand(
        sub_cmd_name="yaml",
        sub_cmd_description="Export a poll as a yaml file",
        options=[OPT_find_poll],
    )
    async def export_yaml(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to yaml")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = StringIO()

                yaml.dump(buffer, f, Dumper=Dumper)
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.yaml"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    image = export.group(name="image", description="Export a poll to an image file")

    @image.subcommand(
        sub_cmd_name="pie",
        sub_cmd_description="Export a pie chart of the poll",
        options=[OPT_find_poll],
    )
    async def export_pie(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to pie chart")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = BytesIO()

                arr = np.array([len(x) for x in buffer.values()])
                labels = list(buffer.keys())
                fig = plt.figure()
                plt.pie(arr, labels=labels)
                plt.title(_poll.title)
                plt.savefig(f, format="png")
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.png"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @image.subcommand(
        sub_cmd_name="bar",
        sub_cmd_description="Export a bar graph of the poll",
        options=[OPT_find_poll],
    )
    async def export_bar(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to bar graph")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = BytesIO()

                arr = np.array([len(x) for x in buffer.values()])
                labels = list(buffer.keys())
                fig = plt.figure()
                plt.bar(labels, arr, width=0.4)
                plt.xlabel("Options")
                plt.ylabel("No. of Votes")
                plt.title(_poll.title)
                plt.savefig(f, format="png")
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.png"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")


def setup(bot: "Bot"):
    PollUtils(bot)
