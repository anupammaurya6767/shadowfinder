# main.py
import asyncio
import signal
import sys
import os
from getpass import getpass
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

    async def _shutdown(self, signal: Optional[signal.Signals] = None) -> None:
        """Handle graceful shutdown"""
        if signal:
            logger.info(f"Received signal {signal.name}, initiating shutdown...")

        # Set shutdown trigger
        self._shutdown_trigger.set()

        if self.bot:
            try:
                await self.bot.stop()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")

        # Cancel running tasks
        tasks = [t for t in self._running_tasks if not t.done()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} running tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Stop the event loop
        loop = asyncio.get_running_loop()
        loop.stop()

    async def start(self) -> None:
        """Start the bot"""
        try:
            # Check and generate session if needed
            await self.ensure_session()
            
            # Initialize bot
            self.bot = ShadowFinder()
            
            # Setup signal handlers
            self._handle_signals()
            
            # Print startup banner
            self._print_banner()
            
            # Start the bot
            await self.bot.start()
            
            # Wait for shutdown signal
            await self._shutdown_trigger.wait()
            
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            await self._shutdown()
            sys.exit(1)

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
