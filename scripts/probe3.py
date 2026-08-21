"""探测第三轮 —— 定死最后三个未知数。

跑法：
    python3 scripts/probe3.py

要回答：
  1. 字幕文件是什么格式？带时间戳吗？  → 决定 Whisper 还要不要
  2. 日期下界参数真的生效吗？          → 决定基线抓取策略（上一轮测法有误）
  3. 真实产出率是多少？                → 决定召回量和成本

成本约 $0.3（一次 150 条的召回）。
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("APIFY_TOKEN")
ACTOR = "clockworks~tiktok-scraper"
BASE = "https://api.apify.com/v2"
FIX = Path("fixtures")


async def run(client: httpx.AsyncClient, payload: dict) -> list[dict]:
    r = await client.post(f"{BASE}/acts/{ACTOR}/runs", params={"token": TOKEN}, json=payload)
    if r.status_code >= 400:
        print(f"    ✗ HTTP {r.status_code}: {r.text[:300]}")
        return []
    data = r.json()["data"]
    run_id, ds = data["id"], data["defaultDatasetId"]
    while True:
        await asyncio.sleep(5)
        st = (await client.get(f"{BASE}/actor-runs/{run_id}", params={"token": TOKEN})
              ).json()["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    print(f"    {st}")
    if st != "SUCCEEDED":
        return []
    return (await client.get(f"{BASE}/datasets/{ds}/items", params={"token": TOKEN})).json()


# ------------------------------------------------------- 1. 字幕格式

async def check_subtitle(client: httpx.AsyncClient) -> None:
    print("\n" + "=" * 60)
    print("1. 字幕文件格式 —— 决定 Whisper 还要不要")
    print("=" * 60)

    items = await run(client, {
        "searchQueries": ["Color Wow"], "resultsPerPage": 10,
        "shouldDownloadSubtitles": True,
    })
    link = None
    for it in items:
        for s in (it.get("videoMeta") or {}).get("subtitleLinks") or []:
            if s.get("language", "").startswith("eng"):
                link = s["downloadLink"]
                break
        if link:
            break

    if not link:
        print("  ✗ 没拿到英文字幕链接")
        return

    try:
        r = await client.get(link, timeout=30)
        text = r.text
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ✗ 下载失败：{exc}")
        return

    print(f"  HTTP {r.status_code}，{len(text)} 字节")
    print("  ★ 前 600 字符：")
    print("  " + "\n  ".join(text[:600].splitlines()))
    has_ts = "-->" in text
    print(f"\n  ★ 带时间戳: {'是（WebVTT/SRT，可直接对齐时间轴）' if has_ts else '否（纯文本）'}")
    (FIX / "subtitle_sample.txt").write_text(text)


# ------------------------------------------------------- 2. 日期参数

async def check_date_param(client: httpx.AsyncClient) -> None:
    print("\n" + "=" * 60)
    print("2. 日期下界参数 —— 上一轮测法有误，重做")
    print("=" * 60)
    print("  测法：要 60 条 + 只要 14 天内的。")
    print("  若参数生效 → 条数少于 60 且全部在 14 天内")
    print("  若被忽略   → 拿满 60 条且有更早的\n")

    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    for key in ("oldestPostDateUnified", "oldestPostDate"):
        print(f">>> {key} = {since}")
        items = await run(client, {
            "profiles": ["chrisappletonhair"], "resultsPerPage": 60, key: since,
        })
        if not items:
            continue
        dates = sorted((x.get("createTimeISO") or "")[:10] for x in items)
        older = sum(1 for d in dates if d < since)
        print(f"    拿到 {len(items)} 条，{dates[0]} → {dates[-1]}")
        print(f"    ★ 早于下界的: {older} 条 → "
              f"{'✅ 参数生效' if older == 0 and len(items) < 60 else '❌ 被忽略'}")


# ------------------------------------------------------- 3. 真实产出率

async def check_yield(client: httpx.AsyncClient) -> None:
    print("\n" + "=" * 60)
    print("3. 真实产出率 —— 决定召回量")
    print("=" * 60)

    N = 150
    items = await run(client, {
        "searchQueries": ["Color Wow"], "resultsPerPage": N,
        "shouldDownloadSubtitles": True,
    })
    if not items:
        return
    (FIX / "yield_test.json").write_text(json.dumps(items, ensure_ascii=False, indent=2))

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    steps, cur = [], items
    steps.append(("原始召回", len(cur)))

    cur = [x for x in cur if not x.get("isSlideshow")]
    steps.append(("剔除图文帖", len(cur)))

    cur = [x for x in cur if (x.get("textLanguage") or "un") in ("en", "un")]
    steps.append(("只留英文/未知", len(cur)))

    cur = [x for x in cur if 10 <= ((x.get("videoMeta") or {}).get("duration") or 0) <= 90]
    steps.append(("时长 10-90s", len(cur)))

    cur = [x for x in cur
           if datetime.fromisoformat(x["createTimeISO"].replace("Z", "+00:00")) >= cutoff]
    steps.append(("近 30 天", len(cur)))

    cur = [x for x in cur if (x.get("playCount") or 0) >= 10_000]
    steps.append(("播放 >10k", len(cur)))

    print()
    base = len(items)
    for name, n in steps:
        bar = "█" * int(30 * n / max(base, 1))
        print(f"  {name:<14} {n:>4}  {bar}")

    print(f"\n  ★ 产出率 {len(cur)}/{base} = {len(cur)/max(base,1):.1%}")
    if cur:
        need = int(50 / (len(cur) / base))
        print(f"  ★ 要凑够 Top 50，召回量需要约 {need} 条 → 成本约 ${need*1.7/1000:.2f}")
    else:
        print("  ⚠️  一条都没剩，过滤条件或放宽阶梯要重新设计")

    subs = sum(1 for x in cur if (x.get("videoMeta") or {}).get("subtitleLinks"))
    if cur:
        print(f"  ★ 存活样本的字幕覆盖率: {subs}/{len(cur)} = {subs/len(cur):.0%}")
    print(f"  ★ 存活样本涉及账号数: "
          f"{len({(x.get('authorMeta') or {}).get('name') for x in cur})}")


async def main() -> None:
    FIX.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=600) as client:
        await check_subtitle(client)
        await check_date_param(client)
        await check_yield(client)


if __name__ == "__main__":
    asyncio.run(main())
