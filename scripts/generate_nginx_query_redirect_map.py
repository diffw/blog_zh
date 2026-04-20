#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an Nginx map for query-string redirect IDs.")
    parser.add_argument("--mapping", required=True, help="Path to a JSON file of id -> target path")
    parser.add_argument("--query-var", required=True, help="Nginx query variable name without the $arg_ prefix")
    parser.add_argument("--map-name", required=True, help="Name of the Nginx map variable to generate")
    parser.add_argument("--output", required=True, help="Path to nginx map config output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping_path = Path(args.mapping).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    rows = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(rows, dict):
        raise RuntimeError(f"Expected a JSON object in {mapping_path}")

    lines = [
        f"# Generated from {mapping_path.name}",
        f"map $arg_{args.query_var} ${args.map_name} {{",
        '    default "";',
    ]
    for key, target in sorted(rows.items(), key=lambda item: item[0]):
        if key and target:
            lines.append(f"    {key} {target};")
    lines.extend(
        [
            "}",
            "",
            "# Example usage:",
            "# location = /blog/ {",
            f"#     if (${args.map_name} != \"\") {{",
            f"#         return 301 https://diff.im${args.map_name};",
            "#     }",
            "# }",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    print(f"Generated {len(rows)} redirect entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
