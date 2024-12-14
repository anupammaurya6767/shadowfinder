import os
from typing import List, Optional
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

class Config:
    """
    Centralized configuration class for the Telegram Bot.
    Uses environment variables for flexible configuration.
    """
    
    # Bot Authentication Credentials
    USER_SESSION_STRING: Optional[str] = os.getenv("USERBOT_STRING_SESSION")
    TEMP_CHANNEL: int = int(os.getenv("TEMP_CHANNEL", "0"))
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    USERNAME_OF_BOT: Optional[str] = os.getenv("USERNAME_OF_BOT")
    # Database Configuration
    DB_URL: Optional[str] = os.getenv("MONGODB_URL")
    
    # Access Control
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    AUTHORIZED_GROUPS: List[int] = [
        int(group_id.strip()) 
        for group_id in os.getenv("AUTHORIZED_GROUPS", "").split(",") 
        if group_id.strip()
    ]
    ADMIN_IDS: List[int] = [
        int(admin_id.strip()) 
        for admin_id in os.getenv("ADMIN_IDS", "").split(",") 
        if admin_id.strip()
    ]
    
    # Channel Configuration
    FORCE_SUB_ENABLED: bool = os.getenv("FORCE_SUB_ENABLED", "False").lower() == "true"
    FORCE_SUB_CHANNEL: Optional[int] = (
        int(os.getenv("FORCE_SUB_CHANNEL", "0"))
        if os.getenv("FORCE_SUB_ENABLED", "False").lower() == "true"
        else None
    )
    SEARCH_CHANNELS: List[int] = [
        int(channel_id.strip()) 
        for channel_id in os.getenv("SEARCH_CHANNELS", "").split(",") 
        if channel_id.strip()
    ]
    LOG_CHANNEL: Optional[int] = int(os.getenv("LOG_CHANNEL", "0")) or None
    
    # Bot Performance and Limits
    WORKERS: int = int(os.getenv("WORKERS", "4"))
    MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "50"))
    MIN_SEARCH_LENGTH: int = int(os.getenv("MIN_SEARCH_LENGTH", "3"))
    MAX_CONCURRENT_TRANSMISSIONS: int = int(os.getenv("MAX_CONCURRENT_TRANSMISSIONS", "10"))
    
    # Cleanup and Timeout Settings
    DELETE_TIMEOUT: int = int(os.getenv("DELETE_TIMEOUT", "600"))  # 10 minutes
    CACHE_CLEANUP_DAYS: int = int(os.getenv("CACHE_CLEANUP_DAYS", "30"))
    MAX_CACHE_SIZE: int = int(os.getenv("MAX_CACHE_SIZE", "10000"))
    
    # Customization
    START_PIC: str = os.getenv("START_PIC", "https://telegra.ph/file/default-start-pic.jpg")
    
    # Bot Metadata
    VERSION: str = os.getenv("VERSION", "")
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate critical configuration parameters.
        
        Returns:
            bool: True if all critical configurations are set, False otherwise.
        """
        critical_configs = [
            cls.BOT_TOKEN,
            cls.API_ID,
            cls.API_HASH,
            cls.OWNER_ID,
            cls.TEMP_CHANNEL
        ]
        
        # Validate force sub configuration if enabled
        if cls.FORCE_SUB_ENABLED and not cls.FORCE_SUB_CHANNEL:
            logger.warning("Force subscribe is enabled but no channel ID is provided!")
            return False
            
        return all(critical_configs)

    @classmethod
    def debug_info(cls) -> str:
        """Get debug information about configuration"""
        info = {
            "Bot Token": "✅ Set" if cls.BOT_TOKEN else "❌ Not Set",
            "API ID": "✅ Set" if cls.API_ID != 0 else "❌ Not Set",
            "API Hash": "✅ Set" if cls.API_HASH else "❌ Not Set",
            "Database URL": "✅ Set" if cls.DB_URL else "❌ Not Set",
            "Owner ID": cls.OWNER_ID,
            "Admin IDs": len(cls.ADMIN_IDS),
            "Authorized Groups": cls.AUTHORIZED_GROUPS,
            "Force Sub Channel": cls.FORCE_SUB_CHANNEL,
            "Search Channels": len(cls.SEARCH_CHANNELS),
            "Log Channel": cls.LOG_CHANNEL,
            "Workers": cls.WORKERS,
            "Max Results": cls.MAX_RESULTS,
            "Min Search Length": cls.MIN_SEARCH_LENGTH,
            "Delete Timeout": f"{cls.DELETE_TIMEOUT} seconds",
            "Cache Cleanup Days": cls.CACHE_CLEANUP_DAYS,
            "Version": cls.VERSION or "Not Set"
        }
        
        return "\n".join(f"{k}: {v}" for k, v in info.items())