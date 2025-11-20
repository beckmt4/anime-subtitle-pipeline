"""
Benchmark different configurations to find optimal settings.

This tool automatically tests multiple configurations and compares results
to identify the best settings for your use case.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional
import subprocess
import shutil

logger = logging.getLogger(__name__)


def run_pipeline(
    video_path: str,
    config_name: str,
    config_overrides: Dict,
    no_llm: bool = False
) -> Dict:
    """
    Run the subtitle pipeline with specific configuration.
    
    Args:
        video_path: Path to video file
        config_name: Name for this configuration
        config_overrides: Configuration overrides to apply
        no_llm: Whether to skip LLM polishing
        
    Returns:
        Dictionary with timing and output path info
    """
    logger.info(f"Running pipeline with config: {config_name}")
    
    # Build command
    cmd = ["python", "main.py", video_path]
    
    if no_llm:
        cmd.append("--no-llm")
    
    # Apply config overrides (would need to implement config override in main.py)
    # For now, we'll document this limitation
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        elapsed_time = time.time() - start_time
        
        if result.returncode != 0:
            logger.error(f"Pipeline failed: {result.stderr}")
            return {
                "config": config_name,
                "success": False,
                "elapsed_time": elapsed_time,
                "error": result.stderr
            }
        
        # Parse output to find generated files
        video_stem = Path(video_path).stem
        srt_file = Path("outbox") / f"{video_stem}.en.srt"
        log_file = Path("logs") / f"{video_stem}.json"
        
        return {
            "config": config_name,
            "success": True,
            "elapsed_time": elapsed_time,
            "srt_file": str(srt_file),
            "log_file": str(log_file),
            "stdout": result.stdout
        }
        
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Pipeline execution failed: {e}")
        return {
            "config": config_name,
            "success": False,
            "elapsed_time": elapsed_time,
            "error": str(e)
        }


def compare_with_reference(
    video_path: str,
    generated_srt: str,
    subtitle_track: int = 0
) -> Optional[Dict]:
    """
    Compare generated subtitles with reference.
    
    Args:
        video_path: Path to video with embedded subtitles
        generated_srt: Path to generated SRT
        subtitle_track: Reference subtitle track index
        
    Returns:
        Comparison results or None if failed
    """
    cmd = [
        "python",
        "compare_subtitles.py",
        video_path,
        generated_srt,
        "--subtitle-track", str(subtitle_track),
        "--output", "temp_comparison.json"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Comparison failed: {result.stderr}")
            return None
        
        with open("temp_comparison.json", 'r', encoding='utf-8') as f:
            comparison = json.load(f)
        
        # Clean up temp file
        Path("temp_comparison.json").unlink()
        
        return comparison
        
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.error(f"Comparison failed: {e}")
        return None


def benchmark_configurations(
    video_path: str,
    configs: List[Dict],
    reference_track: int = 0
) -> List[Dict]:
    """
    Benchmark multiple configurations.
    
    Args:
        video_path: Path to test video
        configs: List of configuration dictionaries
        reference_track: Reference subtitle track for comparison
        
    Returns:
        List of benchmark results
    """
    results = []
    
    for config in configs:
        config_name = config['name']
        logger.info(f"\n{'='*70}")
        logger.info(f"Testing configuration: {config_name}")
        logger.info(f"{'='*70}")
        
        # Run pipeline
        run_result = run_pipeline(
            video_path,
            config_name,
            config.get('overrides', {}),
            config.get('no_llm', False)
        )
        
        if not run_result['success']:
            results.append(run_result)
            continue
        
        # Save output with config name
        srt_file = Path(run_result['srt_file'])
        backup_srt = srt_file.parent / f"{srt_file.stem}_{config_name}.srt"
        shutil.copy(srt_file, backup_srt)
        run_result['backup_srt'] = str(backup_srt)
        
        # Compare with reference
        comparison = compare_with_reference(
            video_path,
            str(srt_file),
            reference_track
        )
        
        if comparison:
            run_result['comparison'] = {
                'match_rate': comparison['match_rate'],
                'avg_similarity': comparison['average_similarity'],
                'matched_count': comparison['matched_count']
            }
        
        results.append(run_result)
        
        logger.info(f"Config: {config_name}")
        logger.info(f"  Time: {run_result['elapsed_time']:.1f}s")
        if comparison:
            logger.info(f"  Match rate: {comparison['match_rate']*100:.1f}%")
            logger.info(f"  Avg similarity: {comparison['average_similarity']*100:.1f}%")
    
    return results


def print_benchmark_report(results: List[Dict]):
    """
    Print formatted benchmark report.
    
    Args:
        results: List of benchmark result dictionaries
    """
    print("\n" + "=" * 70)
    print("CONFIGURATION BENCHMARK REPORT")
    print("=" * 70)
    
    successful = [r for r in results if r['success']]
    
    if not successful:
        print("\nNo successful runs to compare!")
        return
    
    # Sort by similarity (best first)
    if all('comparison' in r for r in successful):
        successful.sort(key=lambda x: x['comparison']['avg_similarity'], reverse=True)
    
    print(f"\nTested {len(results)} configurations ({len(successful)} successful)\n")
    
    # Print table
    print(f"{'Rank':<6} {'Config':<20} {'Time (s)':<10} {'Similarity':<12} {'Match Rate':<12}")
    print("-" * 70)
    
    for i, result in enumerate(successful, 1):
        config = result['config']
        elapsed = result['elapsed_time']
        
        if 'comparison' in result:
            similarity = result['comparison']['avg_similarity'] * 100
            match_rate = result['comparison']['match_rate'] * 100
            print(f"{i:<6} {config:<20} {elapsed:<10.1f} {similarity:<11.1f}% {match_rate:<11.1f}%")
        else:
            print(f"{i:<6} {config:<20} {elapsed:<10.1f} {'N/A':<12} {'N/A':<12}")
    
    # Print recommendation
    if successful and 'comparison' in successful[0]:
        best = successful[0]
        print("\n" + "=" * 70)
        print("RECOMMENDATION")
        print("=" * 70)
        print(f"\nBest configuration: {best['config']}")
        print(f"  Average similarity: {best['comparison']['avg_similarity']*100:.1f}%")
        print(f"  Processing time: {best['elapsed_time']:.1f}s")
        print(f"  Output file: {best['backup_srt']}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark different pipeline configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark with/without LLM
  python benchmark_configs.py video.mkv --preset llm_comparison

  # Benchmark different profiles
  python benchmark_configs.py video.mkv --preset profiles

  # Custom benchmark
  python benchmark_configs.py video.mkv --config configs.json
        """
    )
    
    parser.add_argument(
        "video",
        type=str,
        help="Path to test video file"
    )
    
    parser.add_argument(
        "--preset",
        type=str,
        choices=["llm_comparison", "profiles", "quick"],
        help="Use preset configuration set"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to custom configuration JSON"
    )
    
    parser.add_argument(
        "--reference-track",
        type=int,
        default=0,
        help="Reference subtitle track index (default: 0)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="benchmark_results.json",
        help="Output file for results (default: benchmark_results.json)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load or create configurations
    if args.config:
        with open(args.config, 'r', encoding='utf-8') as f:
            configs = json.load(f)
    elif args.preset == "llm_comparison":
        configs = [
            {"name": "no_llm", "no_llm": True},
            {"name": "with_llm", "no_llm": False}
        ]
    elif args.preset == "profiles":
        configs = [
            {"name": "dev_profile", "overrides": {"profile": "dev"}},
            {"name": "prod_profile", "overrides": {"profile": "prod"}}
        ]
    elif args.preset == "quick":
        configs = [
            {"name": "baseline", "no_llm": False}
        ]
    else:
        logger.error("Must specify --preset or --config")
        sys.exit(1)
    
    # Run benchmark
    results = benchmark_configurations(args.video, configs, args.reference_track)
    
    # Save results
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nResults saved to {args.output}")
    
    # Print report
    print_benchmark_report(results)


if __name__ == "__main__":
    main()
