from loguru import logger
from pyrogram import Client, enums
from ..config.config import Config
import asyncio
from datetime import datetime
from typing import Any, Union, List, Dict, Optional
from ..database import FileCache
from motor.motor_asyncio import AsyncIOMotorDatabase

async def get_user_info(app: Client, user_id: int) -> dict:
    """
    Get username and full name of a Telegram user by their user ID.
    
    Parameters:
        app (Client): Initialized Pyrogram client
        user_id (int): Telegram user ID
        
    Returns:
        dict: Dictionary containing username and full name
              Returns None values if user not found
    """
    try:
        user = await app.get_users(user_id)
        return {
            "username": user.username,  # Will be None if user has no username
            "full_name": f"{user.first_name} {user.last_name if user.last_name else ''}".strip(),
            "first_name": user.first_name,
            "last_name": user.last_name,  # Will be None if user has no last name
            "is_bot": user.is_bot,
            "is_premium": user.is_premium
        }
    except Exception as e:
        print(f"Error getting user info: {e}")
        return {
            "username": None,
            "full_name": None,
            "first_name": None,
            "last_name": None,
            "is_bot": None,
            "is_premium": None
        }

class SearchClient:
    def __init__(self, api_id: int, api_hash: str, session_string: str):
        """Initialize user bot client for searching"""
        self.client = Client(
            "search_user_bot",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string
        )
        self._lock = asyncio.Lock()
        
    async def start(self):
        """Start the user bot client"""
        await self.client.start()
        
    async def stop(self):
        """Stop the user bot client"""
        await self.client.stop()

    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

async def check_user_in_channel(client: Client, user_id: int) -> bool:
    """Check if user is in force subscribe channel"""
    if not Config.FORCE_SUB_CHANNEL:
        return True
    
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        return member.status not in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]
    except Exception:
        return False

async def delete_message_later(message, delay: int = Config.DELETE_TIMEOUT):
    """Delete message after specified delay"""
    try:
        # Wait for specified delay
        await asyncio.sleep(delay)
        
        # Log deletion attempt
        logger.debug(f"Attempting to delete message {message.id}")
        
        # Attempt to delete
        await message.delete()
        logger.info(f"Successfully deleted message {message.id}")
        
    except Exception as e:
        logger.error(f"Failed to delete message {message.id}: {str(e)}")

async def process_media_message(message, query_lower: str) -> Optional[Dict[str, Any]]:
    """Process a message to extract media information"""
    message_text = (message.caption or "").lower()
    
    media_types = [
        ('document', message.document),
        ('video', message.video),
        ('audio', message.audio),
        ('photo', message.photo),
        ('voice', message.voice),
        ('video_note', message.video_note),
        ('animation', message.animation)
    ]
    
    for media_type, media in media_types:
        if not media:
            continue
            
        if media_type == 'photo':
            if query_lower in message_text:
                photo = message.photo[-1]
                return {
                    'file_id': photo.file_id,
                    'file_name': f"photo_{message.id}",
                    'file_size': photo.file_size,
                    'mime_type': 'image/jpeg',
                    'type': 'photo',
                    'message_id': message.id,
                    'date': message.date,
                    'caption': message.caption
                }
        else:
            file_name = getattr(media, 'file_name', f"{media_type}_{message.id}")
            search_text = f"{file_name} {message_text}"
            
            if query_lower in search_text.lower():
                return {
                    'file_id': media.file_id,
                    'file_name': file_name,
                    'file_size': media.file_size,
                    'mime_type': getattr(media, 'mime_type', f"{media_type}/unknown"),
                    'type': media_type,
                    'message_id': message.id,
                    'date': message.date,
                    'caption': message.caption
                }
    
    return None

async def search_files(
    client: Client,
    query: str,
    db: Optional[AsyncIOMotorDatabase] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Search for files using cache and user bot for complete message history"""
    logger.debug(f"Starting search_files with query: '{query}', limit: {limit}")
    
    if db is None:
        logger.error("Database not provided")
        return []
    
    results = []    
    file_cache = FileCache(db)
    query_lower = query.lower()
    
    # First check cache
    try:
        cached_results = await file_cache.search_cached_files(query_lower, limit)
        logger.debug(f"Found {len(cached_results)} results in cache")
        results.extend(cached_results)
    except Exception as e:
        logger.error(f"Error searching cache: {e}")

    # If we need more results and have user bot, search channels
    if len(results) < limit and hasattr(client, 'user_bot') and client.user_bot is not None:
        try:
            for channel_id in Config.SEARCH_CHANNELS:
                try:
                    logger.debug(f"Searching in channel: {channel_id}")
                    
                    # Verify channel access first
                    try:
                        chat = await client.user_bot.get_chat(channel_id)
                        if not chat:
                            logger.error(f"Cannot access channel {channel_id}")
                            continue
                    except Exception as e:
                        logger.error(f"Error accessing channel {channel_id}: {e}")
                        continue

                    # Search messages
                    message_count = 0
                    try:
                        async for message in client.user_bot.search_messages(
                            chat_id=int(channel_id),
                            query=query_lower,
                            limit=limit
                        ):
                            message_count += 1
                            
                            # Process each media type
                            media_types = [
                                ('document', message.document),
                                ('video', message.video),
                                ('audio', message.audio),
                                ('photo', message.photo),
                                ('voice', message.voice),
                                ('animation', message.animation)
                            ]
                            
                            for media_type, media in media_types:
                                if media:
                                    file_data = None
                                    
                                    if media_type == 'photo':
                                        if query_lower in (message.caption or "").lower():
                                            photo = media[-1]  # Get largest photo size
                                            file_data = {
                                                'file_id': photo.file_id,
                                                'file_unique_id': photo.file_unique_id,
                                                'file_name': f"photo_{message.id}",
                                                'file_size': photo.file_size,
                                                'mime_type': 'image/jpeg',
                                                'type': 'photo'
                                            }
                                    else:
                                        file_name = getattr(media, 'file_name', f"{media_type}_{message.id}")
                                        search_text = f"{file_name} {message.caption or ''}"
                                        
                                        if query_lower in search_text.lower():
                                            file_data = {
                                                'file_id': media.file_id,
                                                'file_unique_id': media.file_unique_id,
                                                'file_name': file_name,
                                                'file_size': media.file_size,
                                                'mime_type': getattr(media, 'mime_type', f"{media_type}/unknown"),
                                                'type': media_type
                                            }
                                    
                                    if file_data:
                                        file_data.update({
                                            'channel_id': int(channel_id),
                                            'message_id': message.id,
                                            'date': message.date,
                                            'caption': message.caption
                                        })
                                        
                                        # Cache the file
                                        try:
                                            await file_cache.cache_file(file_data)
                                        except Exception as e:
                                            logger.error(f"Error caching file: {e}")
                                        
                                        results.append(file_data)
                                        break  # Found a match, move to next message
                        
                            if len(results) >= limit:
                                break
                                
                        logger.debug(f"Found {message_count} matches in {channel_id}")
                        
                    except Exception as e:
                        logger.error(f"Error searching messages in channel {channel_id}: {e}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error processing channel {channel_id}: {e}")
                    continue
                    
                if len(results) >= limit:
                    break
                    
        except Exception as e:
            logger.error(f"Error in user bot search: {e}")

    # Remove duplicates based on file_unique_id
    unique_results = {}
    for result in results:
        unique_id = result.get('file_unique_id')
        if unique_id and (unique_id not in unique_results or result['date'] > unique_results[unique_id]['date']):
            unique_results[unique_id] = result

    # Sort by date
    final_results = sorted(
        unique_results.values(), 
        key=lambda x: x.get('date', datetime.min), 
        reverse=True
    )
    
    logger.debug(f"Returning {len(final_results[:limit])} unique results")
    return final_results[:limit]