# bot/handlers/inline.py
from typing import Any
from pyrogram import Client
from pyrogram.types import (
    InlineQuery, 
    InlineQueryResultArticle, 
    InputTextMessageContent,
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from pyrogram.enums import ParseMode
from bot.database.models import User
from ..helpers.utils import search_files, check_user_in_channel
from ..templates.messages import Messages
from ..config.config import Config
from ..database import FileCache
from loguru import logger
import hashlib
import base64

def create_short_file_id(file_id: str) -> str:
    """Create a short identifier for a file ID"""
    # Create MD5 hash of file_id and take first 8 characters
    return base64.urlsafe_b64encode(
        hashlib.md5(file_id.encode()).digest()[:6]
    ).decode().rstrip('=')

def create_min_length_result() -> InlineQueryResultArticle:
    """Create result for minimum length requirement"""
    return InlineQueryResultArticle(
        title="⚔️ Enter at least 3 characters",
        input_message_content=InputTextMessageContent(
            "🔍 *Speak the name of the artifact you seek...*",
            parse_mode=ParseMode.MARKDOWN
        ),
        description="Minimum 3 characters required for search",
        thumb_url=Config.MIN_LENGTH_THUMB_URL if hasattr(Config, 'MIN_LENGTH_THUMB_URL') else None,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔍 How to Search",
                callback_data="search_help"
            )
        ]])
    )

def create_unauthorized_result() -> InlineQueryResultArticle:
    """Create result for unauthorized users"""
    return InlineQueryResultArticle(
        title="⚠️ Unauthorized Guild",
        input_message_content=InputTextMessageContent(
            Messages.NOT_AUTHORIZED,
            parse_mode=ParseMode.MARKDOWN
        ),
        description="This power can only be used in authorized guilds",
        thumb_url=Config.UNAUTHORIZED_THUMB_URL if hasattr(Config, 'UNAUTHORIZED_THUMB_URL') else None
    )

async def create_force_sub_result(client: Client) -> InlineQueryResultArticle:
    """Create result for force subscribe requirement"""
    if not Config.FORCE_SUB_CHANNEL:
        return create_unauthorized_result()

    try:
        # Get channel info
        channel = await client.get_chat(Config.FORCE_SUB_CHANNEL)
        invite_link = None
        
        # Try to get or create invite link
        if channel.username:
            invite_link = f"https://t.me/{channel.username}"
        else:
            try:
                chat_member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, (await client.get_me()).id)
                if chat_member.privileges and chat_member.privileges.can_invite_users:
                    invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
                    invite_link = invite_link.invite_link
            except Exception as e:
                logger.error(f"Error creating invite link: {e}")

        # If we couldn't get an invite link, use a basic channel link
        if not invite_link:
            if str(Config.FORCE_SUB_CHANNEL).startswith('-100'):
                clean_id = str(Config.FORCE_SUB_CHANNEL)[4:]
                invite_link = f"https://t.me/c/{clean_id}/1"
            else:
                invite_link = f"https://t.me/+{abs(Config.FORCE_SUB_CHANNEL)}"

        return InlineQueryResultArticle(
            title="⚠️ Join Required",
            input_message_content=InputTextMessageContent(
                Messages.FORCE_SUB,
                parse_mode=ParseMode.MARKDOWN
            ),
            description=f"Join {channel.title} to use the bot",
            thumb_url=Config.FORCE_SUB_THUMB_URL if hasattr(Config, 'FORCE_SUB_THUMB_URL') else None,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔱 Join Channel 🔱",
                    url=invite_link
                )
            ]])
        )
    except Exception as e:
        logger.error(f"Error creating force sub result: {e}")
        return create_unauthorized_result()

@Client.on_inline_query()
async def handle_inline_query(client: Client, query: InlineQuery):
    """Handle inline queries"""
    try:
        logger.debug(f"Received inline query: '{query.query}' from user {query.from_user.id}")

        # Check if database is initialized
        if not hasattr(client, 'db') or client.db is None:
            logger.error("Database not initialized")
            return await query.answer(
                [
                    InlineQueryResultArticle(
                        title="❌ Service Unavailable",
                        input_message_content=InputTextMessageContent(
                            "Bot is initializing, please try again in a few moments.",
                            parse_mode=ParseMode.MARKDOWN
                        ),
                        description="Database connection not ready"
                    )
                ],
                cache_time=0
            )

        # Get chat type using custom peer type logic
        chat_id = getattr(query, 'chat', None)
        if chat_id:
            chat_id_str = str(chat_id)
            if chat_id_str.startswith('-100'):  # Channel or Supergroup
                if chat_id not in Config.AUTHORIZED_GROUPS:
                    logger.debug(f"Chat {chat_id} not in authorized groups")
                    return await query.answer(
                        [create_unauthorized_result()],
                        cache_time=0
                    )
            else:
                logger.debug("Not in a supergroup")
                return await query.answer(
                    [create_unauthorized_result()],
                    cache_time=0
                )

        # Check force subscribe
        if not await check_user_in_channel(client, query.from_user.id):
            logger.debug(f"User {query.from_user.id} not subscribed to force sub channel")
            return await query.answer(
                [await create_force_sub_result(client)],
                cache_time=0
            )

        # Check query length
        search_text = query.query.strip()
        if len(search_text) < Config.MIN_SEARCH_LENGTH:
            logger.debug(f"Query too short: {len(search_text)}")
            return await query.answer(
                [create_min_length_result()],
                cache_time=0
            )

        # Search files
        logger.debug(f"Searching for: {search_text}")
        files = await search_files(client, search_text, db=client.db)
        results = []

        file_cache = FileCache(client.db)
        
        for file in files:
            try:
                # Get cached info if available
                cached_file = await file_cache.get_cached_file(file['file_id'])
                access_count = cached_file.get('access_count', 0) if cached_file else 0
                
                # Create short identifier for callback data
                short_id = create_short_file_id(file['file_id'])
                
                # Cache the mapping of short_id to file_id
                await file_cache.cache_short_id_mapping(short_id, file['file_id'])
                
                size = f"{file['file_size'] / 1024 / 1024:.2f} MB"
                popularity = "🔥" if access_count > 10 else ""
                
                # Create file type indicator
                file_type = file.get('type', 'document')
                type_emoji = {
                    'document': '📄',
                    'video': '🎥',
                    'audio': '🎵',
                    'photo': '🖼️',
                    'voice': '🎤',
                    'animation': '🎞️'
                }.get(file_type, '📄')
                
                results.append(
                    InlineQueryResultArticle(
                        title=f"{popularity}{type_emoji} {file['file_name']}",
                        input_message_content=InputTextMessageContent(
                            f"🗡️ **File Name**: {file['file_name']}\n"
                            f"💠 **Size**: {size}\n"
                            f"📥 **Downloads**: {access_count}\n"
                            f"📁 **Type**: {file_type.title()}\n\n"
                            f"⚡️ *Summoning your file from the shadow realm...*",
                            parse_mode=ParseMode.MARKDOWN
                        ),
                        description=f"Size: {size} | Downloads: {access_count}",
                        thumb_url=Config.FILE_THUMB_URL if hasattr(Config, 'FILE_THUMB_URL') else None,
                        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📥 Extract Artifact 📥",
                callback_data=f"dl_{short_id}"
            )
        ], [
            InlineKeyboardButton(
                "🤖 Start Bot",
                url="https://t.me/Searchkrlobot"
            )
        ]])
    )
                )
            except Exception as e:
                logger.error(f"Error processing file result: {e}")
                continue

        if not results:
            logger.debug("No results found")
            results.append(
                InlineQueryResultArticle(
                    title="❌ No artifacts found",
                    input_message_content=InputTextMessageContent(
                        "🔍 *No artifacts match your search query...*",
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    description="Try a different search term",
                    thumb_url=Config.NO_RESULTS_THUMB_URL if hasattr(Config, 'NO_RESULTS_THUMB_URL') else None
                )
            )

        # Update user's search count
        try:
            user_db = User(client.db)
            await user_db.update_user_stats(query.from_user.id, search=True)
        except Exception as e:
            logger.error(f"Error updating user stats: {e}")

        logger.debug(f"Returning {len(results)} results")
        await query.answer(
            results[:Config.MAX_RESULTS],
            cache_time=300,
            is_personal=True
        )

    except Exception as e:
        logger.error(f"Error in inline query: {e}")
        await query.answer(
            [
                InlineQueryResultArticle(
                    title="❌ Error occurred",
                    input_message_content=InputTextMessageContent(
                        "An error occurred while searching.",
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    description="Please try again later"
                )
            ],
            cache_time=0
        )