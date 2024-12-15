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
from pyrogram.errors import QueryIdInvalid, FloodWait
from bot.database.models import User
from ..helpers.utils import search_files, check_user_in_channel
from ..templates.messages import Messages
from ..config.config import Config
from ..database import FileCache
from loguru import logger
import hashlib
import base64
import asyncio

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
# Configuration for timeouts and retries
QUERY_TIMEOUT = 25.0  
MAX_RETRIES = 5      
INITIAL_RETRY_DELAY = 1.0  
DB_OPERATION_TIMEOUT = 15.0  

async def retry_with_flood_control(func, *args, **kwargs):
    """Helper function to handle flood control and retries"""
    total_wait_time = 0
    max_total_wait = 60  # Maximum total wait time in seconds
    
    while total_wait_time < max_total_wait:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            wait_time = e.value * FLOOD_WAIT_MULTIPLIER
            if total_wait_time + wait_time > max_total_wait:
                raise
            logger.warning(f"FloodWait detected, waiting for {wait_time} seconds")
            await asyncio.sleep(wait_time)
            total_wait_time += wait_time
        except Exception as e:
            raise

@Client.on_inline_query()
async def handle_inline_query(client: Client, query: InlineQuery):
    """Handle inline queries with support for userbot clients"""
    try:
        logger.debug(f"Received inline query: '{query.query}' from user {query.from_user.id}")
        
        is_userbot = not getattr(client, 'bot_token', None)
        logger.debug(f"Client type: {'Userbot' if is_userbot else 'Bot'}")
        
        error_result = InlineQueryResultArticle(
            title="❌ Error occurred",
            input_message_content=InputTextMessageContent(
                "An error occurred while searching.",
                parse_mode=ParseMode.MARKDOWN
            ),
            description="Please try again later"
        )

        async def process_query():
            # Database check
            if not hasattr(client, 'db') or client.db is None:
                logger.error("Database not initialized")
                return [InlineQueryResultArticle(
                    title="❌ Service Unavailable",
                    input_message_content=InputTextMessageContent(
                        "Bot is initializing, please try again in a few moments.",
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    description="Database connection not ready"
                )]

            # Skip auth checks for userbot
            if not is_userbot:
                # Regular bot authorization checks here
                chat_id = getattr(query, 'chat', None)
                if chat_id:
                    chat_id_str = str(chat_id)
                    if chat_id_str.startswith('-100') and chat_id not in Config.AUTHORIZED_GROUPS:
                        return [create_unauthorized_result()]
                    elif not chat_id_str.startswith('-100'):
                        return [create_unauthorized_result()]

                # Force subscribe check only for regular bot
                if not await check_user_in_channel(client, query.from_user.id):
                    return [await create_force_sub_result(client)]

            # Query length check
            search_text = query.query.strip()
            if len(search_text) < Config.MIN_SEARCH_LENGTH:
                return [create_min_length_result()]

            # Search files with flood control
            try:
                files = await retry_with_flood_control(
                    search_files,
                    client,
                    search_text,
                    db=client.db
                )
            except Exception as e:
                logger.error(f"File search failed: {e}")
                raise

            results = []
            file_cache = FileCache(client.db)

            # Process files
            for file in files:
                try:
                    cached_file = await file_cache.get_cached_file(file['file_id'])
                    access_count = cached_file.get('access_count', 0) if cached_file else 0
                    
                    # Use more compact short IDs for userbot
                    if is_userbot:
                        short_id = base64.urlsafe_b64encode(
                            hashlib.md5(file['file_id'].encode()).digest()[:4]
                        ).decode().rstrip('=')
                    else:
                        short_id = create_short_file_id(file['file_id'])
                    
                    await file_cache.cache_short_id_mapping(short_id, file['file_id'])
                    
                    size = f"{file['file_size'] / 1024 / 1024:.2f} MB"
                    popularity = "🔥" if access_count > 10 else ""
                    
                    file_type = file.get('type', 'document')
                    type_emoji = {
                        'document': '📄', 'video': '🎥', 'audio': '🎵',
                        'photo': '🖼️', 'voice': '🎤', 'animation': '🎞️'
                    }.get(file_type, '📄')
                    
                    # Simplified markup for userbot queries
                    if is_userbot:
                        markup = InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "📥 Download",
                                callback_data=f"dl_{short_id}"
                            )
                        ]])
                    else:
                        markup = InlineKeyboardMarkup([[
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

                    results.append(InlineQueryResultArticle(
                        title=f"{popularity}{type_emoji} {file['file_name']}",
                        input_message_content=InputTextMessageContent(
                            f"🗡️ **File Name**: {file['file_name']}\n"
                            f"💠 **Size**: {size}\n"
                            f"📥 **Downloads**: {access_count}\n"
                            f"📁 **Type**: {file_type.title()}"
                            + ("" if is_userbot else "\n\n⚡️ *Summoning your file from the shadow realm...*"),
                            parse_mode=ParseMode.MARKDOWN
                        ),
                        description=f"Size: {size} | Downloads: {access_count}",
                        thumb_url=Config.FILE_THUMB_URL if hasattr(Config, 'FILE_THUMB_URL') else None,
                        reply_markup=markup
                    ))
                except Exception as e:
                    logger.error(f"Error processing file result: {e}")
                    continue

            if not results:
                results.append(InlineQueryResultArticle(
                    title="❌ No artifacts found",
                    input_message_content=InputTextMessageContent(
                        "🔍 *No artifacts match your search query...*",
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    description="Try a different search term",
                    thumb_url=Config.NO_RESULTS_THUMB_URL if hasattr(Config, 'NO_RESULTS_THUMB_URL') else None
                ))

            # Update user stats only for regular bot
            if not is_userbot:
                try:
                    user_db = User(client.db)
                    await user_db.update_user_stats(query.from_user.id, search=True)
                except Exception as e:
                    logger.error(f"Error updating user stats: {e}")

            return results[:Config.MAX_RESULTS]

        # Execute with appropriate timeout
        timeout = USERBOT_QUERY_TIMEOUT if is_userbot else 25.0
        try:
            results = await asyncio.wait_for(process_query(), timeout=timeout)
            
            # Enhanced retry logic for userbot
            retry_delay = INITIAL_RETRY_DELAY
            
            for attempt in range(MAX_RETRIES):
                try:
                    if is_userbot:
                        # Use flood control for userbot queries
                        await retry_with_flood_control(
                            query.answer,
                            results,
                            cache_time=300 if not is_userbot else 0,  # No cache for userbot
                            is_personal=True
                        )
                    else:
                        await query.answer(
                            results,
                            cache_time=300,
                            is_personal=True
                        )
                    break
                except QueryIdInvalid:
                    if attempt == MAX_RETRIES - 1:
                        raise
                    logger.warning(f"Query answer attempt {attempt + 1} failed, retrying in {retry_delay:.1f}s")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5

        except asyncio.TimeoutError:
            logger.error("Query processing timed out")
            await query.answer([error_result], cache_time=0)
            
    except QueryIdInvalid:
        logger.error("Final QueryIdInvalid error - query expired")
    except FloodWait as e:
        logger.error(f"FloodWait error: {e}")
    except Exception as e:
        logger.error(f"Error in inline query: {e}")
        try:
            await query.answer([error_result], cache_time=0)
        except:
            pass
