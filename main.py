import asyncio
from datetime import datetime
import json
import signal
import sys
import os
from getpass import getpass
from aiohttp import web
from bot.shadowfinder import ShadowFinder
from bot.config.config import Config
from loguru import logger
import platform
import uvloop
import pyrogram
from pyrogram import Client
from typing import Optional, Set

# Enable uvloop for better performance on Unix systems
if platform.system() != 'Windows':
    uvloop.install()

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

class BotRunner:
    def __init__(self):
        self.bot: Optional[ShadowFinder] = None
        self._shutdown_trigger: asyncio.Event = asyncio.Event()
        self._running_tasks: Set[asyncio.Task] = set()
        self._http_server_task: Optional[asyncio.Task] = None
        self._setup_logging()

    async def ensure_session(self):
        """Ensure user session exists"""
        if not Config.USER_SESSION_STRING:
            logger.info("No user session found. Starting session generator...")
            return

    def _setup_logging(self) -> None:
        """Configure logging settings"""
        logger.remove()  # Remove default handler
        logger.add(
            "logs/shadowfinder.log",
            rotation="1 day",
            retention="7 days",
            compression="zip",
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        logger.add(sys.stderr, level="INFO")

    async def handle_restart_message(self) -> None:
        """Handle sending confirmation message after restart"""
        try:
            if os.path.exists("restart.json"):
                with open("restart.json", "r") as f:
                    restart_info = json.load(f)
                
                # Remove the restart marker file
                os.remove("restart.json")
                
                # Send confirmation message
                chat_id = restart_info["chat_id"]
                message_id = restart_info["message_id"]
                restart_time = restart_info["time"]
                
                await self.bot.send_edited_message(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="✅ **Bot Restarted Successfully!**\n\n"
                         "• Bot instance restarted\n"
                         "• Configurations reloaded\n"
                         "• All systems operational\n\n"
                         f"⏱️ Restart initiated at: {restart_time}\n"
                         f"⌛️ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                
                # Log the successful restart
                if Config.LOG_CHANNEL:
                    await self.bot.send_message(
                        Config.LOG_CHANNEL,
                        "✅ **Bot Restart Completed**\n"
                        f"⏰ **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
        except Exception as e:
            logger.error(f"Error handling restart message: {e}")

    def _handle_signals(self) -> None:
        """Setup signal handlers"""
        signals = (signal.SIGTERM, signal.SIGINT)
        for sig in signals:
            try:
                asyncio.get_event_loop().add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._shutdown(sig))
                )
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, _: asyncio.create_task(self._shutdown(s)))

    def _create_task(self, coro) -> asyncio.Task:
        """Create and track asyncio tasks"""
        task = asyncio.create_task(coro)
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        return task

    async def start(self) -> None:
        """Start the bot and HTTP server."""
        try:
            # Check and generate session if needed
            await self.ensure_session()

            # Start HTTP server
            self._http_server_task = self._create_task(self.start_http_server())

            # Initialize bot
            self.bot = ShadowFinder()

            # Setup signal handlers
            self._handle_signals()

            # Print startup banner
            self._print_banner()

            # Start the bot
            await self.bot.start()
            
            # Handle restart message if this is a restart
            await self.handle_restart_message()

            # Wait for shutdown signal
            await self._shutdown_trigger.wait()

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            await self._shutdown()
            sys.exit(1)

    async def _shutdown(self, signal: Optional[signal.Signals] = None) -> None:
        """Handle graceful shutdown."""
        if signal:
            logger.info(f"Received signal {signal.name}, initiating shutdown...")

        # Set shutdown trigger
        self._shutdown_trigger.set()

        if self.bot:
            try:
                await self.bot.stop()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")

        # Stop the HTTP server
        await self.stop_http_server()

        # Cancel running tasks
        tasks = [t for t in self._running_tasks if not t.done()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} running tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Stop the event loop
        loop = asyncio.get_running_loop()
        
        # Check if this is a restart
        if os.environ.get('BOT_RESTARTING'):
            logger.info("Shutdown triggered by restart command")
        else:
            loop.stop()

    async def start_http_server(self) -> None:
        """Start a lightweight HTTP server for health checks."""
        async def health_check(request):
            return web.Response(text="OK")

        app = web.Application()
        app.router.add_get("/", health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8000)
        await site.start()
        logger.info("HTTP server for health checks started on port 8000.")

    async def stop_http_server(self) -> None:
        """Stop the HTTP server."""
        if self._http_server_task:
            self._http_server_task.cancel()
            try:
                await self._http_server_task
            except asyncio.CancelledError:
                pass
            logger.info("HTTP server stopped.")

    def _print_banner(self) -> None:
        """Print startup banner"""
        banner = f"""
╔══════════════════════════════════════════╗
║         ShadowFinder Bot v{Config.VERSION}         ║
╠══════════════════════════════════════════╣
║  "I alone level up..."                   ║
║  - Solo Leveling                         ║
╚══════════════════════════════════════════╝
        """
        print(banner)
        logger.info("Starting ShadowFinder Bot...")

    def run(self) -> None:
        """Run the bot"""
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the bot
            loop.run_until_complete(self.start())

        except KeyboardInterrupt:
            logger.warning("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            sys.exit(1)
        finally:
            try:
                logger.info("Cleaning up...")
                loop.run_until_complete(self._shutdown())
                loop.close()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                sys.exit(1)

def main() -> None:
    """Main entry point"""
    try:
        # Check Python version
        if sys.version_info < (3, 7):
            sys.exit("Python 3.7 or higher is required.")

        # Run the bot
        runner = BotRunner()
        runner.run()

    except KeyboardInterrupt:
        print("\nBot stopped by user!")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
