"""花几毛钱判断一个品牌值不值得跑全量。

为什么不是「数 20 条里几条过关」：
    实测过关率 WavyTalk 2.8%、dr dent 0.13%。20 条样本里期望过关分别是
    0.55 条和 0.03 条 —— 两个都约等于 0，分辨不出好坏。
    稀有事件在 n=20 上没有统计效力。

所以改成测**分布**：中位数和比例在 n=20 上是稳的。
下面三个指标就是 dr dent 栽掉的地方，提前 30 秒就能看出来。

跑法：
    python3 scripts/probe_stats.py momcozy
    python3 scripts/probe_stats.py momcozy "glow recipe" cerave   # 一次比几个
"""
from __future__ import annotations

import asyncio
import re
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C                                  # noqa: E402
from app.apify import Apify                                  # noqa: E402
from app.funnel import BrandRef                              # noqa: E402

PER_RUN = 20

# WavyTalk 的 recall1（1,175 条原始）实测值，作为「这个品牌能出 47 条」的参照。
# inbody 那项取自最终 47 条的实测（85%），momcozy 同口径只有 59%。
REF = {"median": 44_800, "over10k": 0.66, "recent": 0.37, "en": 0.67,
       "inbody": 0.85}


def in_body(caption: str, token: str) -> bool:
    """把 hashtag 块剥掉之后，品牌名是否还出现在正文里。

    这是「视频真的在讲这个产品」的廉价代理。反例来自 momcozy：
        "Baby, you danced terribly and I loved every second.#momcozy#momcozylife..."
    情感向内容挂一串品牌标签就能蹭流量，播放还特别高（那条 2.3M），
    于是全冲进 TOP —— 但对「我该怎么拍」这个问题毫无参考价值。

    品类决定这个比例：健身器械、美发工具必须把产品演示出来；
    母婴这种身份认同型内容池则充斥着标签齐全但内容无关的视频。
    """
    body = re.sub(r"#\S+", " ", caption or "")
    return token in re.sub(r"[^a-z0-9]", "", body.lower())


async def check(name: str) -> dict:
    brand = BrandRef.from_brand_name(name)
    items = await Apify().run(
        {"searchQueries": [brand.nickname], "resultsPerPage": PER_RUN,
         "shouldDownloadSubtitles": False},
        label=f"probe:{name}",
    )
    if not items:
        return {"name": name, "n": 0}

    now = time.time()
    plays = sorted(i.get("playCount") or 0 for i in items)
    return {
        "name": name,
        "n": len(items),
        "median": st.median(plays),
        "over10k": sum(1 for p in plays if p >= C.MIN_PLAYS) / len(plays),
        "recent": sum(1 for i in items
                      if now - (i.get("createTime") or 0) < C.WINDOW_DAYS * 86400) / len(items),
        "en": sum(1 for i in items
                  if (i.get("textLanguage") or "") == "en") / len(items),
        "inbody": sum(1 for i in items
                      if in_body(i.get("text") or "", brand.token)) / len(items),
        "items": items,
        "token": brand.token,
    }


def verdict(r: dict) -> str:
    """产量看三项、相关性看一项，两个维度分开判 —— 它们是两种不同的失败。

    dr dent 死在产量（近期高播放内容太少，最终 2 条）。
    momcozy 产量没问题（29 条），死在相关性（一半是挂标签的情感向内容）。
    """
    if not r.get("n"):
        return "✗ 一条都没搜到，换词或换品牌"

    yield_hits = sum([r["median"] >= REF["median"] * 0.5,
                      r["over10k"] >= REF["over10k"] * 0.5,
                      r["recent"] >= REF["recent"] * 0.5])
    y = {3: "产量稳", 2: "产量够", 1: "产量悬",
         0: "产量不行（会像 dr dent 只出个位数）"}[yield_hits]

    if r["inbody"] >= 0.75:
        rel = "内容对口"
    elif r["inbody"] >= 0.55:
        rel = "混入蹭标签内容（momcozy 是 59%）"
    else:
        rel = "大量蹭标签内容"

    mark = "✓" if yield_hits >= 2 and r["inbody"] >= 0.75 else (
        "⚠" if yield_hits >= 2 or r["inbody"] >= 0.75 else "✗")
    return f"{mark} {y} · {rel}"


async def main() -> None:
    show = "--show" in sys.argv
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        sys.exit(__doc__)

    # 每个参数是一个品牌。多词品牌名不加引号会被 shell 拆开，
    # 于是 "mellow sleep" 变成 mellow 和 sleep 两次探测，钱花了却什么都没测到。
    # 所以先把解析结果回显出来。
    print(f"\n将检查 {len(names)} 个品牌：" + " / ".join(f"「{n}」" for n in names))
    if any(" " not in n for n in names) and len(names) > 1:
        print("（多词品牌名记得加引号：probe_stats.py \"mellow sleep\"）")

    rows = await asyncio.gather(*(check(n) for n in names))

    if show:
        # 指标只是筛子，不是判决。momcozy 那次是逐条读文案才确认低分对应的
        # 确实是无关内容 —— 换个品类可能只是「说了产品但没念品牌名」，
        # 那种内容其实是对口的。所以下结论之前先用眼睛看一遍。
        for r in rows:
            if not r.get("n"):
                continue
            print(f"\n{'='*88}\n{r['name']} 的 {r['n']} 条文案"
                  f"（✓ = 正文里提到了品牌，不只是 hashtag）\n{'='*88}")
            for it in r["items"]:
                cap = re.sub(r"\s+", " ", it.get("text") or "").strip()
                mark = "✓" if in_body(cap, r["token"]) else "·"
                print(f"{mark} {(it.get('playCount') or 0):>9,}  {cap[:110]}")

    print(f"\n每个品牌抓 {PER_RUN} 条，约占全量的 1%\n")
    head = (f"{'品牌':<16}{'回条':>5}{'播放中位数':>12}{'≥10k':>7}"
            f"{'近30天':>8}{'英文':>7}{'正文提品牌':>11}")
    print(head + "   判断")
    print("-" * 104)
    for r in rows:
        if not r.get("n"):
            print(f"{r['name']:<16}{0:>5}{'—':>12}{'—':>7}{'—':>8}{'—':>7}{'—':>11}"
                  f"   {verdict(r)}")
            continue
        print(f"{r['name']:<16}{r['n']:>5}{r['median']:>12,.0f}"
              f"{r['over10k']:>7.0%}{r['recent']:>8.0%}{r['en']:>7.0%}"
              f"{r['inbody']:>11.0%}   {verdict(r)}")
    print("-" * 104)
    print(f"{'WavyTalk 参照':<14}{'':>5}{REF['median']:>12,.0f}"
          f"{REF['over10k']:>7.0%}{REF['recent']:>8.0%}{REF['en']:>7.0%}"
          f"{REF['inbody']:>11.0%}   → 47 条，内容对口")
    print(f"{'momcozy 实测':<14}{'':>5}{'—':>12}{'—':>7}{'—':>8}{'—':>7}"
          f"{0.59:>11.0%}   → 29 条，但一半是蹭标签的")
    print()


if __name__ == "__main__":
    asyncio.run(main())
