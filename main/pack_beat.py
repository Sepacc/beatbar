"""
pack_beat.py - Desktop CLI tool to create .beat archive files from beatmaps.

Usage examples:

  # Pack beatmap + skins only (video referenced by filename, not embedded):
  python pack_beat.py wicked-r34-level-1.mp4 wicked-r34-level-1.json

  # Pack with embedded video (self-contained .beat file):
  python pack_beat.py wicked-r34-level-1.mp4 wicked-r34-level-1.json --embed-video

  # Custom output path and title:
  python pack_beat.py video.mp4 beats.json -o "mypack.beat" --title "My Pack"

  # Show info about an existing .beat file:
  python pack_beat.py info mypack.beat

  # Extract / inspect a .beat file:
  python pack_beat.py extract mypack.beat ./extracted/
"""

import sys
import os
import argparse
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS_DIR)

from beat_format import BeatFormat


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def _progress(written: int, total: int):
    pct = int(written * 100 / total)
    bar = "=" * (pct // 4) + "-" * (25 - pct // 4)
    mb_w = written / 1_048_576
    mb_t = total   / 1_048_576
    print(f"\r  [{bar}] {pct:3d}%  {mb_w:.1f} / {mb_t:.1f} MB", end="", flush=True)


def cmd_create(args):
    video_path  = args.video
    beat_path   = args.beatmap
    output_path = args.output or os.path.splitext(beat_path)[0] + ".beat"
    title       = args.title or os.path.splitext(os.path.basename(beat_path))[0]

    # Auto-find skins dir from viewer/skins relative to script
    skins_dir = args.skins
    if not skins_dir:
        candidate = os.path.normpath(os.path.join(_THIS_DIR, "viewer", "skins"))
        if os.path.isdir(candidate):
            skins_dir = candidate

    print(f"Creating .beat archive: {output_path}")
    print(f"  Title      : {title}")
    print(f"  Beatmap    : {beat_path}")
    print(f"  Video      : {video_path or '(not included)'}")
    print(f"  Embed video: {args.embed_video}")
    print(f"  Skins dir  : {skins_dir or '(not found)'}")

    t0 = time.time()
    out = BeatFormat.create(
        output_path,
        beat_path,
        title=title,
        video_path=video_path,
        skins_dir=skins_dir,
        embed_video=args.embed_video,
        on_progress=_progress if args.embed_video else None,
    )
    if args.embed_video:
        print()  # newline after progress bar

    elapsed = time.time() - t0
    size_mb = os.path.getsize(out) / 1_048_576
    print(f"\n[OK] Done in {elapsed:.1f}s - {size_mb:.1f} MB")
    print(f"     Output: {out}")

    # Print info
    info = BeatFormat.get_info(out)
    print("\n  Contents:")
    for k, v in info.items():
        print(f"    {k:<25} {v}")


def cmd_info(args):
    path = args.beat_file
    if not BeatFormat.is_valid(path):
        print(f"[ERROR] Not a valid .beat file: {path}")
        sys.exit(1)
    info = BeatFormat.get_info(path)
    size_mb = os.path.getsize(path) / 1_048_576
    print(f"\n.beat file: {path}  ({size_mb:.1f} MB)")
    for k, v in info.items():
        print(f"  {k:<25} {v}")


def cmd_extract(args):
    path     = args.beat_file
    dest_dir = args.dest
    if not BeatFormat.is_valid(path):
        print(f"[ERROR] Not a valid .beat file: {path}")
        sys.exit(1)

    with BeatFormat.open(path) as bf:
        print(f"Title       : {bf.get_title()}")
        print(f"Video ref   : {bf.get_video_name()}")

        skins_dir = bf.extract_skins(dest_dir)
        print(f"Skins       -> {skins_dir}  ({len(bf.list_skins())} files)")

        bm = bf.get_beatmap()
        print(f"Beats       : {len(bm.get('beats', []))}")
        print(f"Zones       : {len(bm.get('zones', []))}")

        import json
        bm_path = os.path.join(dest_dir, "beatmap.json")
        with open(bm_path, "w", encoding="utf-8") as f:
            json.dump(bm, f, indent=2)
        print(f"Beatmap     -> {bm_path}")

        if bf.has_embedded_video():
            vsize_mb = bf.get_embedded_video_size_bytes() / 1_048_576
            print(f"Video ({vsize_mb:.1f} MB) -> extracting...", end="", flush=True)
            vp = bf.extract_video(dest_dir)
            print(f" {vp}")
        else:
            print("No embedded video.")

    print(f"\n[OK] Extracted to: {dest_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="BeatViewer .beat archive packer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    # ── create ────────────────────────────────────────────────────────────────
    cp = sub.add_parser("create", help="Create a .beat archive")
    cp.add_argument("video",    nargs="?", help="Video file path (optional reference)")
    cp.add_argument("beatmap",  help="Beatmap .json file path")
    cp.add_argument("-o", "--output", help="Output .beat file path")
    cp.add_argument("--title",  help="Human-readable title for the pack")
    cp.add_argument("--skins",  help="Directory with SVG skin files (default: viewer/skins)")
    cp.add_argument("--embed-video", action="store_true",
                    help="Embed the entire video file inside the .beat archive (self-contained)")

    # ── info ──────────────────────────────────────────────────────────────────
    ip = sub.add_parser("info", help="Inspect a .beat file")
    ip.add_argument("beat_file", help="Path to the .beat file")

    # ── extract ───────────────────────────────────────────────────────────────
    ep = sub.add_parser("extract", help="Extract skins and beatmap from a .beat file")
    ep.add_argument("beat_file", help="Path to the .beat file")
    ep.add_argument("dest",      help="Directory to extract files to")

    # ── Shorthand: positional create when first arg is a file ─────────────────
    # (python pack_beat.py video.mp4 beats.json ...)
    if len(sys.argv) >= 2 and sys.argv[1] not in ("create", "info", "extract", "-h", "--help"):
        # Inject "create" subcommand
        sys.argv.insert(1, "create")

    args = parser.parse_args()

    if args.cmd == "create":
        if not args.beatmap:
            parser.error("beatmap .json path is required")
        cmd_create(args)
    elif args.cmd == "info":
        cmd_info(args)
    elif args.cmd == "extract":
        cmd_extract(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
