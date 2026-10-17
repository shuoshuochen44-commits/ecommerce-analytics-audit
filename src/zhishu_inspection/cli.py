import argparse
import json
from pathlib import Path

from .profiling import profile_dataset, render_profile_markdown


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile the five core Olist CSV files"
    )
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/week-01")
    )
    args = parser.parse_args()

    profile = profile_dataset(args.raw_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "profile.md").write_text(
        render_profile_markdown(profile), encoding="utf-8"
    )
    print(f"Profiled {len(profile)} files into {args.output_dir}")


if __name__ == "__main__":
    main()
