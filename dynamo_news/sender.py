from discord import Embed, File, TextChannel


async def edit_or_send(
    drb, channel_id: int, embed: Embed, file: File, send_for: str = "ppi"
) -> TextChannel:
    channel = drb.get_channel(channel_id)
    async for message in channel.history(limit=100):
        text = message.content
        embeds = message.embeds
        if text:
            if "is LIVE in" in text or "will be released in" in text:
                await message.delete()
        elif embeds:
            if (
                (
                    "consumer price index calendar" in embeds[0].title.lower()
                    and send_for == "cpi"
                )
                or (
                    "non farm payrolls" in embeds[0].title.lower() and send_for == "nfp"
                )
                or (
                    "producer price index" in embeds[0].title.lower()
                    and send_for == "ppi"
                )
                or (
                    "u.k federal funds rate" in embeds[0].title.lower()
                    and send_for == "feduk"
                )
                or (
                    "u.s federal funds rate" in embeds[0].title.lower()
                    and send_for == "fedus"
                )
            ):
                await message.delete()
            else:
                print(embeds[0].title)

    await channel.send(embed=embed, file=file)

    return channel
