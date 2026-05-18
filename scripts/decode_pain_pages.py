"""
解码 customer-persona-clustering / social-reviews-analyzer 生成的痛点 HTML
里的 gzip+base64 内嵌页（每个 k-level 是一页）。

输入：
  痛点 HTML 提取后的 JSON（含 variants[].pages[].gzip_b64）

输出：
  pricing_inputs/<source>_decoded.json，结构：
  {
    "product_name": "...",
    "variants": {
      "v0": {"label": "...", "defaultK": 5, "k_to_payload": {"5": {...}, "10": {...}}}
    }
  }
"""

import argparse
import base64
import gzip
import json
import re
import sys
from pathlib import Path


def extract_balanced(html: str, token: str) -> str | None:
    idx = html.find(token)
    if idx == -1:
        return None
    open_i = html.find("{", idx)
    if open_i == -1:
        return None
    depth, in_s, sc, esc = 0, False, None, False
    for i in range(open_i, len(html)):
        c = html[i]
        if esc:
            esc = False; continue
        if in_s:
            if c == "\\":
                esc = True; continue
            if c == sc:
                in_s = False
            continue
        if c in ('"', "'"):
            in_s = True; sc = c; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[open_i:i + 1]
    return None


def decode_page_data(html_inner: str) -> dict | None:
    for tok in ["const DATA =", "const D =", "window.DATA =", "const data ="]:
        raw = extract_balanced(html_inner, tok)
        if not raw:
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            fixed = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$]*)\s*:", r'\1"\2":', raw)
            fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
            try:
                return json.loads(fixed)
            except Exception:
                continue
    return None


def slim_payload(payload: dict) -> dict:
    """保留 Phase 0 / Phase 1 / Phase 2 / Market Gap 都用得到的字段。"""
    keep = ["product_name", "persona_col", "personas", "persona_sizes",
            "clusters", "rate_matrix", "count_matrix",
            "n_total", "n_with_pain", "n_phrases", "quadrant",
            "overall_sentiment", "has_sentiment"]
    out = {k: payload[k] for k in keep if k in payload}
    if "clusters" in out:
        out["clusters"] = [
            {**{kk: vv for kk, vv in c.items() if kk != "samples"},
             "samples": (c.get("samples", [])[:3] if isinstance(c.get("samples"), list) else c.get("samples"))}
            for c in out["clusters"]
        ]
    return out


def process(src_path: Path, dest_path: Path,
            highlight_k: set[int] | None = None) -> None:
    if highlight_k is None:
        highlight_k = {2, 3, 5, 8, 10, 15, 20}

    d = json.loads(src_path.read_text())
    out = {"product_name": d.get("product_name"), "variants": {}}
    variants = d["variants"]
    if isinstance(variants, list):
        variants = {f"v{v.get('id', i)}": v for i, v in enumerate(variants)}

    for vid, v in variants.items():
        if not isinstance(v, dict) or "pages" not in v:
            continue
        out["variants"][vid] = {
            "label": v.get("label", vid),
            "defaultK": v.get("defaultK"),
            "k_to_payload": {},
        }
        for p in v.get("pages", []):
            k = p.get("k")
            if k not in highlight_k:
                continue
            try:
                html_inner = gzip.decompress(base64.b64decode(p["gzip_b64"])).decode("utf-8")
            except Exception as e:
                print(f"  ✗ {vid} k={k} decompress fail: {e}")
                continue
            payload = decode_page_data(html_inner)
            if payload is None:
                print(f"  ✗ {vid} k={k} no DATA block")
                continue
            out["variants"][vid]["k_to_payload"][str(k)] = slim_payload(payload)
            print(f"  ✓ {vid} k={k}  clusters={len(payload.get('clusters', []))}  personas={len(payload.get('personas', []))}")

    dest_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n→ {dest_path}  ({dest_path.stat().st_size/1024:.0f} KB)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="extracted pain JSON (from extract_html_data.py)")
    p.add_argument("--output", required=True, help="decoded JSON output path")
    p.add_argument("--k-levels", default="2,3,5,8,10,15,20", help="comma-separated k values to decode")
    args = p.parse_args()

    highlight_k = {int(x) for x in args.k_levels.split(",")}
    process(Path(args.input), Path(args.output), highlight_k)


if __name__ == "__main__":
    main()
