import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from pyrogram import Client, idle
from pyrogram.types import User as PyrogramUser
from motor.motor_asyncio import AsyncIOMotorClient
from .config.config import Config
from .database.models import User, FileCache
from loguru import logger
import platform
import sys
import os
import pymongo
from pymongo.errors import ConnectionFailure
import pyrogram

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase
    from asyncio import Task

# Configure logger
logger.remove()  # Remove default handler
logger.add(
    "logs/shadowfinder.log",
    rotation="1 day",
    retention="7 days",
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
logger.add(sys.stderr, level="INFO")

class DatabaseError(Exception):
    """Custom exception for database errors"""
    pass

class ShadowFinder(Client):
    db: Optional["AsyncIOMotorDatabase"]
    user_db: Optional[User]
    file_cache: Optional[FileCache]
    tasks: List["Task"]
    uptime_start: datetime
    user_bot: Optional[Client]
    user_states: Dict[int, Dict[str, Any]]

    def __init__(self):
        # Validate critical configurations
        if not Config.validate():
            logger.error("Critical configurations missing!")
            sys.exit(1)

        name = self.__class__.__name__.lower()
        super().__init__(
            name=name,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/handlers"),
            workers=Config.WORKERS,
            max_concurrent_transmissions=Config.MAX_CONCURRENT_TRANSMISSIONS
        )
        
        # Initialize attributes
        self.db = None
        self.user_db = None
        self.file_cache = None
        self.uptime_start = datetime.now()
        self.tasks = []
        self.user_bot = None
        self.user_states = {}
        
        
        # Add custom peer type handler
        def get_peer_type_new(peer_id: int) -> str:
            peer_id_str = str(peer_id)
            if not peer_id_str.startswith("-"):
                return "user"
            elif peer_id_str.startswith("-100"):
                return "channel"
            else:
                return "chat"
            
        pyrogram.utils.MIN_CHANNEL_ID = -1002281400624
        pyrogram.utils.get_peer_type = get_peer_type_new
        self.register_handlers()

    async def initialize_user_bot(self) -> None:
        """Initialize user bot client for searching"""
        if not Config.USER_SESSION_STRING:
            logger.warning("User bot session string not configured")
            return

        try:
            self.user_bot = Client(
                name="search_user_bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=Config.USER_SESSION_STRING,
                in_memory=True
            )

            # Start user bot
            await self.user_bot.start()
            user = await self.user_bot.get_me()
            logger.info(f"User bot started successfully as {user.first_name} (@{user.username})")

            # Wait a moment for client to fully initialize
            await asyncio.sleep(2)

            # Join search channels
            await self.join_search_channels()

        except Exception as e:
            logger.error(f"Failed to initialize user bot: {e}")
            if self.user_bot:
                await self.user_bot.stop()
            self.user_bot = None

    async def join_search_channels(self) -> None:
        """Join all search channels with user bot"""
        if not self.user_bot:
            return

        for channel_id in Config.SEARCH_CHANNELS:
            try:
                # First try to get channel directly
                try:
                    chat = await self.user_bot.get_chat(channel_id)
                    logger.info(f"User bot already in channel: {chat.title} ({channel_id})")
                    continue
                except Exception as e:
                    logger.debug(f"Channel {channel_id} not joined yet: {e}")

                # Try to get channel info using bot account first
                try:
                    chat = await self.get_chat(channel_id)
                    if chat.username:
                        # For public channels/groups
                        join_link = f"https://t.me/{chat.username}"
                    else:
                        # For private channels, try to get invite link
                        try:
                            bot_member = await self.get_chat_member(channel_id, (await self.get_me()).id)
                            if bot_member.privileges and bot_member.privileges.can_invite_users:
                                invite = await self.create_chat_invite_link(channel_id)
                                join_link = invite.invite_link
                            else:
                                join_link = await self.export_chat_invite_link(channel_id)
                        except Exception:
                            # Fallback to basic channel link
                            clean_id = str(channel_id)[4:] if str(channel_id).startswith('-100') else str(abs(channel_id))
                            join_link = f"https://t.me/c/{clean_id}/1"

                    # Try to join using the obtained link
                    await self.user_bot.join_chat(join_link)
                    logger.info(f"Successfully joined channel {channel_id}")

                    # Verify membership
                    await asyncio.sleep(1)  # Wait briefly before verification
                    chat = await self.user_bot.get_chat(channel_id)
                    logger.info(f"Verified membership in channel: {chat.title}")

                except Exception as e:
                    logger.error(f"Failed to join channel {channel_id}: {str(e)}")

            except Exception as e:
                logger.error(f"Error processing channel {channel_id}: {str(e)}")

    async def check_search_channels(self) -> None:
        """Verify user bot's presence in search channels"""
        if not self.user_bot:
            logger.warning("User bot not initialized, skipping channel check")
            return

        for channel_id in Config.SEARCH_CHANNELS:
            try:
                # Use get_chat to verify channel access
                chat = await self.user_bot.get_chat(channel_id)
                
                # Get member status
                member = await self.user_bot.get_chat_member(
                    chat.id,
                    (await self.user_bot.get_me()).id
                )
                
                logger.info(
                    f"User bot membership in {chat.title} ({chat.id}): {member.status}"
                )
                
            except Exception as e:
                logger.error(f"User bot is not in search channel {channel_id}: {str(e)}")
                # Try to join the channel again
                await self.join_search_channels()



    async def stop_user_bot(self) -> None:
        """Stop user bot client"""
        if self.user_bot:
            try:
                await self.user_bot.stop()
                logger.info("User bot stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping user bot: {e}")

    def register_handlers(self):
        """Register all message handlers"""
        try:
            from .handlers import register_all_handlers
            register_all_handlers(self)
            logger.info("Handlers registered successfully")
        except Exception as e:
            logger.error(f"Error registering handlers: {e}")
            raise

    async def initialize_database(self) -> bool:
        """Initialize database connections"""
        try:
            if not Config.DB_URL:
                raise DatabaseError("Database URL is not configured")

            motor_client = AsyncIOMotorClient(Config.DB_URL)
            self.db = motor_client.shadowfinder
            
            # Instead of checking truthiness, check for None
            if self.db is None:
                raise DatabaseError("Failed to initialize database")
            
            self.user_db = User(self.db)
            self.file_cache = FileCache(self.db)
            
            # Create indexes
            await self.db.users.create_index("user_id", unique=True)
            await self.db.file_cache.create_index("file_id", unique=True)
            await self.db.file_cache.create_index("file_name")
            await self.db.file_cache.create_index("last_accessed")
            
            logger.info("Database connection established")
            return True
            
        except pymongo.errors.ConnectionFailure as conn_error:
            logger.error(f"Failed to connect to MongoDB: {conn_error}")
            raise DatabaseError(f"MongoDB connection failed: {conn_error}")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            raise DatabaseError(f"Database initialization failed: {str(e)}")

    async def check_authorized_chats(self) -> None:
        """Verify bot's presence in authorized groups"""
        for chat_id in Config.AUTHORIZED_GROUPS:
            try:
                # Verify chat ID format
                if not str(chat_id).startswith('-100'):
                    logger.warning(f"Invalid group ID format: {chat_id}. Should start with -100")
                    continue
                    
                chat = await self.get_chat(chat_id)
                chat_type = "Channel" if str(chat.id).startswith('-100') else "Group"
                logger.info(
                    f"Bot is present in authorized {chat_type}: {chat.title} ({chat.id})"
                )
                
                # Check bot permissions
                bot_member = await self.get_chat_member(chat.id, (await self.get_me()).id)
                if not bot_member.privileges:
                    logger.warning(f"Bot is not admin in {chat.title} ({chat.id})")
                
            except Exception as e:
                logger.warning(f"Bot is not in authorized chat {chat_id}: {str(e)}")

    async def clean_cache_task(self) -> None:
        """Periodic task to clean old cache"""
        while True:
            try:
                if self.file_cache is not None:  # Explicit None check
                    cleaned = await self.file_cache.clean_old_cache(
                        days=Config.CACHE_CLEANUP_DAYS
                    )
                    logger.info(f"Cleaned {cleaned} old cache entries")
            except Exception as e:
                logger.error(f"Cache cleaning error: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
            await asyncio.sleep(86400)  # Run daily

    async def update_bot_stats_task(self) -> None:
        """Periodic task to update bot statistics"""
        while True:
            try:
                if self.db is None:
                    logger.warning("Database not initialized. Skipping stats update.")
                    await asyncio.sleep(3600)
                    continue

                stats: Dict[str, Any] = {
                    'total_users': await self.db.users.count_documents({}),
                    'active_users': await self.db.users.count_documents({
                        'last_used': {'$gte': datetime.now() - timedelta(days=7)}
                    }),
                    'total_files': await self.db.file_cache.count_documents({}),
                    'last_updated': datetime.now()
                }
                
                await self.db.stats.update_one(
                    {'_id': 'bot_stats'},
                    {'$set': stats},
                    upsert=True
                )
                
                logger.info(f"Bot stats updated: {stats}")
            except Exception as e:
                logger.error(f"Stats update error: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
            await asyncio.sleep(3600)  # Run hourly

    async def send_startup_message(self) -> None:
        """Send startup notification to owner"""
        try:
            system_info: Dict[str, str] = {
                'Platform': platform.system(),
                'Python': platform.python_version(),
                'Library': self.__class__.__name__,
                'Database': 'MongoDB',
                'Pyrogram': pyrogram.__version__,
                'Bot Version': Config.VERSION
            }
            
            # Add configuration info
            config_info = (
                f"**Configuration:**\n"
                f"🔐 Authorized Groups: `{len(Config.AUTHORIZED_GROUPS)}`\n"
                f"🔍 Search Channels: `{len(Config.SEARCH_CHANNELS)}`\n"
                f"📢 Force Sub: `{'Enabled' if Config.FORCE_SUB_CHANNEL else 'Disabled'}`\n"
                f"📝 Log Channel: `{'Set' if Config.LOG_CHANNEL else 'Not Set'}`\n"
                f"🤖 User Bot: `{'Connected' if self.user_bot else 'Not Connected'}`\n"
            )
            
            startup_msg = (
                "🗡️ **Shadow Monarch's Messenger has awakened** 🗡️\n\n"
                f"**System Information:**\n"
                f"🖥️ Platform: `{system_info['Platform']}`\n"
                f"🐍 Python: `{system_info['Python']}`\n"
                f"📚 Library: `{system_info['Library']}`\n"
                f"🗃️ Database: `{system_info['Database']}`\n"
                f"⚙️ Pyrogram: `{system_info['Pyrogram']}`\n"
                f"🤖 Bot Version: `{system_info['Bot Version']}`\n\n"
                f"{config_info}\n"
                f"⏰ Start Time: `{self.uptime_start.strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            
            await self.send_message(Config.OWNER_ID, startup_msg)
            if Config.LOG_CHANNEL:
                await self.send_message(Config.LOG_CHANNEL, startup_msg)
                
        except Exception as e:
            logger.error(f"Failed to send startup message: {str(e)}")

    def get_uptime(self) -> str:
        """Get bot uptime"""
        delta = datetime.now() - self.uptime_start
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d, {hours}h, {minutes}m, {seconds}s"

    async def start(self):
        """Start the bot"""
        try:
            logger.info("Starting ShadowFinder Bot...")
            
            # Initialize database
            await self.initialize_database()
            
            # Start bot client first
            await super().start()
            me: PyrogramUser = await self.get_me()
            logger.info(f"Bot Started as @{me.username}")
            
            # Initialize user bot after bot is started
            await self.initialize_user_bot()
            
            # Check authorized chats and search channels
            await self.check_authorized_chats()
            await self.check_search_channels()
            
            # Start background tasks
            self.tasks.extend([
                asyncio.create_task(self.clean_cache_task()),
                asyncio.create_task(self.update_bot_stats_task())
            ])
            
            # Send startup notification
            await self.send_startup_message()
            
            logger.info("Bot is ready to serve!")
            await idle()
            
        except DatabaseError as e:
            logger.error(f"Database error: {str(e)}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to start bot: {str(e)}")
            sys.exit(1)

    async def stop(self, *args) -> None:
        """Stop the bot"""
        try:
            # Stop user bot first
            await self.stop_user_bot()
            
            # Cancel all background tasks
            for task in self.tasks:
                task.cancel()
            
            # Wait for tasks to complete
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            # Send stop message to owner
            uptime = self.get_uptime()
            stop_msg = (
                "⚠️ **Shadow Monarch's Messenger is shutting down** ⚠️\n\n"
                f"⏰ Uptime: `{uptime}`\n"
                f"📅 Stop Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            
            await self.send_message(Config.OWNER_ID, stop_msg)
            if Config.LOG_CHANNEL:
                await self.send_message(Config.LOG_CHANNEL, stop_msg)
                
        except Exception as e:
            logger.error(f"Failed to send stop message: {str(e)}")
            
        try:
            await super().stop()
            logger.info("Bot stopped gracefully")
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")

    async def restart(self) -> None:
        """Restart the bot"""
        try:
            restart_msg = (
                "🔄 **Shadow Monarch's Messenger is restarting** 🔄\n\n"
                f"⏰ Uptime before restart: `{self.get_uptime()}`\n"
                f"📅 Restart Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            
            await self.send_message(Config.OWNER_ID, restart_msg)
            if Config.LOG_CHANNEL:
                await self.send_message(Config.LOG_CHANNEL, restart_msg)
                
            # Stop the bot
            await self.stop()
            
            # Restart using execl
            os.execl(sys.executable, sys.executable, "-m", "bot")
            
        except Exception as e:
            logger.error(f"Failed to restart bot: {str(e)}")
            await self.send_message(Config.OWNER_ID, f"❌ Failed to restart: {str(e)}")

if __name__ == "__main__":
    try:
        bot = ShadowFinder()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        sys.exit(1)