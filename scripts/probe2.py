"""探测第二轮 —— 回答第一轮留下的问题。

跑法：
    python3 scripts/probe2.py

第 1 部分读本地 fixtures，不花钱。
第 2 部分要调 3 次 API（各 10 条），几分钱。
"""
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("APIFY_TOKEN")
ACTOR = "clockworks~tiktok-scraper"
BASE = "https://api.apify.com/v2"
FIX = Path("fixtures")


# ---------------------------------------------------------- 第 1 部分：读本地

def dump_structure() -> None:
    """把一条完整记录摊开，看清嵌套结构。零成本。"""
    path = next(FIX.glob("keyword_*.json"), None)
    if not path:
        print("找不到 fixtures，先跑 probe_apify.py")
        return

    items = json.loads(path.read_text())
    it = items[0]

    print("=" * 60)
    print("一条完整记录（截断长文本）")
    print("=" * 60)

    def trim(v, depth=0):
        if isinstance(v, str) and len(v) > 120:
            return v[:120] + f"...(共{len(v)}字)"
        if isinstance(v, list) and len(v) > 3:
            return [trim(x, depth + 1) for x in v[:3]] + [f"...(共{len(v)}项)"]
        if isinstance(v, dict):
            return {k: trim(x, depth + 1) for k, x in v.items()}
        return v

    print(json.dumps(trim(it), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("关键嵌套字段确认")
    print("=" * 60)
    print("videoMeta  :", json.dumps(trim(it.get("videoMeta")), ensure_ascii=False))
    print("authorMeta :", json.dumps(trim(it.get("authorMeta")), ensure_ascii=False))
    print("mediaUrls  :", json.dumps(trim(it.get("mediaUrls")), ensure_ascii=False))
    print("mentions   :", it.get("mentions"), "|", it.get("detailedMentions"))

    print("\n" + "=" * 60)
    print("语言与时长分布（决定过滤规则）")
    print("=" * 60)
    langs: dict[str, int] = {}
    for x in items:
        langs[x.get("textLanguage") or "?"] = langs.get(x.get("textLanguage") or "?", 0) + 1
    print("textLanguage:", langs)

    durs = [x.get("videoMeta", {}).get("duration") for x in items]
    durs = sorted(d for d in durs if d)
    print("时长排序:", durs)

    slides = sum(1 for x in items if x.get("isSlideshow"))
    print(f"图文帖: {slides}/{len(items)}")

    print("\ncaption 长度（决定能不能只靠 caption 聚类）:")
    lens = sorted(len(x.get("text") or "") for x in items)
    print(" ", lens)
    print("  中位数:", lens[len(lens) // 2])
    print("\n前 3 条 caption 原文：")
    for x in items[:3]:
        print("  -", (x.get("text") or "")[:200])


# ---------------------------------------------------------- 第 2 部分：调 API

async def run(client: httpx.AsyncClient, payload: dict) -> list[dict]:
    r = await client.post(f"{BASE}/acts/{ACTOR}/runs", params={"token": TOKEN}, json=payload)
    if r.status_code >= 400:
        print(f"    ✗ HTTP {r.status_code}: {r.text[:300]}")
        return []
    run_id = r.json()["data"]["id"]
    ds = r.json()["data"]["defaultDatasetId"]
    while True:
        await asyncio.sleep(5)
        st = (await client.get(f"{BASE}/actor-runs/{run_id}", params={"token": TOKEN})
              ).json()["data"]["status"]
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"    {st}")
            break
    if st != "SUCCEEDED":
        return []
    return (await client.get(f"{BASE}/datasets/{ds}/items", params={"token": TOKEN})).json()


async def probe_params() -> None:
    print("\n" + "=" * 60)
    print("参数支持测试")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=300) as client:
        # 1) actor 的输入 schema —— 权威地告诉我们支持哪些参数
        r = await client.get(f"{BASE}/acts/{ACTOR}", params={"token": TOKEN})
        if r.status_code < 400:
            schema = r.json()["data"].get("versions", [{}])[-1].get("inputSchema")
            if schema:
                props = json.loads(schema).get("properties", {})
                print("\n★ actor 支持的全部输入参数：")
                for k, v in props.items():
                    print(f"    {k:<32} {v.get('type','')}")
            else:
                print("  拿不到 inputSchema，去 apify.com 页面上看 Input 那一栏")

        # 2) 日期下界 —— 决定基线抓取策略
        print("\n>>> 测 oldestPostDateUnified（profile）")
        items = await run(client, {
            "profiles": ["colorwow.hair"], "resultsPerPage": 10,
            "oldestPostDateUnified": "2026-06-01",
        })
        if items:
            dates = sorted(x.get("createTimeISO", "")[:10] for x in items)
            print(f"    拿到 {len(items)} 条，范围 {dates[0]} → {dates[-1]}")
            print("    ★ 若最早那条 >= 2026-06-01，说明日期参数生效")

        # 3) 字幕 —— 换个参数名再试
        print("\n>>> 测 shouldDownloadSubtitles + shouldDownloadVideos")
        items = await run(client, {
            "searchQueries": ["Color Wow"], "resultsPerPage": 10,
            "shouldDownloadSubtitles": True, "shouldDownloadVideos": False,
        })
        if items:
            n = sum(1 for x in items if x.get("subtitleLinks") or x.get("videoMeta", {}).get("subtitleLinks"))
            print(f"    ★ 字幕覆盖 {n}/{len(items)}")
            print("    videoMeta 内的键:", list(items[0].get("videoMeta", {}).keys()))


if __name__ == "__main__":
    dump_structure()
    if TOKEN:
        asyncio.run(probe_params())
