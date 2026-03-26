from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from .pog import (
    build_pog_manifest,
    build_pog_publish_diagnostics,
    has_last_good_pog_publish,
    load_pog_publish_config,
    resolve_pog_publish_mode,
    write_pog_diagnostics,
    write_pog_failure_diagnostics,
    write_pog_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the MSP-POG static viewer outputs.")
    parser.add_argument("--output-dir", default="docs/pog", help="Directory for generated POG outputs.")
    parser.add_argument("--config", default="config/pog_sources.json", help="Path to the POG publish config.")
    parser.add_argument(
        "--shell-dir",
        default="docs/pog",
        help="Directory containing the static POG app shell files.",
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=("auto", "fixture", "live"),
        help="POG source mode. auto prefers live when Nexgen credentials are present.",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    config_path = Path(args.config)
    shell_dir = Path(args.shell_dir)
    generated_at = datetime.now(timezone.utc)

    board, sources, _ = load_pog_publish_config(
        config_path,
        mode="fixture",
        environment=os.environ,
        load_assets=False,
    )
    runtime_mode = resolve_pog_publish_mode(
        requested_mode=args.mode,
        sources=sources,
        environment=os.environ,
    )
    try:
        board, sources, assets = load_pog_publish_config(
            config_path,
            mode=runtime_mode,
            environment=os.environ,
        )
        manifest = build_pog_manifest(
            board=board,
            sources=sources,
            assets=assets,
            generated_at=generated_at,
            output_dir=output_dir,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        copy_shell_assets(shell_dir=shell_dir, output_dir=output_dir)
        write_pog_outputs(output_dir=output_dir, manifest=manifest, assets=assets)
        write_pog_diagnostics(
            output_dir,
            build_pog_publish_diagnostics(
                status="healthy",
                last_success_at=generated_at,
                source_mode=runtime_mode,
                details={
                    "sourceCount": len(sources),
                    "slotCount": len(manifest["slots"]),
                },
            ),
        )
        print(f"Wrote {len(manifest['slots'])} POG slots to {output_dir}.")
        return 0
    except Exception as error:
        diagnostics = write_pog_failure_diagnostics(
            output_dir,
            attempted_at=generated_at,
            source_mode=runtime_mode,
            details={"failureReason": str(error)},
        )
        if not has_last_good_pog_publish(output_dir):
            raise
        print(
            f"Reused last good POG publish after refresh failure: {error}"
            f" status={diagnostics.status}",
            file=sys.stderr,
        )
        return 0


def copy_shell_assets(*, shell_dir: Path, output_dir: Path) -> None:
    for filename in ("index.html", "app.js", "styles.css"):
        source_path = shell_dir / filename
        destination_path = output_dir / filename
        if source_path.resolve() == destination_path.resolve():
            continue
        shutil.copy2(source_path, destination_path)


if __name__ == "__main__":
    sys.exit(main())
