from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from ..templates.messages import Messages
from ..helpers.decorators import force_subscribe
from ..config.config import Config
from loguru import logger
import os
from typing import Any
from dotenv import load_dotenv, find_dotenv

def is_admin_or_owner(user_id: int) -> bool:
    """Check if user is admin or owner"""
    return user_id == Config.OWNER_ID or user_id in Config.ADMIN_IDS

async def update_env_setting(setting: str, value: Any) -> bool:
    """Update setting in .env file"""
    try:
        env_file = find_dotenv()
        if not env_file:
            logger.error("Could not find .env file")
            return False
            
        # Read the current .env content
        with open(env_file, 'r') as file:
            lines = file.readlines()
            
        # Update the specific setting
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f'{setting}='):
                lines[i] = f'{setting}={value}\n'
                updated = True
                break
                
        if not updated:
            lines.append(f'{setting}={value}\n')
            
        # Write back to .env file
        with open(env_file, 'w') as file:
            file.writelines(lines)
            
        # Update Config
        setattr(Config, setting, value)
        
        # Reload environment variables
        load_dotenv()
        
        return True
    except Exception as e:
        logger.error(f"Error updating env file: {e}")
        return False

async def handle_setting_value(client: Client, message: Message):
    """Handle setting value updates"""
    try:
        user_state = client.user_states.get(message.from_user.id)
        if not user_state or user_state.get('state') != 'awaiting_setting':
            return

        section = user_state['section']
        setting = user_state['setting']
        value = message.text.strip()

        # Validation rules based on setting
        setting_rules = {
            'WORKERS': {'type': 'int', 'min': 1, 'max': 32},
            'MAX_CONCURRENT_TRANSMISSIONS': {'type': 'int', 'min': 1, 'max': 20},
            'MIN_SEARCH_LENGTH': {'type': 'int', 'min': 1, 'max': 10},
            'MAX_RESULTS': {'type': 'int', 'min': 10, 'max': 100},
            'DELETE_TIMEOUT': {'type': 'int', 'min': 60, 'max': 3600},
            'CACHE_CLEANUP_DAYS': {'type': 'int', 'min': 1, 'max': 90},
            'MAX_CACHE_SIZE': {'type': 'int', 'min': 1000, 'max': 100000},
            'FORCE_SUB_CHANNEL': {'type': 'channel_id'},
            'LOG_CHANNEL': {'type': 'channel_id'},
            'SEARCH_CHANNELS': {'type': 'channel_list'},
            'AUTHORIZED_GROUPS': {'type': 'channel_list'},
            'ADMIN_IDS': {'type': 'id_list'},
            'FORCE_SUB_ENABLED': {'type': 'bool'},
            'VERSION': {'type': 'string'},
        }

        # Get validation rules for this setting
        rules = setting_rules.get(setting.upper(), {'type': 'string'})
        valid = True
        error_message = None
        converted_value = value

        # Validate based on type
        try:
            if rules['type'] == 'int':
                converted_value = int(value)
                if converted_value < rules['min'] or converted_value > rules['max']:
                    valid = False
                    error_message = f"Value must be between {rules['min']} and {rules['max']}"
                    
            elif rules['type'] == 'channel_id':
                if value.lower() not in ['none', 'false']:
                    try:
                        converted_value = int(value)
                    except ValueError:
                        valid = False
                        error_message = "Please enter a valid channel ID or 'none'"
                        
            elif rules['type'] == 'channel_list':
                # Validate comma-separated channel IDs
                try:
                    if value.lower() != 'none':
                        ids = [int(x.strip()) for x in value.split(',')]
                        converted_value = ','.join(map(str, ids))
                except ValueError:
                    valid = False
                    error_message = "Please enter valid channel IDs separated by commas"
                    
            elif rules['type'] == 'id_list':
                # Validate comma-separated user IDs
                try:
                    ids = [int(x.strip()) for x in value.split(',')]
                    converted_value = ','.join(map(str, ids))
                except ValueError:
                    valid = False
                    error_message = "Please enter valid user IDs separated by commas"
                    
            elif rules['type'] == 'bool':
                converted_value = str(value.lower() in ['true', '1', 'yes']).lower()

        except ValueError:
            valid = False
            error_message = f"Invalid value for {rules['type']} type"

        if valid:
            success = await update_env_setting(setting.upper(), converted_value)
            
            if success:
                await message.reply_text(
                    f"✅ Setting `{setting}` updated to `{converted_value}`!\n"
                    "Note: Restart bot to apply changes.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "Back to Settings",
                            callback_data=f"settings_section_{section}"
                        )
                    ]])
                )
            else:
                await message.reply_text(
                    "❌ Failed to update setting in .env file.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "Try Again",
                            callback_data=f"settings_edit_{section}_{setting}"
                        )
                    ]])
                )
        else:
            await message.reply_text(
                f"❌ Invalid value: {error_message}",
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
        await message.reply_text(
            "❌ An error occurred while updating the setting.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Back to Settings",
                    callback_data="admin_settings"
                )
            ]])
        )

@Client.on_message(filters.private & ~filters.command(["start", "help", "about", "stats", "admin", "cancel"]))
@force_subscribe
async def handle_private_messages(client: Client, message: Message):
    """Handle private messages that are not commands"""
    try:
        # Check if user is admin and has pending setting edit
        if is_admin_or_owner(message.from_user.id):
            if hasattr(client, 'user_states'):
                user_state = client.user_states.get(message.from_user.id)
                if user_state and user_state.get('state') == 'awaiting_setting':
                    await handle_setting_value(client, message)
                    return

        # Default message for non-admin users
        buttons = [[
            InlineKeyboardButton("⚔️ Use in Groups ⚔️", switch_inline_query="")
        ]]
        await message.reply_text(
            "⚔️ *I only serve in authorized guilds!* Use me in inline mode in allowed groups.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error handling private message: {e}")
        await message.reply_text(
            "❌ An error occurred while processing your message."
        )

@Client.on_message(filters.private & filters.command("cancel"))
async def handle_cancel(client: Client, message: Message):
    """Handle cancel command"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            return
            
        if hasattr(client, 'user_states'):
            if client.user_states.pop(message.from_user.id, None):
                await message.reply_text(
                    "✅ Operation cancelled.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_panel")
                    ]])
                )
                return
                
        await message.reply_text("❌ No active operation to cancel.")
        
    except Exception as e:
        logger.error(f"Error handling cancel command: {e}")
        await message.reply_text("❌ An error occurred while canceling the operation.")