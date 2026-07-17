#!/usr/bin/env python3
"""Create a rights manifest and static reports from a local PICO-8 cart."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from analyze_cart import analyze, markdown_report
from pico8_cart import CartError, read_cartridge


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cartridge", type=Path, help="local .p8, .p8.png, or .p8.rom obtained lawfully")
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license", required=True, help="SPDX-like name or exact source wording")
    parser.add_argument("--permission-basis", required=True, help="why source inspection is allowed")
    parser.add_argument("--copy-cart", action="store_true", help="copy the cart only when redistribution/storage is allowed")
    args = parser.parse_args()

    try:
        raw = args.cartridge.read_bytes()
        cart = read_cartridge(args.cartridge)
        args.case_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "title": args.title,
            "author": args.author,
            "source_url": args.source_url,
            "license": args.license,
            "permission_basis": args.permission_basis,
            "local_filename": args.cartridge.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "cart_copied_into_case": bool(args.copy_cart),
            "notes": "Verify current source terms before publishing, modifying, redistributing, or commercializing any derivative.",
        }
        (args.case_dir / "rights.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = analyze(cart, args.cartridge.name)
        result["rights"] = manifest
        (args.case_dir / "static-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.case_dir / "static-analysis.md").write_text(markdown_report(result), encoding="utf-8")
        if args.copy_cart:
            shutil.copy2(args.cartridge, args.case_dir / args.cartridge.name)
        print(args.case_dir)
        return 0
    except FileExistsError:
        print(f"error: case directory already exists: {args.case_dir}", file=sys.stderr)
        return 2
    except (OSError, CartError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
