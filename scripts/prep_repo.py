"""上传 GitHub 前的准备：清掉不该进仓库的东西，把 demo 数据打包成 seed/。

跑法：
    python3 scripts/prep_repo.py          # 先看会做什么
    python3 scripts/prep_repo.py --yes    # 真的执行

两件事：

1. 删掉带密钥的和临时的文件。`outlier_key.env` 装着真 token 且不在 .gitignore
   里 —— 直接 push 就是又一次泄露。

2. 建 seed/。`data/` 有 717MB（大头是下载的视频）必须整个 gitignore，但那样
   线上就没有 demo 数据了 —— 而 demo 是没有邀请码的访客唯一看得到的东西。
   所以把 demo 需要的那 47 张封面（8.4MB）和一份 brief 单独复制到 seed/，
   这个目录进仓库，服务启动时自动导入。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_JOB = "baa8bf6bdae9"
DEMO_BRAND = "wavytalk"
DEMO_CATEGORY = "hair tools"

JUNK = [
    "outlier_key.env",              # 真 token，不在 .gitignore 里
    "preview-home.html",
    "preview-result.html",
    "design-results-REAL-COVERS.html",
    "STATUS.md",                    # 早就过时了
    ".DS_Store",
]


def main() -> None:
    go = "--yes" in sys.argv
    print(f"{'执行' if go else '预览'}模式\n")

    print("一、删掉这些文件")
    for name in JUNK:
        p = ROOT / name
        if not p.exists():
            print(f"   ·  {name}  (不存在，跳过)")
            continue
        print(f"   ✗  {name}")
        if go:
            p.unlink()

    print("\n二、打包 seed/")
    brief = ROOT / "data" / "briefs" / f"{DEMO_JOB}.json"
    if not brief.exists():
        sys.exit(f"\n找不到 {brief} —— demo 数据缺失，先确认 job_id 对不对")

    data = json.loads(brief.read_text(encoding="utf-8"))
    vids = data.get("videos") or []
    seed = ROOT / "seed"
    covers_src = ROOT / "data" / "covers"

    have = [v for v in vids if (covers_src / f"{v['id']}.jpg").exists()]
    size = sum((covers_src / f"{v['id']}.jpg").stat().st_size for v in have)
    print(f"   brief   {brief.name}  ({brief.stat().st_size // 1024} KB, {len(vids)} 条)")
    print(f"   封面     {len(have)}/{len(vids)} 张  ({size / 1024 / 1024:.1f} MB)")

    if len(have) < len(vids):
        print(f"   ⚠️ 有 {len(vids) - len(have)} 张封面缺失，先跑 cache_covers.py")

    if go:
        (seed / "covers").mkdir(parents=True, exist_ok=True)
        shutil.copy2(brief, seed / f"{DEMO_JOB}.json")
        for v in have:
            name = f"{v['id']}.jpg"
            shutil.copy2(covers_src / name, seed / "covers" / name)
        (seed / "demo.json").write_text(json.dumps({
            "job_id": DEMO_JOB,
            "brand": DEMO_BRAND,
            "category": DEMO_CATEGORY,
            "count": len(vids),
            "crawled": data.get("stats", {}).get("after_dedupe", 0),
        }, indent=2), encoding="utf-8")
        print(f"   → 写入 {seed}")

    print("\n" + ("完成。" if go else "确认无误后加 --yes 执行。"))


if __name__ == "__main__":
    main()
