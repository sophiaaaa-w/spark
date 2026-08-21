"""把模型的逐条标注聚合成「共性」，并按产品给 body 分组。

全部纯代码，零 API 成本。模型只负责打标，统计由代码做 —— 模型算数不可靠，
而这些数字直接决定用户信哪条路。

两个设计要点：

1. **占比写成 `28/50 条` 而不是百分比。** 一条视频可以归入多个类型（钩子确实
   可能同时是「结果预告」和「沙龙平替」），所以各类型占比加起来会超 100%，
   写成百分比会让人以为算错了。

2. **只有 body 按产品分组，hook 和 CTA 不分。**
   「结果预告」这种钩子对拉直棒和卷发棒是通用的，CTA 也一样。只有卖点是产品
   特有的 —— 蒸汽护发和自动卷发完全两回事。
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from . import config as C
from .models import Video


# ---------------------------------------------------------------- 产品标签

# 品类通用词，不是产品名。挖词阶段会把 #wavytalkhair 剥成 "hair"、
# #wavytalkstraightener 剥成 "straightener" —— 这些是品类词，拿来分组会得到
# 「hair 13 条」这种没有意义的分桶。
_GENERIC = {
    "hair", "beauty", "tool", "tools", "care", "products", "product",
    "straightener", "curler", "dryer", "brush", "styler", "iron",
    "skincare", "makeup", "serum", "cream", "official", "partner",
}


def clean_product_terms(terms: list[str], *, min_len: int = 5) -> list[str]:
    """滤掉品类通用词，只留真正的产品型号名。

    判断规则：单个词且在通用词表里 → 丢弃。多词短语保留（"thermal brush" 是
    产品名，"brush" 不是）。
    """
    out = []
    for t in terms:
        t = t.strip().lower()
        if len(t) < min_len:
            continue
        words = t.split()
        if len(words) == 1 and t in _GENERIC:
            continue
        # 全部由通用词组成的短语也丢（如 "hair brush"）
        if words and all(w in _GENERIC for w in words):
            continue
        out.append(t)
    return sorted(set(out), key=len, reverse=True)


def tag_products(videos: list[Video], product_terms: list[str],
                 subtitle_text: dict[str, str] | None = None) -> dict[str, list[str]]:
    """给每条视频打产品标签。纯字符串匹配，零成本。

    product_terms 来自挖词阶段（thermal brush / airshape pro / power wave …），
    是从真实数据里学到的，不是预设的 —— 所以换品牌自动适配。
    """
    subtitle_text = subtitle_text or {}
    norm_terms = [(t, re.sub(r"[^a-z0-9]", "", t.lower())) for t in product_terms]
    out: dict[str, list[str]] = {}
    for v in videos:
        blob = " ".join([
            v.caption.lower(),
            " ".join(v.hashtags),
            subtitle_text.get(v.id, "").lower(),
        ])
        flat = re.sub(r"[^a-z0-9]", "", blob)
        hits = [t for t, n in norm_terms if n and n in flat]
        out[v.id] = hits
    return out


def group_by_product(videos: list[Video], tags: dict[str, list[str]],
                     *, min_group: int = 5) -> dict[str, list[Video]]:
    """按产品分组。分不出有意义的组就合并成一组。

    规则（对所有品牌通用）：能分出 ≥2 组、每组 ≥min_group 条才分组，否则全部合并。
    单产品品牌自动退化成不分组，不需要为不同品牌写不同逻辑。
    """
    buckets: dict[str, list[Video]] = {}
    for v in videos:
        # 一条视频提到多个产品时，归给最具体的那个（最长的词）
        hits = sorted(tags.get(v.id, []), key=len, reverse=True)
        buckets.setdefault(hits[0] if hits else "", []).append(v)

    big = {k: vs for k, vs in buckets.items() if k and len(vs) >= min_group}
    if len(big) < 2:
        return {"": list(videos)}

    leftovers = [v for k, vs in buckets.items() if k not in big for v in vs]
    if leftovers:
        big["其他 / 未识别产品"] = leftovers
    return big


# ---------------------------------------------------------------- 共性聚合

@dataclass(slots=True)
class Commonality:
    id: int
    name: str
    description: str
    members: list[Video] = field(default_factory=list)
    quote: str = ""
    quote_video_id: str = ""
    quote_t: float | None = None

    @property
    def count(self) -> int:
        return len(self.members)

    def stats(self, total: int) -> dict:
        if not self.members:
            return {}
        return {
            "count": self.count,
            "total": total,
            "median_engagement": round(
                statistics.median(m.engagement_rate for m in self.members), 4),
            "median_plays": int(statistics.median(m.plays for m in self.members)),
            "median_score": round(
                statistics.median(m.score for m in self.members), 3),
        }

    def as_dict(self, total: int) -> dict:
        d = {"id": self.id, "name": self.name, "description": self.description,
             "quote": self.quote, "quote_video_id": self.quote_video_id,
             "quote_t": self.quote_t,
             "member_ids": [m.id for m in self.members]}
        d.update(self.stats(total))
        return d


def _collect(types: list[dict], assignments: dict[str, list[int]],
             by_id: dict[str, Video]) -> list[Commonality]:
    out = []
    for t in types:
        c = Commonality(id=t["id"], name=t.get("name", ""),
                        description=t.get("description", ""))
        for vid, ids in assignments.items():
            if t["id"] in (ids or []) and vid in by_id:
                c.members.append(by_id[vid])
        out.append(c)
    return [c for c in out if c.members]


def _pick_quotes(group: list[Commonality], quotes: dict[str, str]) -> None:
    """给每个共性挑一句代表原话，且**不同共性不用同一条视频**。

    一条视频可以归入多个类型，如果都取组内得分最高那条，几个类型会显示同一句话，
    看起来像坏了。按组从大到小依次挑，已被占用的视频跳过。
    """
    used: set[str] = set()
    for c in sorted(group, key=lambda x: x.count, reverse=True):
        for v in sorted(c.members, key=lambda x: x.score, reverse=True):
            q = (quotes.get(v.id) or "").strip()
            if q and v.id not in used:
                c.quote, c.quote_video_id, used = q, v.id, used | {v.id}
                break
        else:                                   # 实在没有没被占用的，允许复用
            for v in sorted(c.members, key=lambda x: x.score, reverse=True):
                q = (quotes.get(v.id) or "").strip()
                if q:
                    c.quote, c.quote_video_id = q, v.id
                    break


def build(result: dict, videos: list[Video], *,
          product_terms: list[str],
          subtitle_text: dict[str, str] | None = None) -> dict:
    """把模型输出聚合成最终 brief 结构。"""
    by_id = {v.id: v for v in videos}
    rows = [r for r in result.get("videos", []) if r.get("video_id") in by_id]
    total = len(rows)

    hook_a = {r["video_id"]: r.get("hook_type_ids") for r in rows}
    body_a = {r["video_id"]: r.get("body_type_ids") for r in rows}
    cta_a = {r["video_id"]: r.get("cta_type_ids") for r in rows}
    hook_q = {r["video_id"]: r.get("hook_quote", "") for r in rows}
    cta_q = {r["video_id"]: r.get("cta_quote", "") for r in rows}

    hooks = _collect(result.get("hook_types", []), hook_a, by_id)
    bodies = _collect(result.get("body_types", []), body_a, by_id)
    ctas = _collect(result.get("cta_types", []), cta_a, by_id)
    _pick_quotes(hooks, hook_q)
    _pick_quotes(ctas, cta_q)
    _pick_quotes(bodies, hook_q)    # body 没有单独 quote，用开场句占位

    for group in (hooks, bodies, ctas):
        group.sort(key=lambda c: c.count, reverse=True)

    # hook 时长中位数本身就是一条发现：「前 N 秒必须完成钩子」
    hook_ends = [r.get("hook_ends_at") for r in rows if r.get("hook_ends_at")]
    median_hook = round(statistics.median(hook_ends), 1) if hook_ends else None

    # ---- 卖点：挂在 body 类型下面，再按产品拆开 ----
    #
    # 为什么这么挂：产品差异只体现在卖点上（蒸汽护发 vs 自动卷发完全两回事），
    # 而 hook 和 CTA 对不同产品是通用的。
    # 为什么 body 类型本身不按产品拆：拆完每组只剩 6-12 条，三个数据就没统计
    # 意义了。所以类型统计用全部 50 条，只有卖点往下分层。
    sp_names = {s["id"]: s.get("name", "") for s in result.get("selling_points", [])}
    sp_by_video = {r["video_id"]: (r.get("selling_point_ids") or []) for r in rows}
    terms = clean_product_terms(product_terms)
    tags = tag_products(videos, terms, subtitle_text)
    groups = group_by_product(videos, tags)
    product_of = {v.id: g for g, vs in groups.items() for v in vs}

    def points_for(members: list[Video], scope: list[Video] | None = None) -> list[dict]:
        counts: dict[int, int] = {}
        for v in members:
            for sid in sp_by_video.get(v.id, []):
                counts[sid] = counts.get(sid, 0) + 1
        return [{"name": sp_names[sid], "count": n, "of": len(members)}
                for sid, n in sorted(counts.items(), key=lambda kv: -kv[1])
                if sid in sp_names and sp_names[sid]]

    body_blocks = []
    for c in bodies:
        by_product: dict[str, list[Video]] = {}
        for v in c.members:
            by_product.setdefault(product_of.get(v.id, ""), []).append(v)
        groups_out = []
        for pname, mem in sorted(by_product.items(), key=lambda kv: -len(kv[1])):
            pts = points_for(mem)
            if pts:
                groups_out.append({"product": pname or "全部",
                                   "video_count": len(mem),
                                   "selling_points": pts[:6]})
        body_blocks.append({**c.as_dict(total), "by_product": groups_out})

    product_summary = [{"product": k or "全部", "video_count": len(v)}
                       for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]

    # ---- 视频索引：每条用了哪些类型 ----
    def names(ids, pool):
        m = {c.id: c.name for c in pool}
        return [m[i] for i in (ids or []) if i in m]

    index = []
    for r in sorted(rows, key=lambda r: -by_id[r["video_id"]].score):
        v = by_id[r["video_id"]]
        index.append({
            "video_id": v.id, "url": v.url, "author": v.author.username,
            "plays": v.plays, "engagement_rate": round(v.engagement_rate, 4),
            "duration": v.duration, "score": v.score,
            "products": tags.get(v.id, []),
            "hook": names(r.get("hook_type_ids"), hooks),
            "body": names(r.get("body_type_ids"), bodies),
            "cta": names(r.get("cta_type_ids"), ctas),
            "hook_quote": r.get("hook_quote", ""),
            "cta_quote": r.get("cta_quote", ""),
        })

    return {
        "category": result.get("category") or "unknown",
        "total_videos": total,
        "median_hook_seconds": median_hook,
        "hooks": [c.as_dict(total) for c in hooks],
        "bodies": body_blocks,
        "ctas": [c.as_dict(total) for c in ctas],
        "products": product_summary,
        "index": index,
    }


def verify_quotes(built: dict, subtitle_text: dict[str, str]) -> dict:
    """校验 quote 是否逐字来自字幕。

    不能只靠 prompt 要求 —— 字幕在我们手里，对一遍就是保证。
    重复出现的原句是 brief 的指纹，模型一润色就毁了。
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    bad = []
    for section in ("hooks", "bodies", "ctas"):
        for c in built.get(section, []):
            q = (c.get("quote") or "").strip().rstrip("…").rstrip(".")
            if not q:
                c["quote_verified"] = None
                continue
            src = norm(subtitle_text.get(c.get("quote_video_id"), ""))
            ok = bool(src) and norm(q) in src
            c["quote_verified"] = ok
            if not ok:
                bad.append(f"{section}/{c['name']}: {q[:50]}")
    built["unverified_quotes"] = bad
    return built
