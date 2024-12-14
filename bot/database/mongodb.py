from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from ..config.config import Config
from datetime import datetime

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.DB_URL)
        self._db: AsyncIOMotorDatabase = self.client.shadowfinder

    @property
    def db(self) -> AsyncIOMotorDatabase:
        return self._db

    def get_collection(self, name: str):
        """Get collection by name"""
        return self._db[name]

    async def close(self):
        """Close database connection"""
        self.client.close()

    async def add_user(self, user_id: int):
        """Add user to database"""
        await self.db.users.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'user_id': user_id,
                    'last_used': datetime.now()
                },
                '$setOnInsert': {
                    'joined_date': datetime.now()
                }
            },
            upsert=True
        )

    async def get_user_stats(self):
        """Get total users count"""
        total_users = await self.db.users.count_documents({})
        return total_users

    async def is_user_exist(self, user_id: int):
        """Check if user exists in database"""
        user = await self.db.users.find_one({'user_id': user_id})
        return bool(user)

    async def update_last_used(self, user_id: int):
        """Update user's last usage time"""
        await self.db.users.update_one(
            {'user_id': user_id},
            {'$set': {'last_used': datetime.now()}}
        )
