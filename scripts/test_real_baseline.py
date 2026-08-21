"""用真实账号历史算基线倍数，然后拿真正的爆款重跑聚类。

跑法：
    python3 scripts/test_real_baseline.py @wavytalkofficial

依赖 probe_brand.py 存下的 recall_*.json 和 brand_*.json，不重新召回。
成本：账号历史 ≈ 账号数 × 25 × $1.7/1000，再加一次 Claude 聚类 $0.05。

这是第一次端到端验证「基线倍数」这个核心机制：
按播放量排 vs 按基线倍数排，两个榜单会差多少。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import baseline, cluster, config as C, db, funnel   # noqa: E402
from app import subtitles as subs                            # noqa: E402
from app.apify import Apify                                  # noqa: E402
from app.funnel import BrandRef, FunnelStats                 # noqa: E402
from app.models import dedupe, parse_many                    # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def load_brand(handle: str) -> tuple[BrandRef, str]:
    path = FIX / f"brand_{handle}.json"
    if not path.exists():
        sys.exit(f"找不到 {path.name}，先跑 probe_brand.py @{handle}")
    d = json.loads(path.read_text())
    return BrandRef(
        username=d["username"], author_id=d["author_id"],
        nickname=d["nickname"], hashtag=d["hashtag"],
    ), d.get("bio", "")


def load_candidates(handle: str, brand: BrandRef):
    path = FIX / f"recall_{handle}.json"
    if not path.exists():
        sys.exit(f"找不到 {path.name}，先跑 probe_brand.py @{handle}")
    videos = dedupe(parse_many(json.loads(path.read_text())))
    stats = FunnelStats(recalled=len(videos))
    kept = funnel.hard_filter(videos, brand, window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=stats)
    return kept, stats


async def fetch_histories(usernames, since_ts):
    api = Apify()
    out, to_fetch = {}, []
    for u in usernames:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT author_id FROM author_meta WHERE username = ?", (u,)
            ).fetchone()
        cached = baseline.cache_read(row["author_id"]) if row else None
        if cached:
            out[u] = cached
        else:
            to_fetch.append(u)

    print(f"  缓存命中 {len(out)} 个，需抓 {len(to_fetch)} 个"
          f"（约 ${len(to_fetch)*25*1.7/1000:.2f}）")
    if not to_fetch:
        return out

    raw_map = await api.author_histories(to_fetch, since_ts=since_ts)
    for u, raws in raw_map.items():
        points = baseline.history_from_raw(raws)
        out[u] = points
        if raws:
            parsed = parse_many(raws[:1])
            if parsed:
                a = parsed[0].author
                baseline.cache_write(a.id, u, a.followers, points)
    got = sum(1 for v in out.values() if v)
    print(f"  {got}/{len(usernames)} 个账号拿到历史，"
          f"合计 {sum(len(v) for v in out.values())} 条")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    db.init()
    brand, bio = load_brand(handle)
    print("=" * 74)
    print(f"真实基线倍数：{brand.nickname}（@{handle}）")
    print("=" * 74)

    videos, stats = load_candidates(handle, brand)
    print(f"\n候选 {len(videos)} 条（严格条件，未放宽）")
    if not videos:
        sys.exit("没有候选")

    accounts = funnel.prescreen_accounts(videos)
    since = baseline.earliest_candidate_ts(videos)
    print(f"预筛 {len(accounts)} 个账号，历史回溯到 "
          f"{time.strftime('%Y-%m-%d', time.gmtime(since))}")

    print("\n抓账号历史…")
    t0 = time.time()
    histories = asyncio.run(fetch_histories(accounts, since))
    print(f"  耗时 {time.time()-t0:.0f}s")

    scored = baseline.apply_baselines(videos, histories)

    # ------------------------------------------------- 两个榜单的对比
    print("\n" + "=" * 74)
    print("按播放量排  vs  按基线倍数排　—— 这是整个产品的立论")
    print("=" * 74)
    by_plays = sorted(scored, key=lambda v: v.plays, reverse=True)[:10]
    by_mult = sorted(scored, key=lambda v: v.baseline_multiple or 0,
                     reverse=True)[:10]
    print(f"  {'按播放量':<34}｜  按基线倍数")
    print(f"  {'-'*33} ｜ {'-'*33}")
    for a, b in zip(by_plays, by_mult):
        left = f"{a.plays:>9,}  @{a.author.username[:18]}"
        right = f"{b.baseline_multiple:>7.1f}×  @{b.author.username[:18]}"
        print(f"  {left:<34}｜ {right}")

    overlap = len({v.id for v in by_plays} & {v.id for v in by_mult})
    print(f"\n  两个榜单 Top10 只重合 {overlap} 条"
          f" —— 重合越少，说明基线倍数越有必要")

    print("\n" + "=" * 74)
    print("真实基线明细（倍数降序，前 20）")
    print("=" * 74)
    print(f"  {'倍数':>8} {'播放':>11} {'账号中位':>11} {'粉丝':>11} {'置信':>4} 账号")
    for v in sorted(scored, key=lambda x: x.baseline_multiple or 0,
                    reverse=True)[:20]:
        flag = {"high": "高", "low": "低"}.get(v.baseline_confidence, "?")
        print(f"  {v.baseline_multiple:>7.1f}× {v.plays:>11,} "
              f"{v.baseline:>11,} {v.author.followers:>11,} {flag:>4} "
              f"@{v.author.username}")

    outliers = [v for v in scored if (v.baseline_multiple or 0) >= 1.5]
    print(f"\n  ★ {len(scored)}/{len(videos)} 条算出倍数"
          f"（{len(videos)-len(scored)} 条账号历史不足被剔除）")
    print(f"  ★ 其中 {len(outliers)} 条真的超出常态 1.5 倍以上")

    ranked = funnel.final_rank(outliers)
    print(f"  ★ 终排序后进入分析：{len(ranked)} 条")

    if len(ranked) < C.MIN_VIDEOS_PER_PATTERN:
        sys.exit("\n  样本太少，跳过聚类。")

    print("\n下载字幕…")
    cues = asyncio.run(subs.fetch_many(ranked))
    texts = {vid: subs.plain_text(c) for vid, c in cues.items() if c}
    print(f"  {len(texts)}/{len(ranked)} 条有口播")

    print("\n调用 Claude 聚类…")
    t0 = time.time()
    result = cluster.run(ranked, texts, brand=brand.nickname, category_hint=bio)
    print(f"  完成（{time.time()-t0:.0f}s）")

    print("\n" + "=" * 74)
    print(f"品类：{result.get('category')}　"
          f"{len(result['patterns'])} 个 pattern　"
          f"{result['unclustered_count']} 条未归类")
    print("=" * 74)
    for p in result["patterns"]:
        marks = []
        if p.get("highest_lift"):
            marks.append("⚡ 少有人用但一用就爆")
        if p.get("thin_evidence"):
            marks.append("⚠ 样本支撑较薄")
        print(f"\n{'─' * 74}")
        print(f"0{p['rank']}  {p['move_name']}"
              + (("   " + " · ".join(marks)) if marks else ""))
        print(f"{'─' * 74}")
        print(f"命中 {p['share_count']}/{p['share_total']} 条"
              f"   真实倍数中位数 {p.get('median_multiple')}×")
        print(f"\n为什么有效：\n  {p['why_it_works']}")
        print("\n真实原话：")
        for h in p.get("hook_examples", []):
            print(f"  · 「{h['quote']}」")

    if result.get("dropped_patterns"):
        print(f"\n被丢弃（支撑不足 {C.MIN_VIDEOS_PER_PATTERN} 条）：")
        for p in result["dropped_patterns"]:
            print(f"  · {p['move_name']}  仅 {p['share_count']} 条")

    (FIX / f"result_{handle}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n结果已存 fixtures/result_{handle}.json")


if __name__ == "__main__":
    main()
