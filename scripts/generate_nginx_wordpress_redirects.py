#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an Nginx map for WordPress ?p=ID redirects.")
    parser.add_argument("--mapping", required=True, help="Path to wordpress-url-map.csv")
    parser.add_argument("--output", required=True, help="Path to nginx map config output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping_path = Path(args.mapping).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    rows = []
    with mapping_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            post_id = (row.get("wordpress_id") or "").strip()
            new_url = (row.get("new_url") or "").strip()
            if post_id and new_url:
                rows.append((post_id, new_url))

    lines = [
        "# Generated from data/wordpress-url-map.csv",
        "map $arg_p $wordpress_redirect_uri {",
        "    default \"\";",
    ]
    lines.extend(f"    {post_id} {new_url};" for post_id, new_url in rows)
    lines.extend(
        [
            "}",
            "",
            "# Example usage:",
            "# location = /blog/ {",
            "#     if ($wordpress_redirect_uri != \"\") {",
            "#         return 301 https://diff.im$wordpress_redirect_uri;",
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
