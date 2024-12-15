# bot/handlers/admin.py
import json 
import os
import sys
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from ..database import Database, User, FileCache
from ..templates.messages import Messages
from ..config.config import Config
from datetime import datetime
import asyncio
from ..helpers.decorators import force_subscribe
from loguru import logger
from motor.motor_asyncio import  AsyncIOMotorDatabase

db = Database()
user_model = User(db.db)
file_cache = FileCache(db.db)

def is_admin_or_owner(user_id: int) -> bool:
    """Check if user is admin or owner"""
    return user_id == Config.OWNER_ID or user_id in Config.ADMIN_IDS

async def get_bot_stats(db: AsyncIOMotorDatabase):
    """Get overall bot statistics"""
    user_model = User(db)
    file_cache = FileCache(db)
    
    total_users = await user_model.collection.count_documents({})
    banned_users = await user_model.collection.count_documents({'banned': True})
    total_files = await file_cache.collection.count_documents({})
    
    total_downloads = await file_cache.collection.aggregate([
        {'$group': {'_id': None, 'total': {'$sum': '$access_count'}}}
    ]).to_list(1)
    
    return {
        'total_users': total_users,
        'banned_users': banned_users,
        'total_files': total_files,
        'total_downloads': total_downloads[0]['total'] if total_downloads else 0
    }


# Admin Commands
@Client.on_message(filters.command(["admin", "panel"]) & filters.private)
async def admin_panel(client: Client, message: Message):
    """Admin panel command"""
    if not is_admin_or_owner(message.from_user.id):
        await message.reply_text(Messages.NOT_AUTHORIZED)
        return
    
    stats = await get_bot_stats(client.db)  # Pass the database instance
    
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
        ]
    ]
    
    await message.reply_text(
        f"⚔️ **Shadow Monarch's Admin Panel** ⚔️\n\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"🚫 Banned Users: {stats['banned_users']}\n"
        f"📁 Cached Files: {stats['total_files']}\n"
        f"📥 Total Downloads: {stats['total_downloads']}\n",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_message(filters.command(["ban"]) & filters.group)
async def ban_user(client: Client, message: Message):
    """Ban user command"""
    if not is_admin_or_owner(message.from_user.id):
        await message.reply_text(Messages.NOT_AUTHORIZED)
        return

    if len(message.command) < 2:
        await message.reply_text(
            "⚠️ **Usage**:\n"
            "/ban user_id/username reason\n"
            "or reply to user's message with /ban reason"
        )
        return

    try:
        # Get user to ban
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            reason = ' '.join(message.command[1:]) if len(message.command) > 1 else "No reason provided"
        else:
            user_id = (
                int(message.command[1]) if message.command[1].isdigit()
                else (await client.get_users(message.command[1])).id
            )
            reason = ' '.join(message.command[2:]) if len(message.command) > 2 else "No reason provided"

        # Check if user exists and is not admin
        if user_id in Config.ADMIN_IDS or user_id == Config.OWNER_ID:
            await message.reply_text("⚠️ Cannot ban an admin!")
            return

        user_data = await user_model.get_user(user_id)
        if not user_data:
            await message.reply_text(Messages.USER_NOT_FOUND)
            return

        if user_data.get('banned', True):
            await message.reply_text(Messages.USER_ALREADY_BANNED)
            return

        # Ban user
        ban_data = {
            "banned": True,
            "ban_reason": reason,
            "banned_by": message.from_user.id,
            "ban_date": datetime.now()
        }
        await user_model.ban_user(user_id, ban_data)
        
        user = await client.get_users(user_id)
        
        # Log the ban
        log_text = f"""
🚫 **User Banned**
👤 **User**: {user.mention} [`{user.id}`]
👮 **Admin**: {message.from_user.mention}
📝 **Reason**: {reason}
⏰ **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if Config.LOG_CHANNEL:
            await client.send_message(Config.LOG_CHANNEL, log_text)
        
        await message.reply_text(
            Messages.BANNED_USER.format(
                mention=user.mention,
                user_id=user_id,
                admin_mention=message.from_user.mention,
                reason=reason
            )
        )
        
        # Notify user
        try:
            await client.send_message(
                user_id,
                f"⚠️ You have been banned from using ShadowFinder!\n"
                f"📝 **Reason**: {reason}\n"
                f"👮 **Admin**: {message.from_user.mention}"
            )
        except Exception:
            pass

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@Client.on_message(filters.command(["unban"]) & filters.group)
async def unban_user(client: Client, message: Message):
    """Unban user command"""
    if not is_admin_or_owner(message.from_user.id):
        await message.reply_text(Messages.NOT_AUTHORIZED)
        return

    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Usage**:\n"
            "/unban user_id/username\n"
            "or reply to user's message with /unban"
        )
        return

    try:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
        else:
            user_id = (
                int(message.command[1]) if message.command[1].isdigit()
                else (await client.get_users(message.command[1])).id
            )

        user_data = await user_model.get_user(user_id)
        if not user_data:
            await message.reply_text(Messages.USER_NOT_FOUND)
            return

        if not user_data.get('banned', False):
            await message.reply_text(Messages.USER_NOT_BANNED)
            return

        # Unban user
        await user_model.ban_user(user_id, {"banned": False})
        
        user = await client.get_users(user_id)
        
        # Log the unban
        log_text = f"""
✅ **User Unbanned**
👤 **User**: {user.mention} [`{user.id}`]
👮 **Admin**: {message.from_user.mention}
⏰ **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if Config.LOG_CHANNEL:
            await client.send_message(Config.LOG_CHANNEL, log_text)
        
        await message.reply_text(
            Messages.UNBANNED_USER.format(
                mention=user.mention,
                user_id=user_id,
                admin_mention=message.from_user.mention
            )
        )
        
        # Notify user
        try:
            await client.send_message(
                user_id,
                f"✨ You have been unbanned from ShadowFinder!\n"
                f"👮 **Unbanned by**: {message.from_user.mention}\n"
                f"You can now use the bot again."
            )
        except Exception:
            pass

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")



@Client.on_message(filters.command(["addadmin"]) & filters.user(Config.OWNER_ID))
async def add_admin(client: Client, message: Message):
    """Command to add a new admin"""
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Usage**:\n"
            "/addadmin user_id/username\n"
            "or reply to user's message with /addadmin"
        )
        return

    try:
        # Get user to add as admin
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
        else:
            user_id = (
                int(message.command[1]) if message.command[1].isdigit()
                else (await client.get_users(message.command[1])).id
            )

        # Check if user is already an admin
        if user_id in Config.ADMIN_IDS or user_id == Config.OWNER_ID:
            await message.reply_text("⚠️ User is already an admin!")
            return

        # Get user details
        user = await client.get_users(user_id)

        # Update admin list 
        # Note: This is a runtime update. You'll need to modify your config file 
        # or have a mechanism to persist these changes between bot restarts
        Config.ADMIN_IDS.append(user_id)

        # Log the admin addition
        log_text = f"""
🆕 **New Admin Added**
👤 **Admin**: {user.mention} [`{user.id}`]
👮 **Added by**: {message.from_user.mention}
⏰ **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if Config.LOG_CHANNEL:
            await client.send_message(Config.LOG_CHANNEL, log_text)
        
        await message.reply_text(
            f"✅ **{user.mention}** has been added as an admin!\n"
            f"👤 User ID: `{user_id}`"
        )
        
        # Notify the new admin
        try:
            await client.send_message(
                user_id,
                f"🎉 Congratulations! You have been promoted to admin in ShadowFinder!\n"
                f"👮 **Promoted by**: {message.from_user.mention}"
            )
        except Exception:
            pass

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@Client.on_message(filters.command(["addchannel", "addgroup"]) & filters.private)
async def add_authorized_channel(client: Client, message: Message):
    """Command to add a channel or group to authorized lists"""
    if not is_admin_or_owner(message.from_user.id):
        await message.reply_text(Messages.NOT_AUTHORIZED)
        return

    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text(
            "⚠️ **Usage**:\n"
            "/addchannel channel_id/username\n"
            "/addgroup group_id/username\n"
            "or forward a message and reply with the command"
        )
        return

    try:
        # Get channel/group ID
        if message.reply_to_message and message.reply_to_message.forward_from_chat:
            chat_id = message.reply_to_message.forward_from_chat.id
        else:
            # Try to get chat ID from username or ID
            input_chat = message.command[1]
            try:
                chat = await client.get_chat(input_chat)
                chat_id = chat.id
            except Exception as e:
                await message.reply_text(f"❌ Error getting chat: {str(e)}")
                return

        # Determine chat type
        chat = await client.get_chat(chat_id)
        is_channel = chat.type in [enums.ChatType.CHANNEL]
        is_group = chat.type in [enums.ChatType.SUPERGROUP, enums.ChatType.GROUP]

        # Validate chat type based on command
        if message.command[0].lower() == 'addchannel' and not is_channel:
            await message.reply_text("❌ This is not a channel!")
            return
        
        if message.command[0].lower() == 'addgroup' and not is_group:
            await message.reply_text("❌ This is not a group!")
            return

        # Determine which list to add to
        if is_channel:
            if chat_id in Config.SEARCH_CHANNELS:
                await message.reply_text("⚠️ Channel already in search channels!")
                return
            Config.SEARCH_CHANNELS.append(chat_id)
            list_name = "Search Channels"
        else:
            if chat_id in Config.AUTHORIZED_GROUPS:
                await message.reply_text("⚠️ Group already in authorized groups!")
                return
            Config.AUTHORIZED_GROUPS.append(chat_id)
            list_name = "Authorized Groups"

        # Log the addition
        log_text = f"""
🆕 **{list_name} Added**
📍 **Chat**: {chat.title} [`{chat_id}`]
👮 **Added by**: {message.from_user.mention}
⏰ **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if Config.LOG_CHANNEL:
            await client.send_message(Config.LOG_CHANNEL, log_text)
        
        await message.reply_text(
            f"✅ **{chat.title}** has been added to {list_name}!\n"
            f"👥 Chat ID: `{chat_id}`\n\n"
            "⚠️ Note: This is a runtime update. Persist changes in your config file."
        )

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")


@Client.on_message(filters.command(["broadcast"]) & filters.user(Config.OWNER_ID))
async def broadcast(client: Client, message: Message):
    """Broadcast message to all users"""
    if len(message.command) < 2:
        await message.reply_text(
            "⚠️ **Usage**:\n"
            "/broadcast message\n"
            "or reply to a message with /broadcast"
        )
        return

    status_msg = await message.reply_text(Messages.BROADCAST_STARTED)
    
    broadcast_msg = (
        message.text.split(None, 1)[1]
        if len(message.command) > 1
        else message.reply_to_message.text
    )

    total_users = 0
    success = 0
    failed = 0
    
    async with asyncio.Lock():
        async for user in db.users.find({'banned': False}):
            total_users += 1
            try:
                await client.send_message(
                    user['user_id'],
                    f"📢 **Broadcast Message**\n\n{broadcast_msg}"
                )
                success += 1
                await asyncio.sleep(0.1)  # Prevent flooding
            except Exception:
                failed += 1

            if total_users % 20 == 0:  # Update status every 20 users
                await status_msg.edit_text(
                    f"🔄 Broadcasting...\n"
                    f"👥 Progress: {total_users}\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}"
                )

    await status_msg.edit_text(
        Messages.BROADCAST_DONE.format(
            total=total_users,
            success=success,
            failed=failed
        )
    )

@Client.on_message(filters.command(["restart"]) & filters.private)
async def restart_bot(client: Client, message: Message):
    """Restart the bot and reload configurations"""
    if not is_admin_or_owner(message.from_user.id):
        await message.reply_text(Messages.NOT_AUTHORIZED)
        return

    restart_msg = await message.reply_text("🔄 Restarting bot and reloading configurations...")

    try:
        # Log the restart
        log_text = f"""
🔄 **Bot Restart Initiated**
👤 **Triggered By**: {message.from_user.mention}
⏰ **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        if Config.LOG_CHANNEL:
            await client.send_message(Config.LOG_CHANNEL, log_text)

        # Update the restart message
        await restart_msg.edit_text(
            "🔄 **Bot is restarting**\n\n"
            "• Stopping current instance...\n"
            "• Reloading configurations...\n"
            "• Starting new instance...\n\n"
            "⏳ Please wait 10-15 seconds..."
        )

        # Save restart message info
        restart_info = {
            "chat_id": message.chat.id,
            "message_id": restart_msg.id,
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Save restart info to file
        with open("restart.json", "w") as f:
            json.dump(restart_info, f)

        # Trigger graceful shutdown with restart flag
        os.environ['BOT_RESTARTING'] = '1'
        
        # Stop the client gracefully
        await client.stop()
        
        # Execute the restart
        if sys.platform.startswith('win'):
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    except Exception as e:
        logger.error(f"Error during restart: {e}")
        await restart_msg.edit_text(f"❌ **Error during restart**\n\n`{str(e)}`")


@Client.on_message(filters.command(["channels"]) & filters.private)
async def list_channels(client: Client, message: Message):
    """List all channels configured for file search"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            await message.reply_text(Messages.NOT_AUTHORIZED)
            return

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

        # Add total count footer
        channels_text += f"\n**Total Configured Channels**: `{len(Config.SEARCH_CHANNELS)}`"
        
        # Add refresh button
        buttons = [[
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_channels")
        ]]
        
        await message.reply_text(
            channels_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Error in channels command: {e}")
        await message.reply_text("❌ Error fetching channels list!")



@Client.on_message(filters.command(["stats"]) & filters.private)
@force_subscribe
async def user_stats(client: Client, message: Message):
    """Get user statistics"""
    # Initialize database and models
    db_instance = Database()
    user_model = User(db_instance.db)
    
    user_data = await user_model.get_user(message.from_user.id)
    if not user_data:
        await message.reply_text(Messages.USER_NOT_FOUND)
        return

    if is_admin_or_owner(message.from_user.id):
        stats = await get_bot_stats(client.db)
        admin_stats = f"\n\n👑 **Admin Statistics**\n" \
                     f"👥 Total Users: {stats['total_users']}\n" \
                     f"🚫 Banned Users: {stats['banned_users']}\n" \
                     f"📁 Cached Files: {stats['total_files']}\n" \
                     f"📥 Total Downloads: {stats['total_downloads']}"
    else:
        admin_stats = ""

    await message.reply_text(
        Messages.USER_STATS.format(
            mention=message.from_user.mention,
            user_id=message.from_user.id,
            joined_date=user_data['joined_date'].strftime("%Y-%m-%d %H:%M:%S"),
            searches=user_data.get('searches', 0),
            downloads=user_data.get('downloads', 0),
            last_active=user_data['last_used'].strftime("%Y-%m-%d %H:%M:%S")
        ) + admin_stats
    )
    
    # Close database connection when done
    await db_instance.close()

@Client.on_message(filters.command(["checkid"]) & (filters.private | filters.group))
async def check_id(client: Client, message: Message):
    """Debug command to check channel/group IDs"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            await message.reply_text("⚔️ Only admins can use this command!")
            return

        # Get chat info based on context
        if str(message.chat.id).startswith('-100'):  # Group/Channel
            chat = message.chat
        elif message.reply_to_message and message.reply_to_message.forward_from_chat:
            chat = message.reply_to_message.forward_from_chat
        else:
            await message.reply_text(
                "⚠️ **Usage**: \n"
                "• In groups: Just send `/checkid` to check group info\n"
                "• For channels: Forward a message from the channel and reply with `/checkid`"
            )
            return
        
        try:
            bot_member = await client.get_chat_member(chat.id, (await client.get_me()).id)
            member_count = await client.get_chat_members_count(chat.id)
            
            # Check chat type
            chat_type = (
                "Channel" if str(chat.id).startswith('-100') and (
                    getattr(chat, 'type', None) == 'channel' or 
                    getattr(chat, 'type', None) == 'supergroup'
                ) else "Group"
            )
            
            permissions = []
            if hasattr(bot_member, 'privileges') and bot_member.privileges:
                if bot_member.privileges.can_delete_messages:
                    permissions.append("Delete Messages ✅")
                if bot_member.privileges.can_manage_chat:
                    permissions.append("Manage Chat ✅")
                if bot_member.privileges.can_restrict_members:
                    permissions.append("Restrict Members ✅")
                if bot_member.privileges.can_promote_members:
                    permissions.append("Promote Members ✅")
                if bot_member.privileges.can_invite_users:
                    permissions.append("Invite Users ✅")
                if bot_member.privileges.can_pin_messages:
                    permissions.append("Pin Messages ✅")
            
            is_search_channel = chat.id in Config.SEARCH_CHANNELS
            is_auth_group = chat.id in Config.AUTHORIZED_GROUPS
            
            info_text = (
                f"📊 **Chat Information**\n\n"
                f"**Title**: {chat.title}\n"
                f"**ID**: `{chat.id}`\n"
                f"**Type**: {chat_type}\n"
                f"**Members**: {member_count}\n"
                f"**Username**: @{chat.username or 'private'}\n"
                f"**Search Channel**: {'Yes ✅' if is_search_channel else 'No ❌'}\n"
                f"**Authorized Group**: {'Yes ✅' if is_auth_group else 'No ❌'}\n\n"
                f"**Bot Permissions**:\n"
                f"• Admin: {'Yes ✅' if hasattr(bot_member, 'privileges') and bot_member.privileges else 'No ❌'}\n"
            )
            
            if permissions:
                info_text += "• " + "\n• ".join(permissions)
            
            config_text = []
            if not is_search_channel and chat_type == "Channel":
                config_text.append("Add to SEARCH_CHANNELS to enable search")
            if not is_auth_group and chat_type == "Group":
                config_text.append("Add to AUTHORIZED_GROUPS to enable bot usage")
            
            if config_text:
                info_text += "\n\n⚠️ **Required Actions**:\n• " + "\n• ".join(config_text)
            
            # Add configuration help
            if config_text:
                info_text += "\n\n📝 **Add to config**:\n"
                if not is_search_channel and chat_type == "Channel":
                    info_text += f"SEARCH_CHANNELS=....,{chat.id}\n"
                if not is_auth_group and chat_type == "Group":
                    info_text += f"AUTHORIZED_GROUPS=....,{chat.id}\n"
            
            await message.reply_text(info_text)
            
        except Exception as e:
            await message.reply_text(
                f"❌ **Error checking chat**\n\n"
                f"Chat ID: `{chat.id}`\n"
                f"Error: `{str(e)}`\n\n"
                f"Make sure bot is member of the chat!"
            )

    except Exception as e:
        logger.error(f"Error in checkid command: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")

@Client.on_message(filters.command(["checkconfig"]) & filters.private)
async def check_config(client: Client, message: Message):
    """Check bot configuration"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            await message.reply_text("⚔️ Only admins can use this command!")
            return

        config_text = "📝 **Bot Configuration**\n\n"
        
        # Check Authorized Groups
        config_text += "🛡️ **Authorized Groups**:\n"
        for group_id in Config.AUTHORIZED_GROUPS:
            try:
                chat = await client.get_chat(group_id)
                config_text += f"✅ {chat.title} (`{group_id}`)\n"
            except Exception as e:
                config_text += f"❌ Error with ID {group_id}: {str(e)}\n"
        
        # Check Search Channels
        config_text += "\n🔍 **Search Channels**:\n"
        for channel_id in Config.SEARCH_CHANNELS:
            try:
                chat = await client.get_chat(channel_id)
                config_text += f"✅ {chat.title} (`{channel_id}`)\n"
            except Exception as e:
                config_text += f"❌ Error with ID {channel_id}: {str(e)}\n"
        
        # Check Force Sub Channel
        if Config.FORCE_SUB_CHANNEL:
            config_text += "\n📢 **Force Sub Channel**:\n"
            try:
                chat = await client.get_chat(Config.FORCE_SUB_CHANNEL)
                config_text += f"✅ {chat.title} (`{Config.FORCE_SUB_CHANNEL}`)\n"
            except Exception as e:
                config_text += f"❌ Error: {str(e)}\n"

        await message.reply_text(config_text)
        
    except Exception as e:
        logger.error(f"Error in config check: {e}")
        await message.reply_text(f"❌ Error checking config: {str(e)}")

@Client.on_message(filters.private & filters.regex(r'^[^/]'))
async def handle_setting_value(client: Client, message: Message):
    """Handle incoming setting values"""
    try:
        # Check if user has a pending setting edit
        if not hasattr(client, 'user_states'):
            client.user_states = {}
            
        user_state = client.user_states.get(message.from_user.id)
        if not user_state or user_state.get('state') != 'awaiting_setting':
            return
            
        section = user_state['section']
        setting = user_state['setting']
        value = message.text.strip()
        
        # Validate and update setting
        success = await update_bot_setting(client, section, setting, value)
        
        if success:
            await message.reply_text(
                f"✅ Setting `{setting}` updated successfully!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "Back to Settings",
                        callback_data=f"settings_section_{section}"
                    )
                ]])
            )
        else:
            await message.reply_text(
                "❌ Failed to update setting. Please check the value and try again.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "Try Again",
                        callback_data=f"settings_edit_{section}_{setting}"
                    )
                ]])
            )
            
        # Clear user state
        client.user_states.pop(message.from_user.id, None)
        
    except Exception as e:
        logger.error(f"Error handling setting value: {e}")
        await message.reply_text("❌ An error occurred while updating the setting.")

async def update_bot_setting(client: Client, section: str, setting: str, value: str) -> bool:
    """Update bot setting"""
    try:
        setting_key = setting.upper()
        if not hasattr(Config, setting_key):
            return False
            
        # Validate value based on setting type
        current_value = getattr(Config, setting_key)
        if isinstance(current_value, int):
            try:
                value = int(value)
            except ValueError:
                return False
        elif isinstance(current_value, bool):
            value = value.lower() in ['true', '1', 'yes']
            
        # Update config
        setattr(Config, setting_key, value)
        
        # Save to database if needed
        if client.db:
            await client.db.settings.update_one(
                {'key': setting_key},
                {'$set': {'value': value}},
                upsert=True
            )
            
        return True
        
    except Exception as e:
        logger.error(f"Error updating setting: {e}")
        return False


