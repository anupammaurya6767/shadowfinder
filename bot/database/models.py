# bot/database/models.py
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

# Type checking imports
if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

class User:
    collection: AsyncIOMotorCollection

    def __init__(self, db: "AsyncIOMotorDatabase"):
        self.collection = db.users

    async def create_user(self, user_id: int, username: Optional[str] = None) -> bool:
        """Create a new user in database"""
        user_data = {
            'user_id': user_id,
            'username': username,
            'joined_date': datetime.now(),
            'last_used': datetime.now(),
            'searches': 0,
            'downloads': 0,
            'banned': False
        }
        try:
            await self.collection.update_one(
                {'user_id': user_id},
                {'$setOnInsert': user_data},
                upsert=True
            )
            return True
        except Exception:
            return False

    async def update_user_stats(self, user_id: int, search: bool = False, download: bool = False) -> bool:
        """Update user statistics"""
        update_data: Dict[str, Any] = {
            'last_used': datetime.now()
        }
        if search:
            update_data['$inc'] = {'searches': 1}
        if download:
            update_data['$inc'] = {'downloads': 1}
        
        try:
            await self.collection.update_one(
                {'user_id': user_id},
                {'$set': update_data}
            )
            return True
        except Exception:
            return False

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user details"""
        return await self.collection.find_one({'user_id': user_id})

    async def ban_user(self, user_id: int, banned: bool = True) -> bool:
        """Ban or unban user"""
        try:
            await self.collection.update_one(
                {'user_id': user_id},
                {'$set': {'banned': banned}}
            )
            return True
        except Exception:
            return False

class FileCache:
    def __init__(self, db: "AsyncIOMotorDatabase"):
        self.collection = db.file_cache
        self.id_mappings = db.file_id_mappings  # New collection for ID mappings


    async def increment_access_count(self, file_id: str) -> bool:
        """Increment the access count for a file"""
        try:
            result = await self.collection.update_one(
                {'file_id': file_id},
                {
                    '$inc': {'access_count': 1},
                    '$set': {'last_accessed': datetime.now()}
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error incrementing access count: {e}")
            return False

    async def get_file_id_from_short_id(self, short_id: str) -> Optional[str]:
        """Get the original file ID from a short ID"""
        try:
            mapping = await self.id_mappings.find_one({'short_id': short_id})
            return mapping['file_id'] if mapping else None
        except Exception as e:
            logger.error(f"Error retrieving file ID from short ID: {e}")
            return None

    async def update_file_id(self, file_unique_id: str, new_file_id: str) -> bool:
        """Update file ID for a file"""
        try:
            result = await self.collection.update_many(
                {'file_unique_id': file_unique_id},
                {
                    '$set': {
                        'file_id': new_file_id,
                        'last_updated': datetime.now()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating file ID: {e}")
            return False
        
    async def cache_short_id_mapping(self, short_id: str, file_id: str) -> bool:
        """Cache the mapping of short ID to file ID"""
        try:
            await self.id_mappings.update_one(
                {'short_id': short_id},
                {
                    '$set': {
                        'file_id': file_id,
                        'created_at': datetime.now()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error caching short ID mapping: {e}")
            return False

    async def cache_file(self, file_data: Dict[str, Any]) -> bool:
        """Cache file information"""
        try:
            # Ensure required fields
            required_fields = ['file_id', 'file_unique_id', 'file_name', 'channel_id', 'message_id']
            if not all(field in file_data for field in required_fields):
                logger.error(f"Missing required fields in file_data: {file_data}")
                return False

            # Convert channel_id and message_id to int
            if 'channel_id' in file_data:
                file_data['channel_id'] = int(file_data['channel_id'])
            if 'message_id' in file_data:
                file_data['message_id'] = int(file_data['message_id'])

            await self.collection.update_one(
                {'file_id': file_data['file_id']},
                {
                    '$set': {
                        **file_data,
                        'last_updated': datetime.now()
                    },
                    '$setOnInsert': {
                        'access_count': 0,
                        'first_seen': datetime.now()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error caching file: {e}")
            return False

    async def get_cached_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file from cache"""
        try:
            file_data = await self.collection.find_one({'file_id': file_id})
            if file_data:
                await self.collection.update_one(
                    {'file_id': file_id},
                    {
                        '$set': {'last_accessed': datetime.now()},
                        '$inc': {'access_count': 1}
                    }
                )
            return file_data
        except Exception:
            return None

    async def search_cached_files(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search through cached files"""
        try:
            cursor = self.collection.find(
                {
                    'file_name': {'$regex': query, '$options': 'i'}
                }
            ).sort('access_count', -1).limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception:
            return []

    async def clean_old_cache(self, days: int = 30) -> int:
        """Clean cache older than specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = await self.collection.delete_many(
                {'last_accessed': {'$lt': cutoff_date}}
            )
            return result.deleted_count
        except Exception:
            return 0

    async def get_popular_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most accessed files"""
        try:
            cursor = self.collection.find().sort('access_count', -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception:
            return []
        