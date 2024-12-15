# bot/handlers/__init__.py
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler, InlineQueryHandler
from .commands import start_command, help_command, about_command
from .inline import handle_inline_query
from .callback import handle_callback
from .messages import handle_private_messages
from .admin import (
    admin_panel, ban_user, unban_user, broadcast, 
    user_stats, list_channels, check_id, check_config, add_authorized_channel, add_admin, restart_bot # Add check_config import
)
from ..config.config import Config

def register_all_handlers(app: Client) -> None:
    """Register all handlers with the application"""
    
    # Commands
    app.add_handler(MessageHandler(start_command, filters.command("start") & filters.private))
    app.add_handler(MessageHandler(help_command, filters.command("help")))
    app.add_handler(MessageHandler(about_command, filters.command("about")))
    
    # Admin commands
    app.add_handler(MessageHandler(admin_panel, filters.command(["admin", "panel"]) & filters.private))
    app.add_handler(MessageHandler(ban_user, filters.command("ban") & filters.group))
    app.add_handler(MessageHandler(unban_user, filters.command("unban") & filters.group))
    app.add_handler(MessageHandler(broadcast, filters.command("broadcast") & filters.user(Config.OWNER_ID)))
    app.add_handler(MessageHandler(user_stats, filters.command("stats") & filters.private))
    app.add_handler(MessageHandler(list_channels, filters.command("channels") & filters.private))
    app.add_handler(MessageHandler(restart_bot, filters.command("restart") & filters.private))
    app.add_handler(MessageHandler(check_id, filters.command("checkid") & filters.private))
    app.add_handler(MessageHandler(check_config, filters.command("checkconfig") & filters.private))  # Add checkconfig command
    app.add_handler(MessageHandler(add_authorized_channel, filters.command(["addchannel", "addgroup"])))
    app.add_handler(MessageHandler(add_admin, filters.command(["addadmin"]) & filters.user(Config.OWNER_ID)))

    
    # Inline
    app.add_handler(InlineQueryHandler(handle_inline_query))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Private Messages - Regular messages in private chat that are not commands
    app.add_handler(MessageHandler(
        handle_private_messages,
        filters.private & ~filters.command("start") & ~filters.command("help") & 
        ~filters.command("about") & ~filters.command("stats") & ~filters.command(["admin", "panel"]) &
        ~filters.command("channels") & ~filters.command("checkid") & ~filters.command("checkconfig")  # Add checkconfig to excluded commands
    ))