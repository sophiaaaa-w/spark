"""探测第四轮 —— 最后一个未知数。

日期参数在 profile 上已确认生效。问题是：搜索和 hashtag 上也生效吗？

生效  → 召回量从 ~1000 降到 ~400，成本省一半，时间省更多
不生效 → 只能超量召回再本地过滤

成本约 $0.15。
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("APIFY_TOKEN")
ACTOR = "clockworks~tiktok-scraper"
BASE = "https://api.apify.com/v2"
SINCE = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")


async def run(client: httpx.AsyncClient, payload: dict) -> tuple[list[dict], float]:
    t0 = asyncio.get_event_loop().time()
    r = await client.post(f"{BASE}/acts/{ACTOR}/runs", params={"token": TOKEN}, json=payload)
    if r.status_code >= 400:
        print(f"    ✗ HTTP {r.status_code}: {r.text[:200]}")
        return [], 0
    d = r.json()["data"]
    while True:
        await asyncio.sleep(5)
        st = (await client.get(f"{BASE}/actor-runs/{d['id']}", params={"token": TOKEN})
              ).json()["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    dt = asyncio.get_event_loop().time() - t0
    if st != "SUCCEEDED":
        print(f"    {st}")
        return [], dt
    items = (await client.get(f"{BASE}/datasets/{d['defaultDatasetId']}/items",
                              params={"token": TOKEN})).json()
    return items, dt


def verdict(name: str, items: list[dict], secs: float, asked: int) -> None:
    if not items:
        print(f"    {name}: 空结果")
        return
    dates = sorted((x.get("createTimeISO") or "")[:10] for x in items)
    older = sum(1 for x in dates if x < SINCE)
    ok = older == 0
    print(f"    {name}: {len(items)}/{asked} 条 · {dates[0]} → {dates[-1]} · {secs:.0f}s")
    print(f"      早于 {SINCE} 的: {older} 条 → {'✅ 生效' if ok else '❌ 被忽略'}")
    if ok:
        slides = sum(1 for x in items if x.get("isSlideshow"))
        print(f"      窗口内样本里图文帖: {slides}/{len(items)}")


async def main() -> None:
    print(f"日期下界 = {SINCE}（近 30 天）\n")
    async with httpx.AsyncClient(timeout=900) as client:
        print(">>> 搜索路径")
        items, secs = await run(client, {
            "searchQueries": ["Color Wow"], "resultsPerPage": 60,
            "oldestPostDate": SINCE,
        })
        verdict("keyword", items, secs, 60)

        print("\n>>> hashtag 路径")
        items, secs = await run(client, {
            "hashtags": ["colorwow"], "resultsPerPage": 60,
            "oldestPostDate": SINCE,
        })
        verdict("hashtag", items, secs, 60)

        print("\n>>> 顺带：一次要 300 条要跑多久（决定用户等待时长）")
        items, secs = await run(client, {
            "searchQueries": ["Color Wow"], "resultsPerPage": 300,
            "oldestPostDate": SINCE,
        })
        print(f"    拿到 {len(items)} 条，耗时 {secs:.0f}s")
        if items:
            in_win = sum(
                1 for x in items
                if (x.get("createTimeISO") or "")[:10] >= SINCE
            )
            vids = sum(1 for x in items if not x.get("isSlideshow"))
            print(f"    窗口内 {in_win} · 非图文帖 {vids}")


if __name__ == "__main__":
    asyncio.run(main())
