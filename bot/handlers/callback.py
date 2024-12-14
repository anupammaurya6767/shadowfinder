from datetime import datetime, timedelta
from pyrogram import Client, errors
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    Message
)
from bot.database.models import FileCache, User
from bot.handlers.admin import get_bot_stats
from ..helpers.utils import delete_message_later
from ..templates.messages import Messages
from ..config.config import Config
from pyrogram import enums
from loguru import logger
import asyncio

async def handle_settings_action(client: Client, callback_query: CallbackQuery):
    """Handle settings menu actions"""
    try:
        action = callback_query.data.split('_')[2] if len(callback_query.data.split('_')) > 2 else "view"
        
        if action == "view":
            settings_text = (
                "⚙️ **Bot Settings**\n\n"
                f"**General Settings:**\n"
                f"• Workers: {Config.WORKERS}\n"
                f"• Max Concurrent: {Config.MAX_CONCURRENT_TRANSMISSIONS}\n\n"
                f"**Search Settings:**\n"
                f"• Min Search Length: {Config.MIN_SEARCH_LENGTH}\n"
                f"• Max Results: {Config.MAX_RESULTS}\n\n"
                f"**File Settings:**\n"
                f"• Delete Timeout: {Config.DELETE_TIMEOUT}s\n"
                f"• Cache Cleanup: {Config.CACHE_CLEANUP_DAYS} days\n\n"
                f"**Channel Settings:**\n"
                f"• Force Sub: {'✅' if Config.FORCE_SUB_CHANNEL else '❌'}\n"
                f"• Log Channel: {'✅' if Config.LOG_CHANNEL else '❌'}"
            )
            
            buttons = [
                [
                    InlineKeyboardButton("🔄 Update Settings", callback_data="admin_settings_edit"),
                    InlineKeyboardButton("📝 Edit Config", callback_data="admin_settings_config")
                ],
                [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")]
            ]
            
            await callback_query.edit_message_text(
                settings_text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif action == "edit":
            # Show editable settings
            buttons = [
                [
                    InlineKeyboardButton("⚙️ General", callback_data="admin_settings_section_general"),
                    InlineKeyboardButton("🔍 Search", callback_data="admin_settings_section_search")
                ],
                [
                    InlineKeyboardButton("📁 Files", callback_data="admin_settings_section_files"),
                    InlineKeyboardButton("📢 Channels", callback_data="admin_settings_section_channels")
                ],
                [InlineKeyboardButton("« Back to Settings", callback_data="admin_settings_view")]
            ]
            
            await callback_query.edit_message_text(
                "⚙️ **Edit Settings**\n\nSelect a category to modify settings:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
    except Exception as e:
        logger.error(f"Error in settings action: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

# Broadcast Implementation
async def handle_broadcast_message(client: Client, message: Message, filter_query: dict = None):
    """Process broadcast message"""
    status_msg = await message.reply_text("📢 Starting broadcast...")
    
    success = 0
    failed = 0
    
    async for user in client.db.users.find(filter_query or {}):
        try:
            await message.copy(user['user_id'])
            success += 1
            
            # Update status every 20 users
            if success % 20 == 0:
                await status_msg.edit_text(
                    f"🔄 Broadcasting...\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}"
                )
                
            await asyncio.sleep(0.1)  # Prevent flooding
            
        except Exception as e:
            logger.error(f"Broadcast failed for user {user['user_id']}: {e}")
            failed += 1
            
    await status_msg.edit_text(
        f"📢 **Broadcast Completed**\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"💠 Total: {success + failed}"
    )

async def handle_broadcast_setup(client: Client, callback_query: CallbackQuery):
    """Setup broadcast message"""
    try:
        broadcast_type = callback_query.data.split('_')[2]
        message_type = callback_query.data.split('_')[3] if len(callback_query.data.split('_')) > 3 else "text"
        
        if broadcast_type == "all":
            filter_query = {}
            target = "all users"
        elif broadcast_type == "active":
            filter_query = {
                'last_used': {'$gte': datetime.now() - timedelta(days=7)}
            }
            target = "active users"
        else:
            await callback_query.answer("Invalid broadcast type!")
            return
            
        total_users = await client.db.users.count_documents(filter_query)
        
        buttons = [[InlineKeyboardButton("« Cancel", callback_data="admin_broadcast")]]
        
        await callback_query.edit_message_text(
            f"📢 **Broadcast Setup**\n\n"
            f"Target: {target}\n"
            f"Estimated recipients: {total_users}\n\n"
            f"{'Send me the text message' if message_type == 'text' else 'Send me the media with caption'} "
            f"to broadcast. Use /cancel to cancel.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        # Set user state
        client.broadcast_states[callback_query.from_user.id] = {
            'state': 'awaiting_broadcast',
            'filter': filter_query,
            'type': message_type
        }
        
    except Exception as e:
        logger.error(f"Error in broadcast setup: {e}")
        await callback_query.answer(
            "Error setting up broadcast. Please try again.",
            show_alert=True
        )

# Updated Logs Implementation
async def admin_logs_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Logs button in admin panel"""
    try:
        # Get log level from callback data if provided, default to INFO
        parts = callback_query.data.split('_')
        level = parts[2] if len(parts) > 2 else "INFO"
        page = int(parts[3]) if len(parts) > 3 else 1
        
        try:
            with open("logs/shadowfinder.log", "r", encoding='utf-8') as file:
                # Read all lines and reverse them
                all_logs = file.readlines()
                all_logs.reverse()
                
                # Filter logs by level if specified
                if level != "ALL":
                    filtered_logs = [line for line in all_logs if f"| {level}    |" in line]
                else:
                    filtered_logs = all_logs
                
                # Paginate logs - 10 logs per page
                start_idx = (page - 1) * 10
                end_idx = start_idx + 10
                current_logs = filtered_logs[start_idx:end_idx]
                total_pages = (len(filtered_logs) + 9) // 10
                
                # Format logs for display
                logs_text = "📝 **Bot Logs**\n\n"
                
                if not current_logs:
                    logs_text += "No logs found for the selected criteria."
                else:
                    for log in current_logs:
                        # Parse and format log entry
                        try:
                            parts = log.split("|")
                            timestamp = parts[0].strip()
                            log_level = parts[1].strip()
                            message = parts[-1].strip()
                            
                            if "ERROR" in log_level:
                                logs_text += f"❌ `{timestamp}`\n{message}\n\n"
                            elif "WARNING" in log_level:
                                logs_text += f"⚠️ `{timestamp}`\n{message}\n\n"
                            else:
                                logs_text += f"ℹ️ `{timestamp}`\n{message}\n\n"
                        except:
                            logs_text += f"{log}\n\n"
                
                logs_text += f"\nPage {page}/{total_pages}"
                
                buttons = []
                
                # Level filter buttons
                level_buttons = []
                for log_level in ["ALL", "INFO", "WARNING", "ERROR"]:
                    level_buttons.append(
                        InlineKeyboardButton(
                            f"{'✅' if level == log_level else ''} {log_level}", 
                            callback_data=f"admin_logs_{log_level}_1"
                        )
                    )
                buttons.append(level_buttons)
                
                # Navigation buttons
                nav_buttons = []
                if page > 1:
                    nav_buttons.append(
                        InlineKeyboardButton(
                            "« Previous", 
                            callback_data=f"admin_logs_{level}_{page-1}"
                        )
                    )
                if page < total_pages:
                    nav_buttons.append(
                        InlineKeyboardButton(
                            "Next »", 
                            callback_data=f"admin_logs_{level}_{page+1}"
                        )
                    )
                if nav_buttons:
                    buttons.append(nav_buttons)
                
                # Action buttons
                buttons.append([
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"admin_logs_{level}_{page}"),
                    InlineKeyboardButton("📥 Download", callback_data="admin_logs_download")
                ])
                
                buttons.append([
                    InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")
                ])
                
                await callback_query.edit_message_text(
                    logs_text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                
        except FileNotFoundError:
            await callback_query.edit_message_text(
                "📝 **Bot Logs**\n\n❌ Log file not found!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")
                ]])
            )
            
    except Exception as e:
        logger.error(f"Error in admin logs callback: {e}")
        await callback_query.answer(
            "Error fetching logs. Please try again.",
            show_alert=True
        )

async def handle_logs_download(client: Client, callback_query: CallbackQuery):
    """Handle log file download request"""
    try:
        # Send the log file
        await client.send_document(
            callback_query.from_user.id,
            "logs/shadowfinder.log",
            caption="📝 Bot Logs File",
            file_name="bot_logs.txt"
        )
        await callback_query.answer("Log file sent to your PM!")
    except FileNotFoundError:
        await callback_query.answer("Log file not found!", show_alert=True)
    except Exception as e:
        logger.error(f"Error sending log file: {e}")
        await callback_query.answer(
            "Error sending log file. Please try again.",
            show_alert=True
        )

async def admin_panel_callback(client: Client, callback_query: CallbackQuery):
    """Handle the main admin panel callback"""
    try:
        stats = await get_bot_stats(client.db)
        
        buttons = [
            [
                InlineKeyboardButton("👥 Users", callback_data="admin_users"),
                InlineKeyboardButton("🚫 Banned", callback_data="admin_banned")
            ],
            [
                InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
                InlineKeyboardButton("📝 Logs", callback_data="admin_logs")
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
                InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")
            ],
            [
                InlineKeyboardButton("🔄 Refresh Channels", callback_data="refresh_channels")
            ]
        ]
        
        panel_text = (
            "⚔️ **Shadow Monarch's Admin Panel** ⚔️\n\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"🚫 Banned Users: {stats['banned_users']}\n"
            f"📁 Cached Files: {stats['total_files']}\n"
            f"📥 Total Downloads: {stats['total_downloads']}\n"
        )
        
        try:
            await callback_query.edit_message_text(
                panel_text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except errors.MessageNotModified:
            await callback_query.answer("Panel is already up to date")
            
    except Exception as e:
        logger.error(f"Error in admin panel callback: {e}")
        await callback_query.answer(
            "Error loading admin panel. Please try again.",
            show_alert=True
        )


def is_admin_or_owner(user_id: int) -> bool:
    """Check if user is admin or owner"""
    return user_id == Config.OWNER_ID or user_id in Config.ADMIN_IDS

async def handle_user_page(client: Client, callback_query: CallbackQuery):
    """Handle user list pagination with improved error handling"""
    try:
        page = int(callback_query.data.split('_')[-1])
        skip = (page - 1) * 10
        
        # Get total count first
        total_users = await client.db.users.count_documents({})
        
        # Get paginated users
        users = await client.db.users.find().skip(skip).limit(10).to_list(length=10)
        
        user_buttons = []
        user_text = f"👥 **User List** (Page {page})\n\n"
        user_text += f"Total Users: {total_users}\n\n"
        
        for user in users:
            try:
                # Get user details from Telegram
                user_info = await client.get_users(user['user_id'])
                name = user_info.first_name
                if user_info.last_name:
                    name += f" {user_info.last_name}"
                username = f"@{user_info.username}" if user_info.username else "No username"
                
                status = "🚫" if user.get('banned', False) else "✅"
                user_entry = f"{status} {name} | {username}"
            except Exception as e:
                logger.warning(f"Could not get user info for {user['user_id']}: {e}")
                user_entry = f"User {user['user_id']}"
            
            user_text += f"• {user_entry}\n"
            user_buttons.append([
                InlineKeyboardButton(
                    user_entry[:64],  # Telegram button text limit
                    callback_data=f"user_details_{user['user_id']}"
                )
            ])
        
        # Add navigation buttons
        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton("« Previous", callback_data=f"admin_users_page_{page-1}")
            )
        if (page * 10) < total_users:
            nav_buttons.append(
                InlineKeyboardButton("Next »", callback_data=f"admin_users_page_{page+1}")
            )
        
        user_buttons.append(nav_buttons)
        user_buttons.append([InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")])
        
        try:
            await callback_query.edit_message_text(
                user_text,
                reply_markup=InlineKeyboardMarkup(user_buttons)
            )
        except errors.MessageNotModified:
            await callback_query.answer("Page is already displayed")
        except errors.MessageIdInvalid:
            await callback_query.message.reply_text(
                user_text,
                reply_markup=InlineKeyboardMarkup(user_buttons)
            )
            
    except errors.FloodWait as e:
        logger.warning(f"FloodWait in pagination: {e.value} seconds")
        await callback_query.answer(
            f"Please wait {e.value} seconds before changing pages",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error in user pagination: {e}")
        await callback_query.answer(
            "Error loading user page. Please try again.",
            show_alert=True
        )

async def handle_user_details(client: Client, callback_query: CallbackQuery):
    """Handle user details display"""
    try:
        user_id = int(callback_query.data.split('_')[-1])
        user_data = await client.db.users.find_one({'user_id': user_id})
        
        if not user_data:
            await callback_query.answer("User not found!", show_alert=True)
            return
            
        try:
            user_info = await client.get_users(user_id)
            name = user_info.first_name
            if user_info.last_name:
                name += f" {user_info.last_name}"
        except:
            name = "Unknown"
            
        details = (
            f"👤 **User Details**\n\n"
            f"**Name**: {name}\n"
            f"**User ID**: `{user_id}`\n"
            f"**Username**: @{user_data.get('username', 'None')}\n"
            f"**Joined**: {user_data['joined_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Total Downloads**: {user_data.get('downloads', 0)}\n"
            f"**Total Searches**: {user_data.get('searches', 0)}\n"
            f"**Last Active**: {user_data['last_used'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Status**: {'🚫 Banned' if user_data.get('banned', False) else '✅ Active'}"
        )
        
        buttons = []
        if user_data.get('banned', False):
            buttons.append([InlineKeyboardButton("✅ Unban User", callback_data=f"unban_user_{user_id}")])
        else:
            buttons.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_user_{user_id}")])
            
        buttons.extend([
            [InlineKeyboardButton("📊 User Stats", callback_data=f"user_stats_{user_id}")],
            [InlineKeyboardButton("« Back to Users", callback_data="admin_users")]
        ])
        
        await callback_query.edit_message_text(
            details,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in user details handler: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

async def handle_user_stats(client: Client, callback_query: CallbackQuery):
    """Handle detailed user statistics"""
    try:
        user_id = int(callback_query.data.split('_')[-1])
        user_data = await client.db.users.find_one({'user_id': user_id})
        
        if not user_data:
            await callback_query.answer("User not found!", show_alert=True)
            return
            
        # Get user's recent activities
        recent_downloads = await client.db.downloads.find(
            {'user_id': user_id}
        ).sort('timestamp', -1).limit(5).to_list(length=5)
        
        recent_searches = await client.db.searches.find(
            {'user_id': user_id}
        ).sort('timestamp', -1).limit(5).to_list(length=5)
        
        stats_text = (
            f"📊 **Detailed Stats for User {user_id}**\n\n"
            f"**Activity Summary:**\n"
            f"• Total Downloads: {user_data.get('downloads', 0)}\n"
            f"• Total Searches: {user_data.get('searches', 0)}\n"
            f"• Active Days: {(datetime.now() - user_data['joined_date']).days}\n\n"
            f"**Recent Downloads:**\n"
        )
        
        for dl in recent_downloads:
            stats_text += f"• {dl.get('file_name', 'Unknown')} ({dl['timestamp'].strftime('%Y-%m-%d')})\n"
            
        stats_text += "\n**Recent Searches:**\n"
        for search in recent_searches:
            stats_text += f"• {search.get('query', 'Unknown')} ({search['timestamp'].strftime('%Y-%m-%d')})\n"
        
        buttons = [
            [InlineKeyboardButton("« Back to User Details", callback_data=f"user_details_{user_id}")]
        ]
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in user stats handler: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

async def handle_banned_user_details(client: Client, callback_query: CallbackQuery):
    """Handle banned user details display"""
    try:
        user_id = int(callback_query.data.split('_')[-1])
        user_data = await client.db.users.find_one({'user_id': user_id, 'banned': True})
        
        if not user_data:
            await callback_query.answer("Banned user not found!", show_alert=True)
            return
            
        details = (
            f"🚫 **Banned User Details**\n\n"
            f"**User ID**: `{user_id}`\n"
            f"**Username**: @{user_data.get('username', 'None')}\n"
            f"**Banned On**: {user_data.get('ban_date', 'Unknown')}\n"
            f"**Banned By**: {user_data.get('banned_by', 'Unknown')}\n"
            f"**Reason**: {user_data.get('ban_reason', 'No reason provided')}\n\n"
            f"**Account Info:**\n"
            f"• Joined: {user_data['joined_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"• Total Downloads: {user_data.get('downloads', 0)}\n"
            f"• Total Searches: {user_data.get('searches', 0)}"
        )
        
        buttons = [
            [InlineKeyboardButton("✅ Unban User", callback_data=f"unban_user_{user_id}")],
            [InlineKeyboardButton("« Back to Banned Users", callback_data="admin_banned")]
        ]
        
        await callback_query.edit_message_text(
            details,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in banned user details handler: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

async def handle_detailed_stats(client: Client, callback_query: CallbackQuery):
    """Handle detailed statistics display"""
    try:
        stats = await get_bot_stats()
        file_cache = FileCache(client.db)
        
        # Get today's stats
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_downloads = await client.db.downloads.count_documents({
            'timestamp': {'$gte': today}
        })
        today_searches = await client.db.searches.count_documents({
            'timestamp': {'$gte': today}
        })
        
        # Get most active users
        active_users = await client.db.users.find().sort(
            'downloads', -1
        ).limit(5).to_list(length=5)
        
        # Get popular files
        popular_files = await file_cache.get_popular_files(5)
        
        stats_text = (
            "📊 **Detailed Bot Statistics**\n\n"
            f"**Today's Activity:**\n"
            f"• Downloads: {today_downloads}\n"
            f"• Searches: {today_searches}\n\n"
            f"**Overall Stats:**\n"
            f"• Total Users: {stats['total_users']}\n"
            f"• Active Users (7d): {stats['active_users']}\n"
            f"• Banned Users: {stats['banned_users']}\n"
            f"• Total Files: {stats['total_files']}\n"
            f"• Total Downloads: {stats['total_downloads']}\n\n"
            f"**Most Active Users:**\n"
        )
        
        for user in active_users:
            stats_text += f"• ID: {user['user_id']} - {user.get('downloads', 0)} downloads\n"
            
        stats_text += "\n**Most Popular Files:**\n"
        for file in popular_files:
            stats_text += f"• {file['file_name']} ({file['access_count']} downloads)\n"
        
        buttons = [
            [
                InlineKeyboardButton("📈 Usage Trends", callback_data="stats_trends"),
                InlineKeyboardButton("📊 Daily Stats", callback_data="stats_daily")
            ],
            [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")]
        ]
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in detailed stats handler: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

async def handle_user_unban(client: Client, callback_query: CallbackQuery):
    """Handle user unban callback"""
    try:
        # Get user ID from callback data
        user_id = int(callback_query.data.split('_')[-1])
        
        # Get user data
        user_data = await client.db.users.find_one({'user_id': user_id})
        
        if not user_data:
            await callback_query.answer("User not found!", show_alert=True)
            return
            
        if not user_data.get('banned', False):
            await callback_query.answer("User is not banned!", show_alert=True)
            return
            
        try:
            # Update user data
            await client.db.users.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'banned': False,
                        'unbanned_by': callback_query.from_user.id,
                        'unban_date': datetime.now(),
                    },
                    '$unset': {
                        'ban_reason': "",
                        'banned_by': "",
                        'ban_date': ""
                    }
                }
            )
            
            # Try to get user info
            try:
                user_info = await client.get_users(user_id)
                user_mention = user_info.mention
                username = f"@{user_info.username}" if user_info.username else "No username"
            except:
                user_mention = f"User {user_id}"
                username = "Unknown"
            
            # Send unban notification to log channel
            if Config.LOG_CHANNEL:
                log_text = (
                    "✅ **User Unbanned**\n\n"
                    f"**User:** {user_mention} [`{user_id}`]\n"
                    f"**Username:** {username}\n"
                    f"**Unbanned By:** {callback_query.from_user.mention}\n"
                    f"**Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                try:
                    await client.send_message(Config.LOG_CHANNEL, log_text)
                except Exception as e:
                    logger.error(f"Failed to send unban log: {e}")
            
            # Notify user about unban
            try:
                unban_message = (
                    "✅ **You have been unbanned!**\n\n"
                    f"You can now use the bot again.\n"
                    f"Unbanned by: {callback_query.from_user.mention}"
                )
                await client.send_message(user_id, unban_message)
            except Exception as e:
                logger.warning(f"Failed to notify user about unban: {e}")
            
            # Show success message
            await callback_query.answer("User unbanned successfully!", show_alert=True)
            
            # Update the message to show updated user status
            buttons = [[
                InlineKeyboardButton("🔙 Back to Users", callback_data="admin_banned")
            ]]
            
            success_text = (
                f"✅ **User Unbanned Successfully**\n\n"
                f"**User ID:** `{user_id}`\n"
                f"**Username:** {username}\n"
                f"**Unbanned By:** {callback_query.from_user.mention}\n"
                f"**Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            
            try:
                await callback_query.edit_message_text(
                    success_text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except errors.MessageNotModified:
                pass
                
        except Exception as db_error:
            logger.error(f"Database error in unban: {db_error}")
            await callback_query.answer(
                "Failed to unban user. Database error.",
                show_alert=True
            )
            
    except ValueError:
        await callback_query.answer(
            "Invalid user ID format!",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error in unban handler: {e}")
        await callback_query.answer(
            "An error occurred while unbanning user.",
            show_alert=True
        )

async def handle_broadcast_setup(client: Client, callback_query: CallbackQuery):
    """Handle broadcast message setup"""
    try:
        broadcast_type = callback_query.data.split('_')[-1]
        
        if broadcast_type == "all":
            target_text = "all users"
            filter_query = {}
        elif broadcast_type == "active":
            target_text = "active users (last 7 days)"
            filter_query = {
                'last_used': {
                    '$gte': datetime.now() - timedelta(days=7)
                }
            }
        else:
            await callback_query.answer("Invalid broadcast type!", show_alert=True)
            return
            
        user_count = await client.db.users.count_documents(filter_query)
        
        setup_text = (
            "📢 **Broadcast Setup**\n\n"
            f"Target: {target_text}\n"
            f"Estimated recipients: {user_count}\n\n"
            "**Please choose the broadcast type:**"
        )
        
        buttons = [
            [
                InlineKeyboardButton("📝 Text Only", callback_data=f"broadcast_text_{broadcast_type}"),
                InlineKeyboardButton("🖼 With Media", callback_data=f"broadcast_media_{broadcast_type}")
            ],
            [InlineKeyboardButton("« Back", callback_data="admin_broadcast")]
        ]
        
        await callback_query.edit_message_text(
            setup_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error in broadcast setup handler: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)



async def admin_users_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Users button in admin panel"""
    try:
        users = await client.db.users.find().to_list(length=10)
        
        user_buttons = []
        user_details_text = "👥 **User List**\n\n"
        
        for user in users:
            try:
                # Get user details from Telegram
                user_info = await client.get_users(user['user_id'])
                name = user_info.first_name
                if user_info.last_name:
                    name += f" {user_info.last_name}"
                username = f"@{user_info.username}" if user_info.username else "No username"
                
                user_text = f"{name} | {username}"
            except Exception as e:
                logger.warning(f"Could not get user info for {user['user_id']}: {e}")
                user_text = f"User {user['user_id']}"
            
            user_buttons.append([
                InlineKeyboardButton(
                    user_text, 
                    callback_data=f"user_details_{user['user_id']}"
                )
            ])
            user_details_text += f"• {user_text}\n"
        
        user_buttons.append([
            InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel"),
            InlineKeyboardButton("Next Page »", callback_data="admin_users_page_2")
        ])
        
        # Try to edit the message, handle MESSAGE_NOT_MODIFIED error
        try:
            await callback_query.edit_message_text(
                user_details_text,
                reply_markup=InlineKeyboardMarkup(user_buttons)
            )
        except errors.MessageNotModified:
            # Message is already showing the same content, ignore this error
            await callback_query.answer("User list is already up to date")
        except errors.MessageIdInvalid:
            # Message might have been deleted, send new message
            await callback_query.message.reply_text(
                user_details_text,
                reply_markup=InlineKeyboardMarkup(user_buttons)
            )
            
    except errors.UserNotParticipant:
        logger.warning("Bot was removed from the chat")
        await callback_query.answer(
            "Bot was removed from the chat. Please add bot again.",
            show_alert=True
        )
    except errors.FloodWait as e:
        logger.warning(f"FloodWait received: {e.value} seconds")
        await callback_query.answer(
            f"Please wait {e.value} seconds before refreshing",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Error in admin users callback: {e}")
        error_message = "An error occurred while fetching user list"
        
        # Check if we can edit the message
        try:
            await callback_query.edit_message_text(
                f"❌ {error_message}\n\nError: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Retry", callback_data="admin_users"),
                    InlineKeyboardButton("« Back", callback_data="admin_panel")
                ]])
            )
        except:
            # If we can't edit, try to answer the callback
            await callback_query.answer(error_message, show_alert=True)

async def admin_banned_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Banned Users button in admin panel"""
    try:
        # Fetch banned users
        banned_users = await client.db.users.find({'banned': True}).to_list(length=10)
        
        banned_buttons = []
        for user in banned_users:
            banned_buttons.append([
                InlineKeyboardButton(
                    f"{user.get('username', 'Unknown')} (ID: {user['user_id']})", 
                    callback_data=f"banned_user_details_{user['user_id']}"
                )
            ])
        
        banned_buttons.append([
            InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel"),
            InlineKeyboardButton("Unban Selected", callback_data="admin_unban_users")
        ])
        
        await callback_query.edit_message_text(
            "🚫 **Banned Users**\n\n"
            "Select a user for more details or manage bans.",
            reply_markup=InlineKeyboardMarkup(banned_buttons)
        )
    except Exception as e:
        logger.error(f"Error in admin banned callback: {e}")
        await callback_query.answer(f"Error fetching banned users: {str(e)}", show_alert=True)

async def admin_stats_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Statistics button in admin panel"""
    try:
        # Fetch comprehensive bot statistics
        stats = await get_bot_stats(client.db)
        
        # Fetch some additional stats from the models
        user_model = User(client.db)
        file_cache = FileCache(client.db)
        
        # Get most popular files
        popular_files = await file_cache.get_popular_files(5)
        popular_files_text = "\n".join([
            f"{file['file_name']} (Accessed: {file['access_count']} times)" 
            for file in popular_files
        ])
        
        stats_text = (
            "📊 **Bot Statistics**\n\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"🚫 Banned Users: {stats['banned_users']}\n"
            f"📁 Cached Files: {stats['total_files']}\n"
            f"📥 Total Downloads: {stats['total_downloads']}\n\n"
            "🔥 **Most Popular Files:**\n"
            f"{popular_files_text}"
        )
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    except Exception as e:
        logger.error(f"Error in admin stats callback: {e}")
        await callback_query.answer(f"Error fetching statistics: {str(e)}", show_alert=True)


async def admin_broadcast_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Broadcast button in admin panel"""
    try:
        await callback_query.edit_message_text(
            "📢 **Broadcast Message**\n\n"
            "Select broadcast options:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("All Users", callback_data="broadcast_all_users"),
                    InlineKeyboardButton("Active Users", callback_data="broadcast_active_users")
                ],
                [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")]
            ])
        )
    except Exception as e:
        logger.error(f"Error in admin broadcast callback: {e}")
        await callback_query.answer(f"Broadcast setup error: {str(e)}", show_alert=True)

async def admin_settings_callback(client: Client, callback_query: CallbackQuery):
    """Handle the Settings button in admin panel"""
    try:
        settings_text = (
            "⚙️ **Bot Settings**\n\n"
            f"**General Settings:**\n"
            f"• Workers: {Config.WORKERS}\n"
            f"• Max Concurrent: {Config.MAX_CONCURRENT_TRANSMISSIONS}\n\n"
            f"**Search Settings:**\n"
            f"• Min Search Length: {Config.MIN_SEARCH_LENGTH}\n"
            f"• Max Results: {Config.MAX_RESULTS}\n\n"
            f"**File Settings:**\n"
            f"• Delete Timeout: {Config.DELETE_TIMEOUT}s\n"
            f"• Cache Cleanup: {Config.CACHE_CLEANUP_DAYS} days\n\n"
            f"**Channel Settings:**\n"
            f"• Force Sub: {'✅' if Config.FORCE_SUB_CHANNEL else '❌'}\n"
            f"• Log Channel: {'✅' if Config.LOG_CHANNEL else '❌'}"
        )
        
        buttons = [
            [
                InlineKeyboardButton("🛠 General", callback_data="settings_section_general"),
                InlineKeyboardButton("🔍 Search", callback_data="settings_section_search")
            ],
            [
                InlineKeyboardButton("📁 Files", callback_data="settings_section_files"),
                InlineKeyboardButton("📢 Channels", callback_data="settings_section_channels")
            ],
            [InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")]
        ]
        
        await callback_query.edit_message_text(
            settings_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        logger.error(f"Error in admin settings callback: {e}")
        await callback_query.answer(f"Error fetching settings: {str(e)}", show_alert=True)

async def refresh_channels_callback(client: Client, callback_query):
    """Handle refresh channels button callback"""
    try:
        if not is_admin_or_owner(callback_query.from_user.id):
            await callback_query.answer("You're not authorized to do this!", show_alert=True)
            return

        # Get updated channels list
        channels_text = "📑 **Configured Search Channels:**\n\n"
        
        for channel_id in Config.SEARCH_CHANNELS:
            try:
                chat = await client.get_chat(channel_id)
                chat_type = "Channel" if chat.type == enums.ChatType.CHANNEL else "Group"
                member_count = await client.get_chat_members_count(channel_id)
                channels_text += (
                    f"• **{chat.title}**\n"
                    f"  ├ **ID**: `{channel_id}`\n"
                    f"  ├ **Type**: `{chat_type}`\n"
                    f"  ├ **Members**: `{member_count}`\n"
                    f"  └ **Username**: @{chat.username if chat.username else 'Private'}\n\n"
                )
            except Exception as e:
                channels_text += f"• **Channel ID**: `{channel_id}`\n  └ Error: `{str(e)}`\n\n"

        if not Config.SEARCH_CHANNELS:
            channels_text += "❌ No channels configured for search!"

        channels_text += f"\n**Total Configured Channels**: `{len(Config.SEARCH_CHANNELS)}`"
        
        buttons = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_channels")
        ]]

        await callback_query.message.edit_text(
            channels_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await callback_query.answer("Channel list refreshed!")

    except Exception as e:
        logger.error(f"Error in refresh channels callback: {e}")
        await callback_query.answer("Error refreshing channels list!", show_alert=True)

async def handle_settings_section(client: Client, callback_query: CallbackQuery):
    """Handle settings section selection"""
    try:
        # Get section from callback data
        section = callback_query.data.split('_')[-1]
        
        # Define settings data
        settings_data = {
            "general": {
                "title": "General Settings",
                "settings": {
                    "Workers": Config.WORKERS,
                    "Max Concurrent": Config.MAX_CONCURRENT_TRANSMISSIONS,
                    "Delete Timeout": f"{Config.DELETE_TIMEOUT}s"
                }
            },
            "search": {
                "title": "Search Settings",
                "settings": {
                    "Min Search Length": Config.MIN_SEARCH_LENGTH,
                    "Max Results": Config.MAX_RESULTS
                }
            },
            "files": {
                "title": "File Settings",
                "settings": {
                    "Cache Cleanup Days": Config.CACHE_CLEANUP_DAYS,
                    "Max Cache Size": getattr(Config, 'MAX_CACHE_SIZE', 10000)
                }
            },
            "channels": {
                "title": "Channel Settings",
                "settings": {
                    "Force Sub Channel": Config.FORCE_SUB_CHANNEL or "Not Set",
                    "Log Channel": Config.LOG_CHANNEL or "Not Set",
                    "Total Search Channels": len(Config.SEARCH_CHANNELS)
                }
            }
        }
        
        if section not in settings_data:
            await callback_query.answer("Invalid settings section!", show_alert=True)
            return
            
        section_data = settings_data[section]
        
        # Create settings text
        settings_text = f"⚙️ **{section_data['title']}**\n\n"
        for key, value in section_data['settings'].items():
            settings_text += f"• **{key}:** `{value}`\n"
        
        # Create buttons
        buttons = []
        for key in section_data['settings'].keys():
            setting_id = key.lower().replace(' ', '_')
            buttons.append([
                InlineKeyboardButton(
                    f"Edit {key}",
                    callback_data=f"settings_edit_{section}_{setting_id}"
                )
            ])
        
        # Add navigation button
        buttons.append([
            InlineKeyboardButton("« Back to Settings", callback_data="admin_settings")
        ])
        
        await callback_query.edit_message_text(
            settings_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        logger.error(f"Error in settings section handler: {e}")
        await callback_query.answer("Error loading settings section", show_alert=True)

async def handle_settings_edit(client: Client, callback_query: CallbackQuery):
    """Handle editing individual settings"""
    try:
        parts = callback_query.data.split('_')
        if len(parts) < 4:
            await callback_query.answer("Invalid edit callback", show_alert=True)
            return
            
        section = parts[2]
        setting = parts[3]
        
        # Show input instructions based on setting type
        setting_info = {
            'workers': {'type': 'integer', 'range': '1-32'},
            'max_concurrent_transmissions': {'type': 'integer', 'range': '1-20'},
            'min_search_length': {'type': 'integer', 'range': '1-10'},
            'max_results': {'type': 'integer', 'range': '10-100'},
            'delete_timeout': {'type': 'integer', 'range': '60-3600'},
            'cache_cleanup_days': {'type': 'integer', 'range': '1-90'},
        }
        
        setting_key = setting.lower()
        info = setting_info.get(setting_key, {'type': 'text', 'range': 'any'})
        
        text = (
            f"⚙️ **Edit {setting.replace('_', ' ').title()}**\n\n"
            f"**Type:** {info['type']}\n"
            f"**Valid Range:** {info['range']}\n\n"
            "Please send the new value for this setting.\n"
            "Send /cancel to cancel."
        )
        
        buttons = [[
            InlineKeyboardButton("« Back", callback_data=f"settings_section_{section}")
        ]]
        
        # Initialize user_states if not exists
        if not hasattr(client, 'user_states'):
            client.user_states = {}
            
        # Set user state for setting edit
        client.user_states[callback_query.from_user.id] = {
            'state': 'awaiting_setting',
            'section': section,
            'setting': setting,
            'setting_info': info
        }
        
        await callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        logger.error(f"Error in settings edit handler: {e}")
        await callback_query.answer(
            "Error preparing setting edit. Please try again.",
            show_alert=True
        )


@Client.on_callback_query()
async def handle_callback(client: Client, callback: CallbackQuery):
    """Handle callback queries"""
    try:
        if callback.data.startswith(("admin_", "user_", "banned_", "stats_", "broadcast_", "settings_", "refresh_")):
            if not is_admin_or_owner(callback.from_user.id):
                await callback.answer("You're not authorized!", show_alert=True)
                return
                
            # Handle admin callbacks
            await handle_admin_callbacks(client, callback)
            return

        # Handle file download callback (dl_)
        if not callback.data.startswith("dl_"):
            return
                
            
        short_id = callback.data.split("_")[1]
        status_message = None
        
        try:
            # Send initial status
            status_message = await client.send_message(
                callback.from_user.id,
                "🔄 Processing your request..."
            )
        except Exception as e:
            logger.error(f"Failed to send status message: {e}")
            
            # Modified error handling
            try:
                await callback.answer(
                    "❌ Please start the bot first! Click here to start @Searchkrlobot",
                    show_alert=True
                )
            except Exception as url_error:
                logger.error(f"Error in callback answer: {url_error}")
                # Fallback method
                await client.send_message(
                    callback.from_user.id, 
                    "❌ Please start the bot first! Use @Searchkrlobot"
                )
            return

        # Get file from cache
        file_cache = FileCache(client.db)
        file_id = await file_cache.get_file_id_from_short_id(short_id)
        
        if not file_id:
            await status_message.edit_text("❌ File not found!")
            await callback.answer("File not found in cache", show_alert=True)
            return
            
        # Get cached file info
        cached_file = await file_cache.get_cached_file(file_id)
        if not cached_file:
            await status_message.edit_text("❌ File information not found!")
            await callback.answer("File info missing", show_alert=True)
            return

        success = False
        error_message = None
        
        try:
            # Verify we have the required info
            channel_id = cached_file.get('channel_id')
            message_id = cached_file.get('message_id')
            
            if not channel_id or not message_id:
                logger.error(f"Missing channel_id or message_id. Cached file: {cached_file}")
                error_message = "File source information missing"
                raise ValueError("Missing source information")

            # Step 1: Get original message using userbot
            await status_message.edit_text("🔄 Retrieving file...")
            
            logger.debug(f"Attempting to get message from channel: {channel_id}, message: {message_id}")
            try:
                source_message = await client.user_bot.get_messages(
                    chat_id=int(channel_id),
                    message_ids=int(message_id)
                )
            except Exception as e:
                logger.error(f"Failed to get source message: {e}")
                error_message = "Failed to retrieve source file"
                raise Exception(f"Message retrieval failed: {str(e)}")

            if not source_message:
                error_message = "Source file not found"
                raise Exception("Source message not found")

            # Step 2: Forward to temp channel using userbot
            await status_message.edit_text("🔄 Processing file...")
            
            try:
                # First try copying to temp channel
                temp_msg = await source_message.copy(
                    chat_id=Config.TEMP_CHANNEL,
                    caption=source_message.caption or Messages.FILE_SENT
                )
            except Exception as e:
                logger.error(f"Failed to copy to temp channel: {e}")
                # Try forwarding instead
                temp_msg = await source_message.forward(
                    chat_id=Config.TEMP_CHANNEL
                )

            if not temp_msg:
                error_message = "Failed to process file"
                raise Exception("Failed to forward to temp channel")

            # Small delay to ensure message processing
            await asyncio.sleep(1)

            # Step 3: Bot forwards from temp channel to user
            await status_message.edit_text("🔄 Sending file...")
            
            sent_msg = await client.copy_message(
                chat_id=callback.from_user.id,
                from_chat_id=Config.TEMP_CHANNEL,
                message_id=temp_msg.id,
                caption=temp_msg.caption or Messages.FILE_SENT
            )
            
            if sent_msg:
                success = True
                # Clean up temp message
                try:
                    await temp_msg.delete()
                except Exception as e:
                    logger.error(f"Failed to delete temp message: {e}")

        except ValueError as ve:
            error_message = str(ve)
            logger.error(f"Validation error: {ve}")
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error in file processing: {e}")

        if success:
            # Update user stats
            try:
                user_model = User(client.db)
                await user_model.update_user_stats(
                    callback.from_user.id,
                    download=True
                )
                
                # Update access count
                downloads = cached_file.get('access_count', 0) + 1
                await file_cache.increment_access_count(file_id)
                
                # Delete status message
                await status_message.delete()
                
                await callback.answer(
                    f"✅ File sent successfully! ({downloads} downloads)",
                    show_alert=True
                )
            except Exception as e:
                logger.error(f"Failed to update stats: {e}")
                await callback.answer("File sent but failed to update stats", show_alert=True)
        else:
            error_text = (
                "❌ Failed to send file\n\n"
                f"Error: {error_message}\n"
                "Please try again or contact support."
            )
            await status_message.edit_text(error_text)
            await callback.answer("Failed to send file", show_alert=True)

            # Log the cached file info for debugging
            logger.debug(f"Failed file send debug info:")
            logger.debug(f"Short ID: {short_id}")
            logger.debug(f"File ID: {file_id}")
            logger.debug(f"Cached File Info: {cached_file}")

    except Exception as e:
        logger.error(f"Error in callback: {e}")
        if status_message:
            await status_message.edit_text("❌ An error occurred while processing your request.")
        await callback.answer(
            "❌ An error occurred. Please try again later.",
            show_alert=True
        )

async def handle_admin_callbacks(client: Client, callback: CallbackQuery):
    """Handle all admin-related callbacks"""
    try:
        parts = callback.data.split('_')
        main_type = parts[0]
        
        # First handle admin panel callback
        if callback.data == "admin_panel":
            await admin_panel_callback(client, callback)
            return
            
        # Handle other admin callbacks
        if main_type == "admin":
            action = parts[1]
            if action == "users":
                await admin_users_callback(client, callback)
            elif action == "banned":
                await admin_banned_callback(client, callback)
            elif action == "stats":
                await admin_stats_callback(client, callback)
            elif action == "logs":
                if len(parts) > 2 and parts[2] == "download":
                    await handle_logs_download(client, callback)
                else:
                    await admin_logs_callback(client, callback)
            elif action == "broadcast":
                await admin_broadcast_callback(client, callback)
            elif action == "settings":
                await admin_settings_callback(client, callback)
                
        # Handle settings callbacks
        elif main_type == "settings":
            if parts[1] == "section":
                await handle_settings_section(client, callback)
            elif parts[1] == "edit":
                await handle_settings_edit(client, callback)
                
        # Handle user related callbacks
        elif main_type == "user":
            if parts[1] == "details":
                await handle_user_details(client, callback)
            elif parts[1] == "stats":
                await handle_user_stats(client, callback)
                
        # Handle ban related callbacks
        elif main_type == "banned" or main_type == "unban":
            if parts[1] == "user":
                if main_type == "banned":
                    await handle_banned_user_details(client, callback)
                else:
                    await handle_user_unban(client, callback)
                    
        # Handle refresh callbacks
        elif main_type == "refresh":
            if parts[1] == "channels":
                await refresh_channels_callback(client, callback)
                
    except Exception as e:
        logger.error(f"Error in admin callback handler: {e}")
        await callback.answer(
            "An error occurred. Please try again.",
            show_alert=True
        )
        
async def handle_file_send(client: Client, callback: CallbackQuery):
    """Handle file sending callbacks"""
    try:
        file_id = callback.data.split("_")[1]
        
        # Get file from cache
        file_cache = FileCache(client.db)
        cached_file = await file_cache.get_cached_file(file_id)
        
        try:
            sent_msg = await client.send_document(
                callback.from_user.id,
                file_id,
                caption=Messages.FILE_SENT
            )
            
            # Schedule message deletion
            asyncio.create_task(delete_message_later(sent_msg))
            
            # Update download count in user stats
            user_model = User(client.db)
            await user_model.update_user_stats(
                callback.from_user.id,
                download=True
            )
            
            downloads = cached_file.get('access_count', 0) if cached_file else 0
            await callback.answer(
                f"🗡️ File sent to your DM! ({downloads} downloads)",
                show_alert=True
            )
            
        except errors.FloodWait as e:
            await callback.answer(
                f"⚠️ Please wait {e.value} seconds before trying again!",
                show_alert=True
            )
        except errors.UserIsBlocked:
            try:
                await callback.answer(
                    "❌ Please start the bot first! Click here to start @Searchkrlobot",
                    show_alert=True
                )
            except Exception as url_error:
                logger.error(f"Error in callback answer: {url_error}")
                # Fallback method
                await client.send_message(
                    callback.from_user.id, 
                    "❌ Please start the bot first! Use @Searchkrlobot"
                )
        

        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await callback.answer(
                "❌ Failed to send file. Please try again later!",
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Error in file send callback: {e}")
        await callback.answer(
            "❌ Error processing file. Please try again!",
            show_alert=True
        )
