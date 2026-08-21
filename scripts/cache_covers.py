"""把 brief 里的 TikTok 封面下载到本地，让 demo 页面不会过期。

为什么必须做：
    Apify 返回的 cover_url 是带签名的 CDN 地址，查询串里有 x-expires。
    实测 WavyTalk 那批的有效期只有约 **两天**。
    demo 要挂在简历上几个月，不缓存的话过两天点开全是裂图 ——
    而 demo 恰恰是大多数访客唯一会看到的页面。

跑法：
    python3 scripts/cache_covers.py           # 处理所有 demo brief
    python3 scripts/cache_covers.py --all     # 处理全部 brief，不只 demo
    python3 scripts/cache_covers.py --force   # 已存在的也重下

只用标准库，不引新依赖。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C                                  # noqa: E402
from app import db                                           # noqa: E402

COVERS_DIR = C.DATA_DIR / "covers"
TIMEOUT = 20
WORKERS = 8

# TikTok 的 CDN 对没有 UA 的请求会回 403
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126.0 Safari/537.36"}


def demo_job_ids() -> set[str]:
    db.init()
    with db.connect() as conn:
        rows = conn.execute("SELECT job_id FROM briefs WHERE is_demo = 1").fetchall()
    return {r["job_id"] for r in rows}


def fetch(url: str, dest: Path) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:                                    # noqa: BLE001
        return False, str(e)[:60]
    if len(data) < 1024:
        return False, f"只有 {len(data)} 字节，八成不是图片"
    dest.write_bytes(data)
    return True, f"{len(data)//1024}KB"


def process(path: Path, *, force: bool) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    vids = data.get("videos") or []
    brand = (data.get("brand") or {}).get("nickname", path.stem)
    todo = []
    for v in vids:
        dest = COVERS_DIR / f"{v['id']}.jpg"
        if dest.exists() and not force:
            v["cover_local"] = f"/covers/{v['id']}.jpg"
            continue
        if v.get("cover_url"):
            todo.append((v, dest))

    print(f"\n{brand}  共 {len(vids)} 条，需要下载 {len(todo)} 张")
    if todo:
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(
                lambda t: (t[0], *fetch(t[0]["cover_url"], t[1])), todo))
        ok = 0
        for v, good, note in results:
            if good:
                v["cover_local"] = f"/covers/{v['id']}.jpg"
                ok += 1
            else:
                print(f"    ✗ {v['id']} @{v.get('author','')} — {note}")
        print(f"  成功 {ok}/{len(todo)}")
        if ok < len(todo):
            print("  ⚠️ 有失败的。签名可能已经过期 —— 那就只能重跑这个品牌，"
                  "拿到新的 cover_url 再缓存。")

    have = sum(1 for v in vids if v.get("cover_local"))
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"  写回 {path.name}，{have}/{len(vids)} 条已本地化")


def main() -> None:
    force = "--force" in sys.argv
    every = "--all" in sys.argv

    briefs = sorted((C.DATA_DIR / "briefs").glob("*.json"))
    if not briefs:
        sys.exit("data/briefs 下没有任何 brief")

    if not every:
        demos = demo_job_ids()
        if not demos:
            sys.exit("还没有标记任何 demo。先跑 scripts/mark_demo.py，"
                     "或者加 --all 处理全部。")
        briefs = [b for b in briefs if b.stem in demos]

    print(f"要处理 {len(briefs)} 份 brief，封面存到 {COVERS_DIR}")
    for b in briefs:
        process(b, force=force)
    print("\n完成。记得确认 main.py 已经把 /covers 挂出来。")


if __name__ == "__main__":
    main()
