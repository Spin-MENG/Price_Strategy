"""
Phase 1 信号抽取（通用版 cluster-aggregated proxy）。

输入：
  --persona-data    竞品 + Reddit personas decoded JSON（任一）
  --pain-data       同上的 pains decoded
  --config          品类配置
  --output-dir      落盘

输出：
  segment_pricing_summary.csv  N 个分群 × M 个信号
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def cluster_to_signal_contrib(cluster_name: str, samples: list,
                              signals: dict, themes: dict) -> dict:
    """单个 pain cluster → 对各信号的 0-2 强度权重 (per 100% rate)。"""
    text = cluster_name + " " + " ".join(samples or [])
    contribs = {}
    for sig_id, sig_def in signals.items():
        hits = 0
        for theme_id in sig_def.get("themes", []):
            theme_def = themes.get(theme_id, {})
            if any(kw in text for kw in theme_def.get("keywords", [])):
                hits += 1
                break
        contribs[sig_id] = min(hits * 2, 2)   # 命中 = 2, 不中 = 0
    return contribs


def compute_segment_signals(persona_name: str, persona_idx: int,
                            clusters: list, rate_matrix: list,
                            signals: dict, themes: dict) -> dict:
    """单个 persona × 所有 pain clusters → M 个信号分。Cap 0.6 模拟 v0 review 尺度。"""
    if persona_idx >= len(rate_matrix):
        return {s: 0 for s in signals}
    rates = rate_matrix[persona_idx]

    sig_score = {s: 0.0 for s in signals}
    for c_idx, c in enumerate(clusters):
        if c_idx >= len(rates):
            continue
        rate_pct = float(rates[c_idx])
        contribs = cluster_to_signal_contrib(c.get("name", ""), c.get("samples", []),
                                              signals, themes)
        for sig, base_w in contribs.items():
            sig_score[sig] += (rate_pct / 100.0) * base_w

    # persona 名称匹配（弱信号）
    name_contribs = cluster_to_signal_contrib(persona_name, [], signals, themes)
    for sig, w in name_contribs.items():
        sig_score[sig] += w * 0.25

    return {s: min(v, 0.6) for s, v in sig_score.items()}


def load_personas_payload(decoded_path: str, default_variant: str, default_k: str) -> dict | None:
    """返回 {personas, persona_sizes, clusters, rate_matrix} 或 None。"""
    if not decoded_path:
        return None
    d = json.loads(Path(decoded_path).read_text())
    variants = d.get("variants", {})
    var = variants.get(default_variant) or next(iter(variants.values()), None)
    if not var:
        return None
    k_payloads = var.get("k_to_payload", {})
    payload = k_payloads.get(default_k) or next(iter(k_payloads.values()), None)
    return payload


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--persona-data", required=True, help="competitor pain decoded (contains personas)")
    p.add_argument("--reddit-data", help="optional Reddit pain decoded")
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--competitor-variant", default="v1")
    p.add_argument("--competitor-k", default="8")
    p.add_argument("--reddit-variant", default="v1")
    p.add_argument("--reddit-k", default="10")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    signals = config["signals"]
    themes = config["pain_themes"]

    rows = []

    # Competitor 端
    comp_payload = load_personas_payload(args.persona_data, args.competitor_variant, args.competitor_k)
    if comp_payload:
        personas = comp_payload.get("personas", [])
        sizes = comp_payload.get("persona_sizes", {})
        clusters = comp_payload.get("clusters", [])
        rates = comp_payload.get("rate_matrix", [])
        print(f"竞品: {len(personas)} personas × {len(clusters)} pain clusters")
        for i, p_name in enumerate(personas):
            n = sizes.get(p_name, 0)
            sigs = compute_segment_signals(p_name, i, clusters, rates, signals, themes)
            rows.append({
                "source": "competitor",
                "segment": f"[Comp] {p_name}",
                "n_reviews": n,
                **{s: sigs[s] for s in signals},
            })

    # Reddit 端
    if args.reddit_data:
        red_payload = load_personas_payload(args.reddit_data, args.reddit_variant, args.reddit_k)
        if red_payload:
            personas = red_payload.get("personas", [])
            sizes = red_payload.get("persona_sizes", {})
            clusters = red_payload.get("clusters", [])
            rates = red_payload.get("rate_matrix", [])
            print(f"Reddit: {len(personas)} personas × {len(clusters)} pain clusters")
            for i, p_name in enumerate(personas):
                n = sizes.get(p_name, 0)
                sigs = compute_segment_signals(p_name, i, clusters, rates, signals, themes)
                rows.append({
                    "source": "reddit",
                    "segment": f"[Reddit] {p_name}",
                    "n_reviews": n,
                    **{s: sigs[s] for s in signals},
                })

    df = pd.DataFrame(rows)
    if df.empty:
        print("⚠ 无可用 persona × cluster 数据，无法生成 segment_pricing_summary")
        return
    df["segment_share"] = df["n_reviews"] / df["n_reviews"].sum()

    col_order = ["source", "segment", "n_reviews", "segment_share"] + list(signals.keys())
    df = df[col_order]
    df.to_csv(out_dir / "segment_pricing_summary.csv", index=False)
    print(f"\n→ {out_dir / 'segment_pricing_summary.csv'} ({len(df)} segments)")


if __name__ == "__main__":
    main()
