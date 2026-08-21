"""清掉仓库里不该给面试官看到的东西。

面试官打开仓库会扫一遍文件树。废弃模块、调试产物、几版旧线框图混在一起，
传达的信息是「这个人不收拾自己的东西」—— 比少几个文件伤害大。

跑法：
    python3 scripts/tidy_repo.py          # 先看会删什么
    python3 scripts/tidy_repo.py --yes    # 真删

删掉的东西都还在 git 历史里，需要时 `git log --diff-filter=D --name-only` 找得回。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 内容分析那条路线整个废弃了 —— 产品最终只输出视频列表，不做结构拆解。
# 留着这些文件会让人以为它们还在跑。
DEAD_MODULES = [
    "app/aggregate.py",
    "app/baseline.py",
    "app/breakdown.py",
    "app/cluster.py",
    "app/timeline.py",
    "app/subtitles.py",
]

DEAD_SCRIPTS = [
    "scripts/build_results.py",
    "scripts/label_hooks.py",
    "scripts/mine_terms.py",
    "scripts/preview.py",
    "scripts/probe2.py",
    "scripts/probe3.py",
    "scripts/probe4.py",
    "scripts/probe_apify.py",
    "scripts/probe_brand.py",
    "scripts/recall2.py",
    "scripts/recall3.py",
    "scripts/run_breakdown.py",
    "scripts/run_cluster.py",
    "scripts/run_timeline.py",
    "scripts/show_labels.py",
    "scripts/test_baseline.py",
    "scripts/test_cluster.py",
    "scripts/test_real_baseline.py",
    "scripts/prep_repo.py",          # 一次性的，已经用完
]

# 调试时 dump 出来的 HTML。.gitignore 只挡了 fixtures/*.json
DEAD_DIRS = [
    "fixtures",
    "templates",                     # 空目录，早就改成 f-string 渲染了
    "static",
]

# 设计稿：只留当前这版三个文件，搬到 design/
DESIGN_SRC = "TikTok viral video scraper wireframe"
DESIGN_KEEP = ["spark-search.html", "spark-loading.html", "spark-results.html"]


def show(label: str, items: list[str]) -> list[Path]:
    live = [ROOT / i for i in items if (ROOT / i).exists()]
    if not live:
        return []
    print(f"\n{label}")
    for p in live:
        kind = "目录" if p.is_dir() else "    "
        print(f"   ✗ {kind} {p.relative_to(ROOT)}")
    return live


def main() -> None:
    go = "--yes" in sys.argv
    print(f"{'执行' if go else '预览'}模式")

    doomed: list[Path] = []
    doomed += show("废弃模块（内容分析路线已放弃）", DEAD_MODULES)
    doomed += show("一次性脚本 / 早期探测", DEAD_SCRIPTS)
    doomed += show("调试产物与空目录", DEAD_DIRS)

    src = ROOT / DESIGN_SRC
    if src.exists():
        print(f"\n设计稿：只保留当前三版，搬到 design/")
        for name in DESIGN_KEEP:
            print(f"   → design/{name}")
        print(f"   ✗ 目录 {DESIGN_SRC}（含旧线框图、截图、上传副本）")

    if not go:
        print("\n确认无误后加 --yes 执行。")
        return

    for p in doomed:
        shutil.rmtree(p) if p.is_dir() else p.unlink()

    if src.exists():
        dst = ROOT / "design"
        dst.mkdir(exist_ok=True)
        for name in DESIGN_KEEP:
            f = src / name
            if f.exists():
                shutil.copy2(f, dst / name)
        shutil.rmtree(src)

    print("\n完成。剩下的文件树：")
    subprocess.run(["git", "status", "--short"], cwd=ROOT)


if __name__ == "__main__":
    main()
