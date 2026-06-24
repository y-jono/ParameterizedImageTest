"""パラメータ → ImageMagick 生成コマンド／exiftool・identify 検証 の共通定義。

「意図(intended)＝生成時にツールへ渡す指定」と「実測(actual)＝生成後にファイルから
読み戻した値」を分離し、フィールド単位で突合する。ImageMagick が指定どおりに作れない
ことがあるため、生成しただけでは信用せず必ず検証する。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

# RGB 埋め込み用 ICC（macOS 同梱）。constraints 上 ICC 埋め込みは RGB のみ。
SRGB_CANDIDATES = [
    "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
    "/usr/share/color/icc/sRGB.icc",
]
EXT = {"JPEG": ".jpg", "TIFF": ".tif", "PSD": ".psd"}

# ImageMagick は既定フォントが無い環境があるため明示する。
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def srgb_profile() -> Optional[str]:
    for p in SRGB_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _font() -> Optional[str]:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def filename(case_id: str, c: Dict) -> str:
    parts = [case_id, c["format"], c["color_mode"], f'{c["bit_depth"]}bit',
             c["compression"], f'alpha-{c["alpha"]}', f'icc-{c["icc_profile"]}']
    return "_".join(parts) + EXT[c["format"]]


def build_command(c: Dict, out_path: Path, canvas=(640, 480)) -> list[str]:
    """case（具体値）から ImageMagick の生成コマンドを組み立てる（JPEG/TIFF のみ）。"""
    w, h = canvas
    caption = (f'{out_path.stem}\\n'
               f'{c["format"]} {c["color_mode"]} {c["bit_depth"]}bit '
               f'{c["compression"]} alpha={c["alpha"]} icc={c["icc_profile"]}')
    cmd = ["magick", "-size", f"{w}x{h}", "gradient:red-blue",
           "-gravity", "North", "-pointsize", "18", "-fill", "white",
           "-undercolor", "#00000080"]
    font = _font()
    if font:
        cmd += ["-font", font]
    cmd += ["-annotate", "+0+12", caption]

    # カラーモード（colorspace は RGB 中に注釈を描いてから変換）
    cs = {"RGB": "sRGB", "CMYK": "CMYK", "Grayscale": "Gray"}[c["color_mode"]]
    cmd += ["-colorspace", cs]

    # αチャンネル
    cmd += ["-alpha", "set"] if c["alpha"] == "present" else ["-alpha", "off"]

    # ビット深度
    cmd += ["-depth", str(c["bit_depth"])]

    # ICC プロファイル（埋め込み or 除去）
    if c["icc_profile"] == "embedded":
        prof = srgb_profile()
        if prof:
            cmd += ["-profile", prof]
    else:
        cmd += ["+profile", "icc"]

    # 圧縮（TIFF のみ。JPEG は形式自体が JPEG 圧縮）
    if c["format"] == "TIFF":
        cmd += ["-compress", "LZW" if c["compression"] == "LZW" else "None"]

    cmd.append(str(out_path))
    return cmd


def generate(c: Dict, out_path: Path) -> tuple[bool, str]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(c, out_path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.returncode == 0 and out_path.exists()), (r.stderr.strip() or r.stdout.strip())


# --------------------------------------------------------------------------- #
# 検証（読み戻し）
# --------------------------------------------------------------------------- #
def _identify(path: Path) -> Dict[str, str]:
    fmt = "%m|%[colorspace]|%z|%C|%[channels]"
    out = subprocess.run(["magick", "identify", "-format", fmt, str(path)],
                         capture_output=True, text=True).stdout.strip()
    m, cs, depth, comp, channels = (out.split("|") + ["", "", "", "", ""])[:5]
    return {"format": m, "colorspace": cs, "depth": depth, "compression": comp,
            "channels": channels.strip()}


def _has_icc(path: Path) -> bool:
    out = subprocess.run(["exiftool", "-s3", "-ICC_Profile:ProfileDescription", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return bool(out)


_CS_TO_MODE = {"srgb": "RGB", "rgb": "RGB", "cmyk": "CMYK", "gray": "Grayscale", "grey": "Grayscale"}


def verify(path: Path, intended: Dict) -> Dict:
    """actual を読み戻し、intended と突合。戻り値に actual と各フィールドの一致/不一致。"""
    idf = _identify(path)
    chan = idf["channels"].split()[0].lower() if idf["channels"] else ""
    alpha_actual = "present" if chan.endswith("a") else "absent"
    cs_token = chan[:-1] if chan.endswith("a") else chan
    mode_actual = _CS_TO_MODE.get(cs_token, idf["colorspace"])
    icc_actual = "embedded" if _has_icc(path) else "absent"

    actual = {
        "format": (idf["format"] or "").upper(),
        "color_mode": mode_actual,
        "bit_depth": idf["depth"],
        "compression": idf["compression"],
        "alpha": alpha_actual,
        "icc_profile": icc_actual,
    }

    checks: Dict[str, bool] = {}
    checks["format"] = actual["format"] == intended["format"].upper()
    checks["color_mode"] = actual["color_mode"] == intended["color_mode"]
    checks["bit_depth"] = str(actual["bit_depth"]) == str(intended["bit_depth"])
    if intended["format"] == "JPEG":
        checks["compression"] = True  # JPEG は形式自体が圧縮。compression パラメータは N/A
        actual["compression"] = f'{idf["compression"]} (n/a: JPEG)'
    else:
        want = "LZW" if intended["compression"] == "LZW" else "None"
        checks["compression"] = idf["compression"] == want
    checks["alpha"] = actual["alpha"] == intended["alpha"]
    checks["icc_profile"] = actual["icc_profile"] == intended["icc_profile"]

    return {"actual": actual, "checks": checks, "match": all(checks.values())}


def tools_available() -> list[str]:
    return [t for t in ("magick", "exiftool") if not shutil.which(t)]
