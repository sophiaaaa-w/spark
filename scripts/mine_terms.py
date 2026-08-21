"""从第一轮召回里挖出第二轮要搜的词，打印给你过目。

跑法：
    python3 scripts/mine_terms.py @wavytalkofficial

**零成本**，只读本地已抓下来的 recall_*.json。

跑完会生成 fixtures/terms_<handle>.json，里面每一条有个 "use": true/false。
你用文本编辑打开、把不想搜的改成 false、保存，然后跑 recall2.py。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, mining                       # noqa: E402
from app.funnel import BrandRef                           # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    bpath = FIX / f"brand_{handle}.json"
    rpath = FIX / f"recall_{handle}.json"
    for p in (bpath, rpath):
        if not p.exists():
            sys.exit(f"找不到 {p.name}，先跑 probe_brand.py @{handle}")

    d = json.loads(bpath.read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    raws = json.loads(rpath.read_text())

    terms = mining.mine(raws, token=brand.hashtag.lstrip("#"),
                        nickname=brand.nickname)

    print("=" * 74)
    print(f"第二轮候选搜索词　{brand.nickname}（@{handle}）")
    print(f"来源：第一轮 {len(raws)} 条召回")
    print("=" * 74)

    on = [t for t in terms if t.use]
    off = [t for t in terms if not t.use]
    chosen = mining.pick(terms)
    chosen_ids = {(t.kind, t.value) for t in chosen}

    print(f"\n实际会搜的（{len(chosen)} 路，其中关键词 "
          f"{sum(1 for t in chosen if t.kind == 'keyword')} 路）\n")
    print(f"  {'类型':<8}{'搜索词':<42}{'第一轮出现':>10}")
    for t in chosen:
        val = f"#{t.value}" if t.kind == "hashtag" else f'"{t.value}"'
        kind = "标签" if t.kind == "hashtag" else "关键词"
        print(f"  {kind:<8}{val:<42}{t.count:>8} 次")

    rest = [t for t in on if (t.kind, t.value) not in chosen_ids]
    if rest:
        print(f"\n勾选了但名额不够（{len(rest)} 个）")
        for t in rest:
            val = f"#{t.value}" if t.kind == "hashtag" else f'"{t.value}"'
            print(f"      {val:<42}{t.count:>5} 次")

    if off:
        print(f"\n建议跳过（{len(off)} 个）\n")
        for t in off:
            val = f"#{t.value}" if t.kind == "hashtag" else f'"{t.value}"'
            print(f"      {val:<40}{t.count:>5} 次   {t.note}")

    n = len(chosen)
    cost = n * C.RECALL2_ITEMS_PER_RUN * 1.7 / 1000
    print(f"\n{'=' * 74}")
    print(f"第二轮预估：{n} 路 × {C.RECALL2_ITEMS_PER_RUN} 条 "
          f"≈ {n * C.RECALL2_ITEMS_PER_RUN} 条，约 ${cost:.2f}")
    print("=" * 74)

    out = FIX / f"terms_{handle}.json"
    out.write_text(json.dumps([t.as_dict() for t in terms],
                              ensure_ascii=False, indent=2))
    print(f"\n已存 fixtures/{out.name}")
    print("\n要改的话：")
    print(f"  open -e fixtures/{out.name}")
    print('  把不想搜的那条 "use": true 改成 false，保存')
    print(f"\n确认后跑：")
    print(f"  python3 scripts/recall2.py @{handle}")


if __name__ == "__main__":
    main()
