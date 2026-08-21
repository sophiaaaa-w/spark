"""从第一轮召回里挖出品牌的实际词汇表，供第二轮扩量使用。

为什么需要这一步：TikTok 不提供「某品牌全部相关视频」的接口，只能从几个由它自己
按相关性排好、且有上限的切片里取并集。实测关键词路填充率只有 49-76%（相关性榨干了），
再加数量没用 —— **要加变体**。

而变体不能凭空想，得从真实数据里挖。@wavytalkofficial 第一轮 856 条就挖出了
#wavytalkthermalbrush(128)、#wavytalkhair(163)、#wavytalkpartner(20)
和 thermal brush / airshape pro / power wave 等一批产品名。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from . import config as C


@dataclass(slots=True)
class Term:
    kind: str          # "hashtag" | "keyword"
    value: str         # 搜索时实际用的字符串
    count: int         # 在第一轮里出现的次数
    use: bool = True   # 是否用于第二轮，用户可改
    note: str = ""     # 为什么建议不用

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value,
                "count": self.count, "use": self.use, "note": self.note}


def _has_stopword(text: str) -> str | None:
    for w in re.split(r"[\s_-]+", text.lower()):
        if w in C.MINE_STOPWORDS:
            return w
    return None


def mine_hashtags(raws: list[dict], token: str) -> list[Term]:
    """挖含品牌 token 的 hashtag。"""
    c: Counter[str] = Counter()
    for r in raws:
        for h in r.get("hashtags") or []:
            if not isinstance(h, dict):
                continue
            name = (h.get("name") or "").lower().strip()
            if name and token in name:
                c[name] += 1

    out: list[Term] = []
    for name, n in c.most_common():
        if n < C.MINE_MIN_HASHTAG_COUNT:
            continue
        t = Term("hashtag", name, n)
        if name == token:
            t.use, t.note = False, "第一轮已经搜过"
        elif (bad := _has_stopword(name.replace(token, ""))):
            t.use, t.note = False, f"含地区/店铺词 “{bad}”"
        out.append(t)
    return out


def mine_products(raws: list[dict], token: str, nickname: str) -> list[Term]:
    """挖 caption 里紧跟在品牌名后面的产品名。

    ⚠️ 必须先把 hashtag 从正文里剥掉。否则 "#wavytalkthermalbrush" 会被读成
    「品牌名 + 产品名 thermalbrush」，挖出一堆和 hashtag 搜索完全重复的词 ——
    实测不剥的话前 12 名有一半是重复的，等于一半预算在搜同一批视频。

    剥掉之后剩下的才是真正的自然语言写法：thermal brush / blowout boost /
    airshape pro / power wave —— 这些是 hashtag 搜不到的那部分内容。
    """
    # 品牌名在文案里连写和分写都有（"wavytalk" / "wavy talk"、"drdent" / "dr dent"）。
    # 不要去猜切分点 —— 老写法是把 token 从第 4 个字符切开去匹配，对 "wavytalk"
    # 恰好蒙对（wavy|talk），对 "drdent" 就会去找 "drde nt"，永远匹配不上，
    # 结果是多词品牌完全挖不到产品名。
    # 改成用用户输入的原始写法生成一个容忍空格的模式：用户输 "dr dent"，
    # 就得到 dr\s*dent，连写分写都能命中。
    # 空格插在哪儿都得认，两个方向都会发生：
    #   用户输 "wavytalk"，文案写 "wavy talk"
    #   用户输 "dr dent"，文案写 "drdent"
    # 所以别去猜切分点，直接允许每两个字母之间有任意空白。
    loose = r"\s*".join(re.escape(ch) for ch in token)
    brand = rf"(?:{re.escape(token)}|{loose})"
    pat = re.compile(rf"{brand}\s+([a-z]+(?:\s+[a-z]+)?)", re.I)
    c: Counter[str] = Counter()
    for r in raws:
        text = (r.get("text") or "").lower()
        text = re.sub(r"#\S+", " ", text)          # ← 关键：先剥 hashtag
        text = re.sub(r"@\S+", " ", text)
        for m in pat.finditer(text):
            phrase = re.sub(r"\s+", " ", m.group(1)).strip()
            if 3 <= len(phrase) <= 24:
                c[phrase] += 1

    out: list[Term] = []
    for phrase, n in c.most_common():
        if n < C.MINE_MIN_PRODUCT_COUNT:
            continue
        t = Term("keyword", f"{nickname} {phrase}", n)
        if (bad := _has_stopword(phrase)):
            t.use, t.note = False, f"含地区/店铺词 “{bad}”"
        elif len(phrase.split()) == 1 and len(phrase) < 5:
            t.use, t.note = False, "词太短，搜出来会很杂"
        out.append(t)
    return out


def mine(raws: list[dict], *, token: str, nickname: str) -> list[Term]:
    """挖出全部候选词。建议使用的排前面，同类型内按出现次数降序。

    额外做一次去重：若某个关键词去掉空格后正好等于某个 hashtag，说明两者会搜到
    同一批视频，保留 hashtag 那条（更精确），关掉关键词那条。
    """
    tags = mine_hashtags(raws, token)
    prods = mine_products(raws, token, nickname)

    tag_values = {t.value for t in tags}
    for p in prods:
        flat = re.sub(r"[^a-z0-9]", "", p.value.lower())
        if flat in tag_values:
            p.use, p.note = False, "与同名 hashtag 重复"

    terms = tags + prods
    terms.sort(key=lambda t: (not t.use, -t.count))
    return terms


def pick(terms: list[Term], limit: int = C.RECALL2_MAX_QUERIES,
         keyword_slots: int = 3) -> list[Term]:
    """从勾选的词里挑出实际要搜的，给关键词留固定名额。

    不留名额的话前 12 名会全是 hashtag（标签的出现次数天然更高）。但两者搜的
    不是同一批东西：hashtag 只覆盖打了标签的，关键词能捞到「正文写了产品名但
    没打标签」的那批 —— 而那批往往更自来水、更不像被 brief 过的。两边都要。
    """
    on = [t for t in terms if t.use]
    tags = [t for t in on if t.kind == "hashtag"]
    kws = [t for t in on if t.kind == "keyword"]
    n_kw = min(keyword_slots, len(kws), limit)
    return tags[: limit - n_kw] + kws[:n_kw]


def selected_payloads(terms: list[Term], *, per_run: int,
                      limit: int = C.RECALL2_MAX_QUERIES) -> list[tuple[str, dict]]:
    """把选中的词转成 Apify 调用参数。"""
    picked = pick(terms, limit)
    out: list[tuple[str, dict]] = []
    for t in picked:
        if t.kind == "hashtag":
            out.append((f"#{t.value}",
                        {"hashtags": [t.value], "resultsPerPage": per_run,
                         "shouldDownloadSubtitles": True}))
        else:
            out.append((t.value,
                        {"searchQueries": [t.value], "resultsPerPage": per_run,
                         "shouldDownloadSubtitles": True}))
    return out
