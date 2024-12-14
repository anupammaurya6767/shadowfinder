from functools import wraps
from loguru import logger
from pyrogram.types import Message, InlineQuery, CallbackQuery
from pyrogram.errors import UserNotParticipant, UserNotParticipant, ChatAdminRequired, ChannelPrivate
from ..templates.messages import Messages
from ..config.config import Config
from .utils import check_user_in_channel
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def force_subscribe(func):
    @wraps(func)
    async def decorator(client, update):
        try:
            if isinstance(update, Message):
                user_id = update.from_user.id if update.from_user else None
                message = update
            elif isinstance(update, CallbackQuery):
                user_id = update.from_user.id if update.from_user else None
                message = update.message
            elif isinstance(update, InlineQuery):
                return await func(client, update)
            else:
                return await func(client, update)

            # Check if force subscribe is enabled and channel is set
            if not Config.FORCE_SUB_CHANNEL:
                return await func(client, update)

            if not user_id:
                logger.warning("No user_id found in update")
                return await func(client, update)

            try:
                await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
                return await func(client, update)
            except UserNotParticipant:
                buttons = [[
                    InlineKeyboardButton(
                        "🔱 Join Channel 🔱",
                        url=f"https://t.me/{(await client.get_chat(Config.FORCE_SUB_CHANNEL)).username}"
                    )
                ]]
                try:
                    await message.reply_text(
                        Messages.FORCE_SUB,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                except Exception as e:
                    logger.error(f"Error sending force sub message: {e}")
                return
            except (ChatAdminRequired, ChannelPrivate) as e:
                logger.error(f"Force subscribe check failed: {e}")
                return await func(client, update)
            except Exception as e:
                logger.error(f"Force subscribe error: {e}")
                return await func(client, update)

        except Exception as e:
            logger.error(f"Decorator error: {e}")
            return await func(client, update)

    return decorator