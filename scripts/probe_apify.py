"""fixtures 字段探测 —— 开工第一步（PRD 第十节）。

跑法：
    pip install httpx python-dotenv
    python scripts/probe_apify.py @cerave

只抓 20 条，成本几分钱。结果存进 fixtures/ 供后续反复使用，
不要每次调 prompt 都重新爬。

它回答 PRD 里那 9 个必验问题，其中前两个如果不满足，方案要当场改：
  1. profile 调用是否支持日期下界参数     → 决定基线抓取策略
  2. 自带字幕覆盖率                       → 低于 50% 则聚类输入要改
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("APIFY_TOKEN")
ACTOR = "clockworks~tiktok-scraper"
BASE = "https://api.apify.com/v2"
OUT = Path("fixtures")

# 关注这些字段是否存在（PRD 第十节的必验清单）
WATCH = [
    "id", "webVideoUrl", "text", "createTimeISO", "diggCount", "shareCount",
    "playCount", "commentCount", "collectCount", "videoMeta", "duration",
    "downloadAddr", "subtitleLinks", "hashtags", "authorMeta", "isAd", "isSlideshow",
]


async def run_actor(client: httpx.AsyncClient, payload: dict) -> list[dict]:
    """异步模式。同步接口有 300s 上限，正式流水线里一定会超（PRD 九·B）。"""
    r = await client.post(f"{BASE}/acts/{ACTOR}/runs", params={"token": TOKEN}, json=payload)
    r.raise_for_status()
    run = r.json()["data"]
    run_id, dataset_id = run["id"], run["defaultDatasetId"]

    while True:
        await asyncio.sleep(5)
        s = await client.get(f"{BASE}/actor-runs/{run_id}", params={"token": TOKEN})
        status = s.json()["data"]["status"]
        print(f"    {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    d = await client.get(f"{BASE}/datasets/{dataset_id}/items", params={"token": TOKEN})
    return d.json()


def report(name: str, items: list[dict]) -> None:
    print(f"\n=== {name} — {len(items)} 条 ===")
    if not items:
        print("  ⚠️  空结果")
        return

    print("  字段存在率：")
    for field in WATCH:
        n = sum(1 for it in items if it.get(field) not in (None, "", [], {}))
        flag = "✓" if n == len(items) else ("~" if n else "✗")
        print(f"    {flag} {field:<16} {n}/{len(items)}")

    print("\n  顶层实际字段：")
    print("   ", sorted(items[0].keys()))

    subs = sum(1 for it in items if it.get("subtitleLinks"))
    print(f"\n  ★ 自带字幕覆盖率：{subs}/{len(items)} = {subs / len(items):.0%}")
    print("    （低于 50% 则聚类输入需要改方案）")

    dates = sorted(it.get("createTimeISO", "") for it in items if it.get("createTimeISO"))
    if dates:
        print(f"  ★ 发布时间范围：{dates[0][:10]} → {dates[-1][:10]}")
        print("    （看关键词搜索到底能回溯多深）")

    durs = [
        it.get("videoMeta", {}).get("duration") or it.get("duration")
        for it in items
    ]
    durs = [d for d in durs if d]
    if durs:
        in_range = sum(1 for d in durs if 10 <= d <= 90)
        print(f"  ★ 时长 10-90s 占比：{in_range}/{len(durs)}")
    else:
        print("  ⚠️  拿不到时长字段 —— 10-90 秒过滤没法做")

    authors = {it.get("authorMeta", {}).get("name") for it in items}
    print(f"  ★ 涉及账号数：{len([a for a in authors if a])}")


async def main(handle: str) -> None:
    if not TOKEN:
        sys.exit("缺 APIFY_TOKEN，先把 .env.example 复制成 .env 并填好")

    handle = handle.lstrip("@")
    OUT.mkdir(exist_ok=True)

    # handle 未必等于好用的关键词/标签：
    #   @colorwow.hair → 关键词该用 "Color Wow"，标签该用 #colorwow
    # 所以关键词和标签允许单独传，默认退化成 handle
    keyword = sys.argv[2] if len(sys.argv) > 2 else handle
    tag = sys.argv[3] if len(sys.argv) > 3 else handle.replace(".", "").replace("_", "")

    async with httpx.AsyncClient(timeout=300) as client:
        probes = {
            "profile": {"profiles": [handle], "resultsPerPage": 20,
                        "shouldDownloadSubtitles": True},
            "keyword": {"searchQueries": [keyword], "resultsPerPage": 20,
                        "shouldDownloadSubtitles": True},
            "hashtag": {"hashtags": [tag], "resultsPerPage": 20,
                        "shouldDownloadSubtitles": True},
        }
        print(f"handle={handle}  keyword={keyword!r}  hashtag=#{tag}")
        for name, payload in probes.items():
            print(f"\n>>> {name}")
            try:
                items = await run_actor(client, payload)
            except Exception as exc:                       # noqa: BLE001
                print(f"  ✗ 失败：{exc}")
                continue
            (OUT / f"{name}_{handle}.json").write_text(
                json.dumps(items, ensure_ascii=False, indent=2)
            )
            report(name, items)

    print(f"\n原始 JSON 已存进 {OUT}/，把这份终端输出发我。")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "@cerave"))
