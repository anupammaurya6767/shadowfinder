# bot/handlers/commands.py
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.helpers.utils import get_user_info
from ..config.config import Config
from ..templates.messages import Messages
from ..helpers.decorators import force_subscribe
from ..database.mongodb import Database
from loguru import logger

db = Database()



async def start_command(client: Client, message: Message):
    """Handle /start command"""
    try:
        await db.add_user(message.from_user.id)
        buttons = [
            [InlineKeyboardButton("⚔️ Search Files ⚔️", switch_inline_query_current_chat="")],
            [
                InlineKeyboardButton("🆘 Support Group", url=f"https://t.me/bots_arena_support"),
                InlineKeyboardButton("📡 Bot Channel", url=f"https://t.me/bots_arena")
            ]
        ]
        await message.reply_text(
            Messages.START,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def help_command(client: Client, message: Message):
    """Handle /help command"""
    try:
        buttons = [[
            InlineKeyboardButton("🔍 Try Searching 🔍", switch_inline_query_current_chat="")
        ],
        [
                InlineKeyboardButton("🆘 Support Group", url=f"https://t.me/bots_arena_support"),
                InlineKeyboardButton("📡 Bot Channel", url=f"https://t.me/bots_arena")
            ]]
        await message.reply_text(
            Messages.HELP.format(
                username=Config.USERNAME_OF_BOT
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")

async def about_command(client: Client, message: Message):
    """Handle /about command"""
    try:
        user_info = await get_user_info(client, Config.OWNER_ID)
        buttons = [[
            InlineKeyboardButton("👑 Owner 👑", url=f"https://t.me/{user_info["username"]}")
        ],
        [
                InlineKeyboardButton("🆘 Support Group", url=f"https://t.me/bots_arena_support"),
                InlineKeyboardButton("📡 Bot Channel", url=f"https://t.me/bots_arena")
            ]]
        total_users = await db.get_user_stats()
        await message.reply_text(
            Messages.ABOUT.format(
                owner_name=user_info["first_name"],
                version=Config.VERSION,
                total_users=total_users
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in about command: {e}")

async def command_in_group(client: Client, message: Message):
    """Handle commands in groups"""
    try:
        bot = await client.get_me()
        buttons = [[
            InlineKeyboardButton("🤖 Start in Private", url=f"https://t.me/{Config.USERNAME_OF_BOT}")
        ]]
        await message.reply_text(
            "⚔️ Please use commands in private chat with the bot.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in group command handler: {e}")


