"""
Batch processing script for multiple video files.

This script watches the inbox/ directory and processes all video files,
or processes a list of files provided as arguments.

Usage:
    # Process all videos in inbox/
    python batch_process.py

    # Process specific files
    python batch_process.py video1.mkv video2.mkv video3.mkv

    # Watch inbox/ directory continuously
    python batch_process.py --watch

    # Process with custom settings
    python batch_process.py --profile prod --no-llm
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List

from core.runtime.config import Config, set_config
from core.runtime.orchestrator import run_generate
from main import setup_logging
from core.media import inspect_media

logger = logging.getLogger(__name__)


def get_video_files(directory: str) -> List[Path]:
    """
    Get all video files from a directory.
    
    Args:
        directory: Path to directory
        
    Returns:
        List of video file paths
    """
    directory = Path(directory)
    if not directory.exists():
        return []
    
    # Common video extensions
    video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm'}
    
    # Collect all video files with supported extensions
    video_files = [f for ext in video_extensions for f in directory.glob(f'*{ext}')]
    
    return sorted(video_files)


def process_batch(
    video_files: List[Path],
    config: Config,
    no_llm: bool = False,
    no_mux: bool = False,
    skip_existing: bool = True
) -> dict:
    """
    Process a batch of video files.
    
    Args:
        video_files: List of video file paths
        config: Configuration object
        no_llm: Skip LLM polishing
        no_mux: Skip video muxing
        skip_existing: Skip files that already have SRT output
        
    Returns:
        Dictionary with processing statistics
    """
    stats = {
        "total": len(video_files),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    outbox_dir = Path(config.get_path("outbox"))
    
    for i, video_path in enumerate(video_files, 1):
        logger.info(f"\n{'='*70}")
        logger.info(f"File {i}/{len(video_files)}: {video_path.name}")
        logger.info(f"{'='*70}")
        
        # Check if already processed
        srt_path = outbox_dir / f"{video_path.stem}.en.srt"
        if skip_existing and srt_path.exists():
            logger.info(f"⊘ Skipping (SRT already exists): {srt_path.name}")
            stats["skipped"] += 1
            continue
        
        # Process video
        try:
            meta = run_generate(
                inspect_media(str(video_path)),
                config,
                no_llm=no_llm,
            )

            stats["processed"] += 1
            logger.info(f"✓ Success: {video_path.name} ({meta['strategy']})")
        
        except KeyboardInterrupt:
            logger.info("\n⚠ Interrupted by user")
            break
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append({
                "file": video_path.name,
                "error": str(e)
            })
            logger.error(f"✗ Error processing {video_path.name}: {e}", exc_info=True)
    
    return stats


def watch_directory(
    directory: str,
    config: Config,
    no_llm: bool = False,
    no_mux: bool = False,
    interval: int = 60
):
    """
    Watch a directory for new video files and process them.
    
    Args:
        directory: Directory to watch
        config: Configuration object
        no_llm: Skip LLM polishing
        no_mux: Skip video muxing
        interval: Check interval in seconds
    """
    directory = Path(directory)
    processed_files = set()
    
    logger.info(f"Watching directory: {directory}")
    logger.info(f"Check interval: {interval}s")
    logger.info("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Get all video files
            video_files = get_video_files(str(directory))
            
            # Filter out already processed files
            new_files = [f for f in video_files if f not in processed_files]
            
            if new_files:
                logger.info(f"Found {len(new_files)} new file(s)")
                
                # Process new files
                stats = process_batch(
                    video_files=new_files,
                    config=config,
                    no_llm=no_llm,
                    no_mux=no_mux,
                    skip_existing=False  # Don't skip in watch mode
                )
                
                # Mark as processed
                processed_files.update(new_files)
                
                # Show stats
                logger.info(f"\nBatch complete: {stats['processed']} processed, {stats['failed']} failed")
            
            # Wait before next check
            time.sleep(interval)
    
    except KeyboardInterrupt:
        logger.info("\n⚠ Watch mode stopped")


def main():
    """Main entry point for batch processing."""
    parser = argparse.ArgumentParser(
        description="Batch process multiple video files for subtitle generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all videos in inbox/
  python batch_process.py
  
  # Process specific files
  python batch_process.py video1.mkv video2.mkv
  
  # Watch inbox/ for new files
  python batch_process.py --watch
  
  # Use prod profile and skip LLM
  python batch_process.py --profile prod --no-llm
        """
    )
    
    parser.add_argument(
        "files",
        nargs="*",
        help="Video files to process (if not specified, processes inbox/)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        choices=["dev", "prod"],
        help="Override config profile"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM polishing"
    )
    
    parser.add_argument(
        "--no-mux",
        action="store_true",
        help="Don't mux subtitles into video"
    )
    
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch inbox/ directory for new files"
    )
    
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=60,
        help="Watch mode check interval in seconds (default: 60)"
    )
    
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip files that already have SRT output (default: true)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = Config(config_path=args.config, profile_override=args.profile)
        set_config(config)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Set up logging
    log_level = args.log_level or config.log_level
    setup_logging(log_level)
    
    logger.info("Anime Subtitle Pipeline - Batch Processing")
    logger.info(f"Profile: {config.profile}")
    
    # Determine files to process
    if args.files:
        # Process specific files
        video_files = [Path(f) for f in args.files]
        
        # Validate files exist
        for f in video_files:
            if not f.exists():
                logger.error(f"File not found: {f}")
                sys.exit(1)
    else:
        # Process inbox directory
        inbox_dir = config.get_path("inbox")
        video_files = get_video_files(inbox_dir)
        
        if not video_files:
            if args.watch:
                logger.info(f"No files in {inbox_dir}, waiting for new files...")
            else:
                logger.warning(f"No video files found in {inbox_dir}")
                sys.exit(0)
    
    try:
        if args.watch:
            # Watch mode
            inbox_dir = config.get_path("inbox")
            watch_directory(
                directory=inbox_dir,
                config=config,
                no_llm=args.no_llm,
                no_mux=args.no_mux,
                interval=args.watch_interval
            )
        else:
            # Batch mode
            logger.info(f"Processing {len(video_files)} file(s)...\n")
            
            stats = process_batch(
                video_files=video_files,
                config=config,
                no_llm=args.no_llm,
                no_mux=args.no_mux,
                skip_existing=args.skip_existing
            )
            
            # Print summary
            logger.info("\n" + "="*70)
            logger.info("BATCH PROCESSING SUMMARY")
            logger.info("="*70)
            logger.info(f"Total files: {stats['total']}")
            logger.info(f"✓ Processed: {stats['processed']}")
            logger.info(f"⊘ Skipped: {stats['skipped']}")
            logger.info(f"✗ Failed: {stats['failed']}")
            
            if stats["errors"]:
                logger.info("\nErrors:")
                for error in stats["errors"]:
                    logger.info(f"  {error['file']}: {error['error']}")
            
            logger.info("="*70)
            
            # Exit code based on results
            if stats["failed"] > 0:
                sys.exit(1)
            else:
                sys.exit(0)
    
    except KeyboardInterrupt:
        logger.info("\n⚠ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
