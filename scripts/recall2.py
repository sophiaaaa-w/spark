"""第二轮召回：用挖出来的词扩量，然后跑完整漏斗和排序。

跑法：
    python3 scripts/recall2.py @wavytalkofficial

依赖 mine_terms.py 生成的 terms_<handle>.json（"use": true 的那些）。
和第一轮的结果合并去重后，跑严格漏斗 + 加权排序，看能不能凑满 Top 50。

成本 ≈ 路数 × 每路条数 × $1.7/1000。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, funnel, mining                # noqa: E402
from app.apify import Apify                                # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.mining import Term                                # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def load(handle: str):
    b = FIX / f"brand_{handle}.json"
    t = FIX / f"terms_{handle}.json"
    r = FIX / f"recall_{handle}.json"
    for p in (b, t, r):
        if not p.exists():
            sys.exit(f"找不到 {p.name}，先跑 probe_brand.py / mine_terms.py")
    d = json.loads(b.read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    terms = [Term(**x) for x in json.loads(t.read_text())]
    return brand, d.get("bio", ""), terms, json.loads(r.read_text())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--per-run", type=int, default=C.RECALL2_ITEMS_PER_RUN)
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    brand, bio, terms, round1 = load(handle)
    payloads = mining.selected_payloads(terms, per_run=args.per_run)
    if not payloads:
        sys.exit("terms 文件里没有 use=true 的词")

    print("=" * 74)
    print(f"第二轮召回　{brand.nickname}（@{handle}）")
    print("=" * 74)
    print(f"\n{len(payloads)} 路 × {args.per_run} 条，"
          f"并发上限 {C.RECALL2_CONCURRENCY}，"
          f"预估 ${len(payloads)*args.per_run*1.7/1000:.2f}\n")
    for label, _ in payloads:
        print(f"  · {label}")

    api = Apify()
    done = {"n": 0}

    def tick(label: str, n: int) -> None:
        done["n"] += 1
        print(f"  [{done['n']}/{len(payloads)}] {label:<40} {n:>4} 条")

    print("\n开跑…")
    t0 = time.time()
    results = await api.run_batch(payloads, on_done=tick)
    round2 = [x for items in results.values() for x in items]
    print(f"\n第二轮 {len(round2)} 条，耗时 {time.time()-t0:.0f}s")

    (FIX / f"recall2_{handle}.json").write_text(
        json.dumps(round2, ensure_ascii=False))

    # ---------------------------------------------------------------- 合并
    merged = round1 + round2
    videos = dedupe(parse_many(merged))
    print(f"\n两轮合计 {len(merged)} 条 → 去重后 {len(videos)} 条唯一视频")
    print(f"  （第一轮单独去重是 {len(dedupe(parse_many(round1)))} 条，"
          f"第二轮净增 {len(videos)-len(dedupe(parse_many(round1)))} 条）")

    # ---------------------------------------------------------------- 漏斗
    st = FunnelStats(recalled=len(merged))
    kept = funnel.hard_filter(videos, brand, window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=st)
    print("\n" + "=" * 74)
    print("漏斗（严格条件，不放宽）")
    print("=" * 74)
    base = max(st.after_dedupe, 1)
    for name, n in [("去重后", st.after_dedupe), ("剔除图文帖", st.after_slideshow),
                    ("只留英文/未知", st.after_language), ("时长 10-90s", st.after_duration),
                    ("近 30 天", st.after_window),
                    (f"播放 ≥{C.MIN_PLAYS//1000}k", st.after_plays),
                    (f"互动率 ≥{C.MIN_ENGAGEMENT_RATE:.0%}", st.after_engagement),
                    ("relevance≥3", st.after_relevance),
                    ("剔除官号", st.after_official)]:
        print(f"  {name:<18}{n:>5}  {'█'*int(30*n/base)}")
    print(f"\n  产出率 {len(kept)}/{base} = {len(kept)/base:.1%}")

    # ---------------------------------------------------------------- 排序
    ranked = funnel.final_rank(kept)
    accounts = {v.author.username for v in ranked}
    subs = sum(1 for v in ranked if v.has_subtitles)

    print("\n" + "=" * 74)
    print("结论")
    print("=" * 74)
    print(f"  过硬门槛            {len(kept)} 条")
    print(f"  每作者≤2条后排序取   {len(ranked)} 条")
    print(f"  涉及账号            {len(accounts)} 个")
    print(f"  字幕覆盖            {subs}/{len(ranked)}"
          f"{f' = {subs/len(ranked):.0%}' if ranked else ''}")
    if len(ranked) >= C.TOP_N:
        print(f"\n  ✅ 凑满 Top {C.TOP_N}")
    else:
        print(f"\n  ⚠️  只有 {len(ranked)} 条，离 Top {C.TOP_N} 差 "
              f"{C.TOP_N-len(ranked)} 条")

    print(f"\n  Top 20（加权得分 = 0.7 播放 + 0.2 互动率 + 0.1 播放粉丝比）")
    print(f"  {'得分':>6}{'播放':>11}{'互动率':>8}{'播放/粉丝':>10}{'字幕':>5}  账号")
    for v in ranked[:20]:
        print(f"  {v.score:>6.3f}{v.plays:>11,}{v.engagement_rate:>8.1%}"
              f"{v.plays_per_follower:>10.1f}{'有' if v.has_subtitles else '—':>5}"
              f"  @{v.author.username}")

    (FIX / f"ranked_{handle}.json").write_text(json.dumps(
        [{"id": v.id, "url": v.url, "score": v.score, "plays": v.plays,
          "engagement_rate": round(v.engagement_rate, 4),
          "plays_per_follower": round(v.plays_per_follower, 2),
          "author": v.author.username, "followers": v.author.followers,
          "duration": v.duration, "has_subtitles": v.has_subtitles,
          "caption": v.caption} for v in ranked],
        ensure_ascii=False, indent=2))
    print(f"\n已存 fixtures/ranked_{handle}.json")


if __name__ == "__main__":
    asyncio.run(main())
