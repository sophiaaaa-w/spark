"""补召回：跑第二轮名额没排上的那几个词，追加到已有数据里。

跑法：
    python3 scripts/recall3.py @wavytalkofficial

只跑还没搜过的词，不重复付费。结果写入 recall3_<handle>.json，
和前两轮合并后重新过漏斗。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, funnel                        # noqa: E402
from app.apify import Apify                                # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def used_terms(handle: str) -> set[str]:
    out = set()
    for n in (f"recall_{handle}.json", f"recall2_{handle}.json",
              f"recall3_{handle}.json"):
        p = FIX / n
        if not p.exists():
            continue
        for r in json.loads(p.read_text()):
            if r.get("searchQuery"):
                out.add("kw:" + r["searchQuery"])
            h = r.get("searchHashtag")
            if h:
                out.add("tag:" + (h if isinstance(h, str) else h.get("name", "")))
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--per-run", type=int, default=C.RECALL2_ITEMS_PER_RUN)
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    d = json.loads((FIX / f"brand_{handle}.json").read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    terms = json.loads((FIX / f"terms_{handle}.json").read_text())
    done = used_terms(handle)

    payloads = []
    for t in terms:
        if not t["use"]:
            continue
        key = ("tag:" + t["value"]) if t["kind"] == "hashtag" else ("kw:" + t["value"])
        if key in done:
            continue
        if t["kind"] == "hashtag":
            payloads.append((f"#{t['value']}",
                             {"hashtags": [t["value"]],
                              "resultsPerPage": args.per_run,
                              "shouldDownloadSubtitles": True}))
        else:
            payloads.append((t["value"],
                             {"searchQueries": [t["value"]],
                              "resultsPerPage": args.per_run,
                              "shouldDownloadSubtitles": True}))

    if not payloads:
        sys.exit("没有未搜过的词了")

    print("=" * 74)
    print(f"补召回　{brand.nickname}（@{handle}）")
    print("=" * 74)
    print(f"\n{len(payloads)} 路 × {args.per_run} 条，"
          f"预估 ${len(payloads)*args.per_run*1.7/1000:.2f}\n")
    for label, _ in payloads:
        print(f"  · {label}")

    api = Apify()
    n = {"i": 0}

    def tick(label, cnt):
        n["i"] += 1
        print(f"  [{n['i']}/{len(payloads)}] {label:<36} {cnt:>4} 条")

    print("\n开跑…")
    t0 = time.time()
    res = await api.run_batch(payloads, on_done=tick)
    new = [x for items in res.values() for x in items]
    print(f"\n新增 {len(new)} 条，耗时 {time.time()-t0:.0f}s")
    (FIX / f"recall3_{handle}.json").write_text(json.dumps(new, ensure_ascii=False))

    # ---- 合并后重跑漏斗 ----
    raws = []
    for f in (f"recall_{handle}.json", f"recall2_{handle}.json",
              f"recall3_{handle}.json"):
        raws += json.loads((FIX / f).read_text())
    videos = dedupe(parse_many(raws))
    st = FunnelStats(recalled=len(raws))
    kept = funnel.hard_filter(videos, brand, window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=st)
    ranked = funnel.final_rank(kept)

    print("\n" + "=" * 74)
    print(f"三轮合计 {len(raws)} 条 → 去重 {len(videos)} 条唯一视频")
    print("=" * 74)
    base = max(st.after_dedupe, 1)
    for name, v in [("去重后", st.after_dedupe), ("剔除图文帖", st.after_slideshow),
                    (f"只留 {'/'.join(sorted(C.ALLOWED_LANGUAGES))}", st.after_language),
                    ("时长 10-90s", st.after_duration), ("近 30 天", st.after_window),
                    ("播放 ≥10k", st.after_plays),
                    (f"互动率 ≥{C.MIN_ENGAGEMENT_RATE:.0%}", st.after_engagement),
                    ("relevance≥3", st.after_relevance),
                    ("剔除官号", st.after_official)]:
        print(f"  {name:<18}{v:>5}  {'█'*int(30*v/base)}")

    print(f"\n  过硬门槛 {len(kept)} 条 → 每作者≤2 取 {len(ranked)} 条")
    if len(ranked) >= C.TOP_N:
        print(f"  ✅ 凑满 Top {C.TOP_N}")
    else:
        print(f"  ⚠️  差 {C.TOP_N - len(ranked)} 条")


if __name__ == "__main__":
    asyncio.run(main())
