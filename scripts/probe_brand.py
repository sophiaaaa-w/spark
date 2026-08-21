"""品牌样本量探测 —— 换品牌时跑这个，不用再写新脚本。

跑法：
    python3 scripts/probe_brand.py @wavytalkofficial
    python3 scripts/probe_brand.py @wavytalkofficial --per-run 400
    python3 scripts/probe_brand.py @wavytalkofficial --hashtag wavytalk

它做四件事：
  1. 解析 handle，拿 nickname / bio / 粉丝数
  2. 四路并行召回
  3. 在「不放宽」的严格条件下（30 天 + 播放 >10k）跑漏斗
  4. 回答一个问题：这个品牌够不够凑出 Top N

成本 ≈ 召回条数 × $1.7/1000。默认 4×400 = 1600 条 ≈ $2.7。
结果存进 fixtures/，后续测试离线复用不再花钱。
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, funnel                      # noqa: E402
from app.apify import Apify                              # noqa: E402
from app.funnel import BrandRef, FunnelStats             # noqa: E402
from app.models import dedupe, parse_many                # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


# 品牌账号名里常见的后缀，做关键词/标签时必须剥掉。
# 实测：@wavytalkofficial 的 nickName 字段就是 "wavytalkofficial"，
# 直接拿去搜等于空转 —— 没人在 caption 里写 "wavytalkofficial"。
_SUFFIXES = ("official", "officiel", "shop", "store", "hq", "global",
             "us", "usa", "uk", "eu", "beauty", "hair", "cosmetics", "inc")


def strip_suffix(token: str) -> str:
    """剥掉品牌名后缀，但不能剥到只剩三四个字母。"""
    cur = token
    for _ in range(3):                      # 可能叠了两层，如 wavytalkofficialus
        for suf in _SUFFIXES:
            if cur.endswith(suf) and len(cur) - len(suf) >= 5:
                cur = cur[: -len(suf)]
                break
        else:
            break
    return cur


def derive_terms(nickname: str, username: str) -> tuple[str, str]:
    """推导 (关键词, hashtag)。猜错很正常，所以命令行可以覆盖。

    两条实测教训：
      · @colorwow.hair 的真实标签是 #colorwow，不是 #colorwowhair 也不是
        #colorwow.hair —— 从 handle 推导不出来
      · @wavytalkofficial 的 nickName 就等于 handle，不剥后缀就是空转
    """
    import re
    nick_raw = (nickname or "").strip()
    nick = re.sub(r"[^a-z0-9]", "", nick_raw.lower())
    user = re.sub(r"[^a-z0-9]", "", (username or "").lower())

    # nickName 和 handle 一样，说明这个字段没填有意义的显示名
    if not nick or nick == user:
        base = strip_suffix(user)
        return base, base

    base = strip_suffix(nick)
    # 显示名有空格且剥完后仍够长时，关键词保留空格形式（caption 里就是这么写的）
    keyword = nick_raw if " " in nick_raw and len(base) >= 5 else base
    return keyword, base


def print_funnel(stats: FunnelStats, kept: int, label: str) -> None:
    base = max(stats.after_dedupe, 1)
    rows = [
        ("去重后", stats.after_dedupe),
        ("剔除图文帖", stats.after_slideshow),
        ("只留英文/未知", stats.after_language),
        ("时长 10-90s", stats.after_duration),
        ("时间窗内", stats.after_window),
        ("播放门槛", stats.after_plays),
        ("互动率 ≥1.5%", stats.after_engagement),
        ("relevance>=3", stats.after_relevance),
        ("剔除官号", stats.after_official),
    ]
    print(f"\n  {label}")
    for name, n in rows:
        bar = "█" * int(30 * n / base)
        print(f"    {name:<16}{n:>5}  {bar}")
    print(f"    产出率 {kept}/{base} = {kept/base:.1%}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--per-run", type=int, default=C.RECALL_ITEMS_PER_RUN)
    ap.add_argument("--hashtag", default=None, help="覆盖自动推导的 hashtag")
    ap.add_argument("--nickname", default=None, help="覆盖账号显示名")
    args = ap.parse_args()

    handle = args.handle.lstrip("@")
    FIX.mkdir(exist_ok=True)
    api = Apify()

    # ---------------------------------------------------------------- 1. 解析
    print("=" * 70)
    print(f"品牌样本量探测：@{handle}")
    print("=" * 70)
    print("\n[1/3] 解析账号…")
    meta = await api.resolve_profile(handle)
    if not meta:
        sys.exit(f"解析不到 @{handle}，检查拼写")

    raw_nick = meta.get("nickName") or handle
    auto_keyword, auto_tag = derive_terms(raw_nick, handle)
    nickname = args.nickname or auto_keyword
    hashtag = args.hashtag or auto_tag
    brand = BrandRef(
        username=handle,
        author_id=str(meta.get("id") or ""),
        nickname=nickname,
        hashtag=hashtag,
    )
    print(f"  账号显示名  {raw_nick}")
    print(f"  粉丝      {int(meta.get('fans') or 0):,}")
    print(f"  发布数    {int(meta.get('video') or 0):,}")
    print(f"  简介      {(meta.get('signature') or '')[:80]}")
    print(f"\n  → 关键词搜索用  \"{nickname}\"")
    print(f"  → hashtag 用    #{hashtag}")
    print(f"  → 官号剔除 token  {brand.token}")

    # ---------------------------------------------------------------- 2. 召回
    print(f"\n[2/3] 四路并行召回，每路 {args.per_run} 条"
          f"（预估 ${args.per_run*4*1.7/1000:.2f}）…")
    t0 = time.time()
    raws = await api.recall(
        nickname=nickname, hashtag=hashtag,
        username=handle, per_run=args.per_run,
    )
    print(f"  合计 {len(raws)} 条，耗时 {time.time()-t0:.0f}s")
    if not raws:
        sys.exit("召回为空")

    out = FIX / f"recall_{handle}.json"
    out.write_text(json.dumps(raws, ensure_ascii=False))
    print(f"  已存 {out.name}（{out.stat().st_size/1e6:.1f} MB）")

    # ---------------------------------------------------------------- 3. 漏斗
    print(f"\n[3/3] 漏斗（严格条件，不放宽）")
    videos = dedupe(parse_many(raws))

    strict = FunnelStats(recalled=len(raws))
    kept = funnel.hard_filter(videos, brand, window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=strict)
    print_funnel(strict, len(kept), f"30 天 + 播放 >{C.MIN_PLAYS:,}")

    # ---------------------------------------------------------------- 结论
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)
    accounts = {v.author.username for v in kept}
    subs = sum(1 for v in kept if v.has_subtitles)

    print(f"  严格条件下候选      {len(kept)} 条")
    print(f"  涉及账号            {len(accounts)} 个")
    print(f"  字幕覆盖            {subs}/{len(kept)}"
          f"{f' = {subs/len(kept):.0%}' if kept else ''}")
    print(f"  目标 Top N          {C.TOP_N}")

    if len(kept) >= C.TOP_N:
        print(f"\n  ✅ 够了。不用放宽门槛就能凑出 Top {C.TOP_N}。")
    elif len(kept) >= C.MIN_VIDEOS_PER_PATTERN * C.MAX_PATTERNS:
        need = int(len(raws) * C.TOP_N / max(len(kept), 1))
        print(f"\n  ⚠️  {len(kept)} 条，够聚类但填不满 Top {C.TOP_N}。")
        print(f"     要凑满需召回约 {need} 条（约 ${need*1.7/1000:.2f}）：")
        print(f"     python3 scripts/probe_brand.py @{handle} "
              f"--per-run {need//4}")
    else:
        print(f"\n  ❌ 只有 {len(kept)} 条，这个品牌 UGC 太稀疏。")
        print("     要么换品牌，要么降播放门槛。")

    if kept:
        print(f"\n  播放量分布（前 15 条）")
        for v in sorted(kept, key=lambda x: x.plays, reverse=True)[:15]:
            print(f"    {v.plays:>10,}  {v.duration:>3}s  "
                  f"{'字幕' if v.has_subtitles else '  —'}  "
                  f"粉丝 {v.author.followers:>10,}  @{v.author.username}")

    (FIX / f"brand_{handle}.json").write_text(json.dumps({
        "username": handle, "author_id": brand.author_id,
        "nickname": nickname, "hashtag": hashtag,
        "bio": meta.get("signature") or "",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
