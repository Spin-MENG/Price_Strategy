"""
通用 HTML → const DATA = {...} JSON 提取器。
用于把 customer-persona-clustering / social-reviews-analyzer 生成的 HTML
报告（带 const DATA = ...; 嵌入 JSON）转回 JSON 数据。

支持 3 种典型嵌入模式：
  · const DATA = {...};
  · window.DATA = {...};
  · const REPORT_DATA = {...};

用法：
  python extract_html_data.py <input.html> --output <out.json>
  python extract_html_data.py <dir>/*.html --batch --output-dir <out_dir>
"""

import argparse
import json
import re
import sys
from pathlib import Path


CANDIDATE_TOKENS = [
    "const DATA =",
    "window.DATA =",
    "const data =",
    "const REPORT_DATA =",
    "const D =",
    "var DATA =",
]


def extract_balanced(html: str, token: str) -> str | None:
    """从 token 出现位置开始，找出第一个平衡 {} 区块的源文本。"""
    idx = html.find(token)
    if idx == -1:
        return None
    open_idx = html.find("{", idx)
    if open_idx == -1:
        return None
    depth = 0
    in_string = False
    string_ch = None
    escape = False
    for i in range(open_idx, len(html)):
        c = html[i]
        if escape:
            escape = False
            continue
        if in_string:
            if c == "\\":
                escape = True
                continue
            if c == string_ch:
                in_string = False
            continue
        if c in ('"', "'"):
            in_string = True
            string_ch = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[open_idx:i + 1]
    return None


def try_parse_loose(raw: str) -> dict | None:
    """尝试解析 raw JSON；失败时修补 unquoted keys + trailing commas。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', raw)
        fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
        try:
            return json.loads(fixed)
        except Exception:
            return None


def extract_from_html(html_path: Path) -> dict | None:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    for token in CANDIDATE_TOKENS:
        raw = extract_balanced(html, token)
        if raw is None:
            continue
        obj = try_parse_loose(raw)
        if obj is not None:
            print(f"  ✓ {html_path.name} parsed via {token!r} ({len(raw):,} chars)")
            return obj
    print(f"  ✗ {html_path.name} no DATA block found")
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", nargs="+", help="HTML files (glob ok)")
    p.add_argument("--output", help="single-file output")
    p.add_argument("--output-dir", help="batch output directory")
    p.add_argument("--batch", action="store_true")
    args = p.parse_args()

    paths = []
    for inp in args.inputs:
        p_ = Path(inp)
        if p_.is_dir():
            paths.extend(p_.glob("*.html"))
        else:
            paths.append(p_)
    if not paths:
        sys.exit("no HTML files found")

    if args.batch or len(paths) > 1:
        out_dir = Path(args.output_dir) if args.output_dir else paths[0].parent / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        for path in paths:
            obj = extract_from_html(path)
            if obj is None:
                continue
            out = out_dir / (path.stem + ".json")
            out.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
            print(f"  → {out}")
    else:
        obj = extract_from_html(paths[0])
        if obj is None:
            sys.exit(1)
        out = Path(args.output) if args.output else paths[0].with_suffix(".json")
        out.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f"→ {out}")


if __name__ == "__main__":
    main()
