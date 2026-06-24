#!/usr/bin/env python3
"""A-1 前処理: 仕様PDF → 高解像度PNG。

Vision LLM（Claude Code 内でのインタラクティブ読み取り）に渡すための画像化を行う。
pdftoppm（poppler, 推奨）を優先し、無ければ macOS の qlmanage にフォールバックする。

使い方:
    uv run python src/a_render.py specs/spec_sample.pdf
    uv run python src/a_render.py specs/spec_sample.pdf --outdir out/1a_extract --dpi 300
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def render_with_pdftoppm(pdf: Path, outdir: Path, dpi: int) -> list[Path]:
    prefix = outdir / pdf.stem
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)],
        check=True,
    )
    return sorted(outdir.glob(f"{pdf.stem}-*.png"))


def render_with_qlmanage(pdf: Path, outdir: Path, size: int = 2000) -> list[Path]:
    subprocess.run(
        ["qlmanage", "-t", "-s", str(size), "-o", str(outdir), str(pdf)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    produced = outdir / f"{pdf.name}.png"  # qlmanage は <name>.pdf.png を作る
    if produced.exists():
        target = outdir / f"{pdf.stem}-1.png"
        produced.replace(target)
        return [target]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="仕様PDF → 高解像度PNG（A-1 前処理）")
    ap.add_argument("pdf", type=Path, help="入力PDF")
    ap.add_argument("--outdir", type=Path, default=Path("out/1a_extract"))
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args(argv)

    if not args.pdf.exists():
        print(f"ERROR: PDF が見つかりません: {args.pdf}", file=sys.stderr)
        return 1
    args.outdir.mkdir(parents=True, exist_ok=True)

    if shutil.which("pdftoppm"):
        pages = render_with_pdftoppm(args.pdf, args.outdir, args.dpi)
        engine = "pdftoppm"
    elif shutil.which("qlmanage"):
        pages = render_with_qlmanage(args.pdf, args.outdir)
        engine = "qlmanage"
    else:
        print("ERROR: pdftoppm も qlmanage も見つかりません。`brew install poppler` を実行してください。",
              file=sys.stderr)
        return 1

    if not pages:
        print("ERROR: ページ画像が生成されませんでした。", file=sys.stderr)
        return 1

    print(f"[{engine}] {len(pages)} ページを生成:")
    for p in pages:
        print(f"  {p}")
    print("\n次の手順 (A-1 読み取り): Claude Code 内でこのPNGと prompts/a1_read.md を使い、")
    print("ページ内容を out/1a_extract/raw_extract.md に忠実に転記してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
