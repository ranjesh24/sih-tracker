"""Launch one worker process per camera, all sharing a single epoch.

    python scripts/run_all_workers.py --video-dir datasets/videos --out-dir runs/

Why this script exists at all
-----------------------------
It exists to generate the epoch exactly once and pass that same value to every
worker.

If each worker defaulted its own epoch to `datetime.now()`, the workers would
start milliseconds to seconds apart and their synthetic clocks would disagree by
that much. The backend's spatio-temporal gate compares `first_frame_at` across
cameras and rejects transits that are too fast to be physical, so a worker whose
clock runs early makes every vehicle appear to reach its camera sooner than it
did. The gate then rejects correct matches as TEMPORAL_TOO_FAST.

That failure is nearly undiagnosable from the symptom: trajectories break, match
rates fall, and every component looks individually correct. Nothing in the
backend can detect it either, beyond the `received_at` skew check. Passing one
epoch to every process is the fix, and it is the whole reason not to start
workers by hand.

One process per camera rather than threads: the models hold the GIL through
inference, so threads would serialise, and a crashed worker takes down only its
own camera.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The pipeline package lives one level up from scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.video_source import to_iso8601_utc  # noqa: E402

VIDEO_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")
RUN_WORKER_SCRIPT = Path(__file__).resolve().parent / "run_worker.py"


def camera_id_from_video(video_path: Path) -> str:
    """Derive a camera code from a video filename.

    `CAM-01.mp4` becomes `CAM-01`. Naming the footage after the camera keeps the
    mapping in one obvious place rather than in a side table nobody updates.

    Args:
        video_path: Path to a source video.

    Returns:
        The camera code.
    """
    return video_path.stem


def discover_videos(video_dir: Path) -> list[Path]:
    """Find the source videos in a directory, in a stable order.

    Args:
        video_dir: Directory to scan.

    Returns:
        Sorted list of video paths.

    Raises:
        FileNotFoundError: If the directory does not exist or holds no video.
    """
    if not video_dir.is_dir():
        raise FileNotFoundError(f"video directory not found: {video_dir}")

    videos = sorted(
        path
        for path in video_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )
    if not videos:
        raise FileNotFoundError(
            f"no videos with suffixes {VIDEO_SUFFIXES} found in {video_dir}"
        )
    return videos


def build_worker_command(
    video_path: Path,
    camera_id: str,
    epoch_iso: str,
    out_dir: Path | None,
    should_post: bool,
    should_visualize: bool,
) -> list[str]:
    """Build the argv for one worker subprocess.

    Args:
        video_path: Source video for this camera.
        camera_id: Camera code.
        epoch_iso: The SHARED epoch, identical across every worker.
        out_dir: Directory for per-camera JSONL output, if in JSONL mode.
        should_post: Whether the worker posts to the backend instead.
        should_visualize: Whether to write an annotated mp4 per camera.

    Returns:
        The command to run.
    """
    command = [
        sys.executable,
        str(RUN_WORKER_SCRIPT),
        "--video",
        str(video_path),
        "--camera-id",
        camera_id,
        "--epoch",
        epoch_iso,
    ]

    if should_post:
        command.append("--post")
    else:
        assert out_dir is not None  # guaranteed by main()
        command += ["--out", str(out_dir / f"{camera_id}.jsonl")]

    if should_visualize and out_dir is not None:
        command += ["--visualize", str(out_dir / f"{camera_id}_annotated.mp4")]

    return command


def build_arg_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Run one worker per camera with a single shared epoch."
    )
    parser.add_argument(
        "--video-dir",
        required=True,
        type=Path,
        help="Directory of source videos, one per camera, named <CAMERA-ID>.mp4.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for per-camera JSONL output. Required unless --post.",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="Workers POST to the backend instead of writing JSONL.",
    )
    parser.add_argument(
        "--epoch",
        default=None,
        help="Override the shared epoch, ISO-8601 UTC. Defaults to now.",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Write an annotated mp4 per camera into --out-dir.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        0 if every worker succeeded, 1 otherwise.
    """
    args = build_arg_parser().parse_args(argv)

    if not args.post and args.out_dir is None:
        print(
            "error: --out-dir is required unless --post is given", file=sys.stderr
        )
        return 1

    try:
        videos = discover_videos(args.video_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    # THE shared epoch. Generated once, here, and passed verbatim to every
    # worker. Nothing below may recompute it per camera.
    epoch_iso = args.epoch or to_iso8601_utc(datetime.now(timezone.utc))

    print(f"shared epoch: {epoch_iso}")
    print(f"cameras: {[camera_id_from_video(video) for video in videos]}")
    print()

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    for video_path in videos:
        camera_id = camera_id_from_video(video_path)
        command = build_worker_command(
            video_path=video_path,
            camera_id=camera_id,
            epoch_iso=epoch_iso,
            out_dir=args.out_dir,
            should_post=args.post,
            should_visualize=args.visualize,
        )
        print(f"launching {camera_id}: {' '.join(command)}", flush=True)
        processes.append((camera_id, subprocess.Popen(command)))

    failed: list[str] = []
    for camera_id, process in processes:
        return_code = process.wait()
        if return_code != 0:
            failed.append(f"{camera_id} (exit {return_code})")

    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1

    print(f"all {len(processes)} workers completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
