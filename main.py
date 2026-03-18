"""
Usage:
    python main.py                      # Run with default settings
    python main.py --theme "art heist"  # Seed the crime with a theme
    python main.py --save-state         # Also save crime_world_state.json
    python main.py --load-state out.json # Skip Phase 1, use saved state
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

from config import OUTPUT_DIR
from crime_generator import generate_crime_world_state
from validators import validate_crime_world_state, summarise_crime_state
from meta_controller import MetaController
from story_assembler import assemble_story


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sly Fox AI Crime Mystery Generator"
    )
    p.add_argument(
        "--theme",
        default="",
        help="Optional seed theme (e.g. 'art heist', 'tech startup')",
    )
    p.add_argument(
        "--save-state",
        action="store_true",
        help="Save the crime world state JSON to the output folder",
    )
    p.add_argument(
        "--load-state",
        metavar="PATH",
        default="",
        help="Load a previously saved crime world state JSON (skip Phase 1)",
    )
    p.add_argument(
        "--output",
        metavar="PATH",
        default="",
        help="Custom path for the final story output file",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 64)
    print("Sly Fox — AI Crime Mystery Generator")
    print("CS7634 AI Storytelling | Team: Sly Fox")
    print("=" * 64)
    print()

    run_id  = datetime.now().strftime("%Y%m%d_%H%M%S")
    t_start = time.time()

    if args.load_state:
        print(f"Loading crime world state from {args.load_state!r}…")
        with open(args.load_state, "r", encoding="utf-8") as f:
            state = json.load(f)
        print(f" Loaded.  Summary: {summarise_crime_state(state)}")
    else:
        state = generate_crime_world_state(seed_theme=args.theme)

        print("\nValidating crime world state…")
        try:
            warnings = validate_crime_world_state(state)
            if warnings:
                print("Warnings:")
                for w in warnings:
                    print(f"      • {w}")
            else:
                print("All validation checks passed.")
        except ValueError as exc:
            print(f"VALIDATION FAILED: {exc}")
            print("Exiting — regenerate or fix the state manually.")
            sys.exit(1)

        print(f"\n Summary: {summarise_crime_state(state)}")

        if args.save_state:
            state_path = os.path.join(OUTPUT_DIR, f"crime_state_{run_id}.json")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            print(f"Crime world state saved → {state_path}")

    mc = MetaController(state)
    plot_points = mc.run()

    print(f"\nPhase 3 — Assembling story…")
    story = assemble_story(state, plot_points)

    out_path = args.output or os.path.join(OUTPUT_DIR, f"mystery_{run_id}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(story)

    elapsed = time.time() - t_start
    print(f"\nDone in {elapsed:.1f}s")
    print(f"Story saved → {out_path}")
    print(f"Length: {len(story):,} chars, ~{len(story.split()):,} words")
    print()

    print("─" * 64)
    print("STORY PREVIEW:")
    print("─" * 64)
    print(story[:1000])
    print("…")
    print("─" * 64)


if __name__ == "__main__":
    main()
