"""按 hook / body / CTA 三段拆解，输出共性 + 卖点 + 视频索引。

跑法：
    python3 scripts/run_breakdown.py @wavytalkofficial

依赖 recall*_<handle>.json（已落盘），**不重新召回**。
成本：一次 Claude 调用，约 $0.3。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import aggregate, breakdown, config as C, frames, funnel   # noqa: E402
from app import subtitles as subs                           # noqa: E402
from app.funnel import BrandRef, FunnelStats                # noqa: E402
from app.mining import Term                                 # noqa: E402
from app.models import dedupe, parse_many                   # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def load(handle: str):
    d = json.loads((FIX / f"brand_{handle}.json").read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    raws = []
    for n in (f"recall_{handle}.json", f"recall2_{handle}.json"):
        p = FIX / n
        if p.exists():
            raws += json.loads(p.read_text())
    kept = funnel.hard_filter(dedupe(parse_many(raws)), brand,
                              window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=FunnelStats())
    ranked = funnel.final_rank(kept)

    terms = []
    tp = FIX / f"terms_{handle}.json"
    if tp.exists():
        for t in json.loads(tp.read_text()):
            v = t["value"]
            # 关键词形态是 "wavytalk thermal brush"，剥掉品牌名只留产品名
            if t["kind"] == "keyword":
                v = v.lower().replace(brand.nickname.lower(), "").strip()
            else:
                v = v.replace(brand.hashtag.lstrip("#"), "").strip()
            if len(v) >= 4:
                terms.append(v)
    return brand, d.get("bio", ""), ranked, sorted(set(terms), key=len, reverse=True)


def show(b: dict) -> None:
    W = 78
    print("\n" + "=" * W)
    print(f"品类 {b['category']}　·　{b['total_videos']} 条视频"
          f"　·　hook 时长中位 {b.get('median_hook_seconds')}s")
    print("=" * W)

    def head(c) -> None:
        mark = {True: "✓", False: "⚠ 非逐字"}.get(c.get("quote_verified"), "")
        print(f"\n  {c['name']}　　{c['count']}/{c['total']} 条"
              f"　ER中位 {c.get('median_engagement', 0):.1%}"
              f"　播放中位 {c.get('median_plays', 0):,}")
        print(f"    {c['description']}")
        if c.get("quote"):
            print(f"    「{c['quote'][:76]}」 {mark}")

    for key, title in (("hooks", "HOOK　前几秒怎么抓人"),
                       ("ctas", "CTA　结尾让观众做什么")):
        print(f"\n\n{'─' * W}\n{title}"
              f"　（一条视频可归入多个类型，占比不互斥）\n{'─' * W}")
        for c in b.get(key) or []:
            head(c)

    print(f"\n\n{'─' * W}\nBODY　中间怎么组织　+　各自高频提到的卖点\n{'─' * W}")
    if len(b.get("products") or []) > 1:
        print("  产品分布　" + "　·　".join(
            f"{p['product']} {p['video_count']} 条" for p in b["products"]))
    for c in b.get("bodies") or []:
        head(c)
        for g in c.get("by_product", []):
            label = f"{g['product']}（{g['video_count']} 条）" if len(
                c.get("by_product", [])) > 1 else "高频卖点"
            names = "　·　".join(sp["name"] for sp in g["selling_points"])
            print(f"      {label}\n        {names}")

    print(f"\n\n{'─' * W}\n视频索引\n{'─' * W}")
    print(f"  {'播放':>10} {'ER':>6}  {'hook':<26}{'body':<22}CTA")
    for r in b["index"]:
        print(f"  {r['plays']:>10,} {r['engagement_rate']:>5.1%}  "
              f"{(r['hook'] or ['—'])[0][:24]:<26}"
              f"{(r['body'] or ['—'])[0][:20]:<22}"
              f"{(r['cta'] or ['—'])[0][:22]}")

    if b.get("unverified_quotes"):
        print(f"\n⚠️ 有 {len(b['unverified_quotes'])} 句 quote 不是逐字原话：")
        for x in b["unverified_quotes"][:5]:
            print(f"    {x}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    brand, bio, videos, terms = load(handle)
    print("=" * 78)
    print(f"分段拆解　{brand.nickname}（@{handle}）")
    print("=" * 78)
    print(f"\n{len(videos)} 条视频，{len({v.author.username for v in videos})} 个账号")
    print(f"产品词表（用于 body 分组）：{', '.join(terms[:8]) or '（无）'}")

    print("\n下载字幕…")
    cues = asyncio.run(subs.fetch_many(videos))
    text = {k: subs.plain_text(v) for k, v in cues.items() if v}
    print(f"  {len(text)}/{len(videos)} 条有口播"
          f"　→ 另外 {len(videos)-len(text)} 条只能靠画面判断")

    missing = frames.check_tools()
    if missing:
        sys.exit(f"缺少 {', '.join(missing)}，装一下：brew install {' '.join(missing)}")

    print(f"\n下载视频并抽前 3 秒的帧（{len(videos)} 条）…")
    t0 = time.time()

    def prog(done, total, v, ok):
        if done % 10 == 0 or done == total:
            print(f"  {done}/{total}")

    hook_frames = asyncio.run(frames.build_hook_frames(videos, on_progress=prog))
    n_fr = sum(len(f) for f in hook_frames.values())
    print(f"  {len(hook_frames)}/{len(videos)} 条成功，共 {n_fr} 帧"
          f"（{time.time()-t0:.0f}s）")

    tags = aggregate.tag_products(videos, aggregate.clean_product_terms(terms), text)
    print("\n调用 Claude（含 {} 张图）…".format(n_fr))
    t0 = time.time()
    raw = breakdown.run(videos, cues, tags, hook_frames,
                        brand=brand.nickname, bio=bio)
    print(f"  完成（{time.time() - t0:.0f}s）")

    built = aggregate.build(raw, videos, product_terms=terms, subtitle_text=text)
    built = aggregate.verify_quotes(built, text)
    show(built)

    (FIX / f"breakdown_{handle}.json").write_text(
        json.dumps({"built": built, "raw": raw}, ensure_ascii=False, indent=2))
    print(f"\n已存 fixtures/breakdown_{handle}.json")


if __name__ == "__main__":
    main()
