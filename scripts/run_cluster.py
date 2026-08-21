"""拿排好序的 Top N 跑聚类，输出 pattern。

跑法：
    python3 scripts/run_cluster.py @wavytalkofficial

依赖 recall2.py 存下的 ranked_*.json（不重新召回）。
成本：只有一次 Claude 调用，约 $0.2。

输出的每个 pattern 带两个数字：
    占比        品牌推得多不多
    ER 中位数   观众买不买账
两者交叉才有判断价值。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cluster, config as C, funnel               # noqa: E402
from app import subtitles as subs                          # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    bpath = FIX / f"brand_{handle}.json"
    if not bpath.exists():
        sys.exit(f"找不到 {bpath.name}")
    d = json.loads(bpath.read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})

    raws = []
    for name in (f"recall_{handle}.json", f"recall2_{handle}.json"):
        p = FIX / name
        if p.exists():
            raws += json.loads(p.read_text())
    if not raws:
        sys.exit("找不到召回数据")

    kept = funnel.hard_filter(dedupe(parse_many(raws)), brand,
                              window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=FunnelStats())
    ranked = funnel.final_rank(kept)

    print("=" * 74)
    print(f"聚类　{brand.nickname}（@{handle}）")
    print("=" * 74)
    print(f"\n过硬门槛 {len(kept)} 条 → 排序取 Top {len(ranked)} 条"
          f"，涉及 {len({v.author.username for v in ranked})} 个账号")

    print("\n下载字幕…")
    cues = asyncio.run(subs.fetch_many(ranked))
    texts = {vid: subs.plain_text(c) for vid, c in cues.items() if c}
    print(f"  {len(texts)}/{len(ranked)} 条有口播")

    print("\n调用 Claude…")
    t0 = time.time()
    result = cluster.run(ranked, texts, brand=brand.nickname,
                         category_hint=d.get("bio", ""))
    print(f"  完成（{time.time()-t0:.0f}s）")

    print("\n" + "=" * 74)
    print(f"品类：{result.get('category')}　"
          f"{len(result['patterns'])} 个 pattern　"
          f"{result['unclustered_count']} 条未归类")
    print("=" * 74)

    for p in result["patterns"]:
        marks = []
        if p.get("highest_lift"):
            marks.append("⚡ 少有人做但一做就灵")
        if p.get("underperforms"):
            marks.append("⚠ 大家都在拍但观众不买账")
        if p.get("thin_evidence"):
            marks.append("· 样本支撑较薄")
        print(f"\n{'─' * 74}")
        print(f"0{p['rank']}  {p['move_name']}"
              + (("   " + "  ".join(marks)) if marks else ""))
        print(f"{'─' * 74}")
        print(f"  占比 {p['share_count']}/{p['share_total']} 条"
              f"　　ER 中位 {p['median_engagement']:.1%}"
              f"　　播放中位 {p['median_plays']:,}")
        print(f"\n为什么有效：\n  {p['why_it_works']}")
        print("\n真实原话：")
        for h in p.get("hook_examples", []):
            print(f"  · 「{h['quote']}」")

    if result.get("dropped_patterns"):
        print(f"\n被丢弃（支撑不足 {C.MIN_VIDEOS_PER_PATTERN} 条）：")
        for p in result["dropped_patterns"]:
            print(f"  · {p['move_name']}  仅 {p['share_count']} 条")

    print(f"\n{'=' * 74}")
    print("逐条打标")
    print("=" * 74)
    by_id = {v.id: v for v in ranked}
    for a in result.get("assignments", []):
        v = by_id.get(a["video_id"])
        if not v:
            continue
        tag = f"0{a['pattern_id']}" if a.get("pattern_id") else " —"
        print(f"  {tag}  {v.plays:>9,} {v.engagement_rate:>6.1%}  "
              f"@{v.author.username[:20]:<20} {a['evidence'][:70]}")

    (FIX / f"result_{handle}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n已存 fixtures/result_{handle}.json")


if __name__ == "__main__":
    main()
