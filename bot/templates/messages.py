# bot/templates/messages.py
class Messages:
    START = """
🗡️ **Welcome to ShadowFinder** 🗡️

I am your **Shadow Monarch's Messenger**, here to assist you in finding hidden treasures across the dungeons of Telegram.

⚔️ **Commands**:
• `/start` - Awaken the Shadow Monarch
• `/help` - Learn the ways of hunting
• `/about` - Discover my origins
• `/stats` - View your hunting records

🔮 **To search**: Simply summon me in any authorized guild (group) using inline mode.

⚡️ **I alone level up...** ⚡️
"""

    HELP = """
📜 **Shadow Monarch's Guide** 📜

🔍 **Search Commands**:
• Use me in inline mode: `@{username} <query>`
• Minimum 3 characters required

⚔️ **Admin Commands**:
• `/ban` - Banish a user (Admin only)
• `/unban` - Restore a user (Admin only)
• `/broadcast` - Send message to all users (Owner only)

⚠️ **Important Notes**:
• Files self-destruct after 10 minutes
• Save important files to Saved Messages
• Bot works only in authorized groups

💫 **Rise, my shadows...** 💫
"""

    ABOUT = """
🏰 **About ShadowFinder** 🏰

A mystical artifact created by the Shadow Monarch to help hunters find their desired treasures.

⚜️ **Features**:
• Swift inline search
• Automatic file cleanup
• Secure file delivery

👑 **Creator**: **{owner_name}**
⚡️ **Version**: `{version}`
🌟 **Users**: `{total_users}`

🌟 **I shall never fall...** 🌟
"""

    # Add these new messages
    FORCE_SUB = """
⚠️ **Access Denied!**

You must join the Shadow Monarch's guild before you can use my powers.
Join the channel and try again.
"""

    NOT_AUTHORIZED = """
⚔️ **Unauthorized Access!**

This power can only be wielded in authorized guilds.
Join an authorized group to use my abilities.
"""

    FILE_SENT = """
📤 **File Summoned Successfully!**

⏳ This message will self-destruct in 10 minutes.
💾 Save the file to your Saved Messages if needed.
"""

    # Admin Messages
    BANNED_USER = """
⚔️ **Shadow Monarch's Judgment** ⚔️

User has been banished from the realm!

👤 **User**: {mention}
🆔 **ID**: `{user_id}`
⚡️ **By Admin**: {admin_mention}
📝 **Reason**: {reason}
"""

    UNBANNED_USER = """
✨ **Shadow Monarch's Mercy** ✨

User has been restored to the realm!

👤 **User**: {mention}
🆔 **ID**: `{user_id}`
⚡️ **By Admin**: {admin_mention}
"""

    # Error Messages
    USER_ALREADY_BANNED = "⚠️ This user is already banished from the realm!"
    USER_NOT_BANNED = "⚠️ This user is not banished!"
    USER_NOT_FOUND = "❌ User not found in the database!"
    NOT_AUTHORIZED = "⚔️ You don't have the authority to use this power!"

    # Stats Message
    USER_STATS = """
📊 **Your Shadow Statistics** 📊

👤 **User**: {mention}
🆔 **ID**: `{user_id}`
📅 **Joined**: {joined_date}
🔍 **Total Searches**: {searches}
📥 **Total Downloads**: {downloads}
⚡️ **Last Active**: {last_active}
"""


    BROADCAST_START = "📢 Starting broadcast..."
    BROADCAST_PROGRESS = "🔄 Broadcasting...\n✅ Success: {}\n❌ Failed: {}"
    BROADCAST_COMPLETE = "📢 **Broadcast Completed**\n\n✅ Success: {}\n❌ Failed: {}\n💠 Total: {}"

    SETTINGS_UPDATED = "✅ Settings updated successfully!"
    SETTINGS_ERROR = "❌ Error updating settings: {}"