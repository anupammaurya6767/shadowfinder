from typing import Any, List, Dict, Optional
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
from ..helpers.utils import check_user_in_channel
from ..templates.messages import Messages
from ..config.config import Config
from ..database import FileCache
from loguru import logger
import hashlib
import base64

def create_short_file_id(file_id: str) -> str:
    """Create a short identifier for a file ID"""
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
        channel = await client.get_chat(Config.FORCE_SUB_CHANNEL)
        invite_link = None
        
        if channel.username:
            invite_link = f"https://t.me/{channel.username}"
        else:
            try:
                chat_member = await client.get_chat_member(
                    Config.FORCE_SUB_CHANNEL,
                    (await client.get_me()).id
                )
                if chat_member.privileges and chat_member.privileges.can_invite_users:
                    invite_link = await client.create_chat_invite_link(Config.FORCE_SUB_CHANNEL)
                    invite_link = invite_link.invite_link
            except Exception as e:
                logger.error(f"Error creating invite link: {e}")

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

class FileSearchManager:
    def __init__(self, client: Client, db=None):
        self.client = client
        self.db = db

    async def search_all_channels(self, query: str) -> List[Dict]:
        """Search for files across all configured channels"""
        all_results = []
        search_channels = []

        # Get search channels from config
        if hasattr(Config, 'SEARCH_CHANNELS'):
            if isinstance(Config.SEARCH_CHANNELS, (list, tuple)):
                search_channels.extend([int(ch) for ch in Config.SEARCH_CHANNELS])
            elif Config.SEARCH_CHANNELS:
                try:
                    search_channels.append(int(Config.SEARCH_CHANNELS))
                except (ValueError, TypeError):
                    logger.error(f"Invalid SEARCH_CHANNELS config: {Config.SEARCH_CHANNELS}")

        # Add force sub channel if configured
        if hasattr(Config, 'FORCE_SUB_CHANNEL') and Config.FORCE_SUB_CHANNEL:
            try:
                force_sub_channel = int(Config.FORCE_SUB_CHANNEL)
                if force_sub_channel not in search_channels:
                    search_channels.append(force_sub_channel)
            except (ValueError, TypeError):
                logger.error(f"Invalid FORCE_SUB_CHANNEL config: {Config.FORCE_SUB_CHANNEL}")

        if not search_channels:
            logger.error("No search channels configured")
            return []

        # Search each channel
        for channel_id in search_channels:
            try:
                channel_results = await self._search_channel(channel_id, query)
                all_results.extend(channel_results)
            except Exception as e:
                logger.error(f"Error searching channel {channel_id}: {e}")
                continue

        return all_results[:Config.MAX_RESULTS]

    async def _search_channel(self, channel_id: int, query: str) -> List[Dict]:
        """Search for files in a specific channel"""
        results = []
        try:
            async for message in self.client.search_messages(
                chat_id=channel_id,
                query=query,
                filter="media",
                limit=20
            ):
                if message.media:
                    file_info = await self._extract_file_info(message)
                    if file_info:
                        results.append(file_info)
        except Exception as e:
            logger.error(f"Error searching channel {channel_id}: {e}")
        return results

    async def _extract_file_info(self, message: Any) -> Optional[Dict]:
        """Extract file information from a message"""
        try:
            media = None
            file_type = None
            file_name = None
            file_size = 0

            if message.document:
                media = message.document
                file_type = "document"
            elif message.video:
                media = message.video
                file_type = "video"
            elif message.audio:
                media = message.audio
                file_type = "audio"
            elif message.photo:
                media = message.photo
                file_type = "photo"
            elif message.animation:
                media = message.animation
                file_type = "animation"

            if media:
                file_id = getattr(media, 'file_id', None)
                file_name = getattr(media, 'file_name', f'media_{file_type}_{message.id}')
                file_size = getattr(media, 'file_size', 0)

                if file_id:
                    return {
                        "file_id": file_id,
                        "file_name": file_name,
                        "file_size": file_size,
                        "type": file_type,
                        "message_id": message.id,
                        "chat_id": message.chat.id
                    }

            return None
        except Exception as e:
            logger.error(f"Error extracting file info: {e}")
            return None

@Client.on_inline_query()
async def handle_inline_query(client: Client, query: InlineQuery):
    """Handle inline queries"""
    try:
        logger.debug(f"Received inline query: '{query.query}' from user {query.from_user.id}")

        # Check database initialization
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

        # Check chat authorization
        chat_id = getattr(query, 'chat', None)
        if chat_id:
            chat_id_str = str(chat_id)
            if chat_id_str.startswith('-100'):
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
        search_manager = FileSearchManager(client, db=client.db)
        files = await search_manager.search_all_channels(search_text)
        
        results = []
        file_cache = FileCache(client.db)

        for file in files:
            try:
                cached_file = await file_cache.get_cached_file(file['file_id'])
                access_count = cached_file.get('access_count', 0) if cached_file else 0
                
                short_id = create_short_file_id(file['file_id'])
                await file_cache.cache_short_id_mapping(short_id, file['file_id'])
                
                size = f"{file['file_size'] / 1024 / 1024:.2f} MB"
                popularity = "🔥" if access_count > 10 else ""
                
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
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(
                                    "📥 Extract Artifact 📥",
                                    callback_data=f"dl_{short_id}"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🤖 Start Bot",
                                    url="https://t.me/Searchkrlobot"
                                )
                            ]
                        ])
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
