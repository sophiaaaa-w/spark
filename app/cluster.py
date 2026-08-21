"""Claude 调用 A —— 把 Top N 条视频聚成 1-3 个共性 pattern。

输入只有文字（caption + hashtag + 时长 + 自带字幕），不看图。
找共性不需要看画面，30 条多模态又慢又贵。

这是整个项目最不稳定的一环。第一版几乎必然输出「都用了吸引人的开头」这种废话，
所以 prompt 里三件事必须卡死：
  1. 强制先逐条打标再归纳（不让它直接跳到结论）
  2. 每个 pattern 至少 5 条支撑，不足则少出。宁可只出 1 个也不硬凑
  3. 给成组的反例，明确写出什么样的输出不可接受
"""
from __future__ import annotations

import json
import logging
import statistics

from anthropic import Anthropic

from . import config as C
from .models import Video

log = logging.getLogger(__name__)


TOOL = {
    "name": "report_patterns",
    "description": "Tag every video first, then report the patterns you found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "REQUIRED. The product category in plain everyday words, "
                               "2-3 words max. Examples: hair care, skincare, "
                               "activewear, robot vacuums, sunscreen. This is shown "
                               "in the UI — never leave it empty.",
            },
            "assignments": {
                "type": "array",
                "description": "One entry for EVERY input video. Do not skip any.",
                "items": {
                    "type": "object",
                    "properties": {
                        "video_id": {"type": "string"},
                        "pattern_id": {
                            "type": ["integer", "null"],
                            "description": "Which pattern this video belongs to. "
                                           "Use null if it doesn't fit — never force it.",
                        },
                        "beats": {
                            "type": "array",
                            "description": "This video's structure as an ordered beat "
                                           "sequence, 3-5 beats. Each beat is "
                                           "FUNCTION(what specifically). "
                                           "Use a small closed vocabulary for FUNCTION: "
                                           "HOOK, PROOF, SPEC, DEMO, STORY, "
                                           "CREDENTIAL, RESULT, CTA. "
                                           "Example: "
                                           "[\"HOOK(result preview)\", "
                                           "\"SPEC(names the tech)\", "
                                           "\"DEMO(step by step)\", \"RESULT(after shot)\"]. "
                                           "Two videos in the same pattern must have "
                                           "closely matching beat sequences — this is "
                                           "how the grouping gets checked.",
                            "items": {"type": "string"},
                        },
                        "evidence": {
                            "type": "string",
                            "description": "The specific thing that made you decide. "
                                           "Quote the actual words or name the actual "
                                           "action. Max 20 words. English.",
                        },
                    },
                    "required": ["video_id", "pattern_id", "beats", "evidence"],
                },
            },
            "patterns": {
                "type": "array",
                "description": f"At most {C.MAX_PATTERNS}. Each needs at least "
                               f"{C.MIN_VIDEOS_PER_PATTERN} videos behind it. "
                               f"Output fewer rather than padding.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "beat_signature": {
                            "type": "array",
                            "description": "The beat sequence shared by the videos in "
                                           "this pattern. Must be consistent with the "
                                           "per-video `beats` you assigned. Same closed "
                                           "vocabulary. 3-5 beats.",
                            "items": {"type": "string"},
                        },
                        "move_name": {
                            "type": "string",
                            "description": "Name for this move, 2-4 words, English. "
                                           "It has to be something a content team would "
                                           "actually say out loud in a meeting. "
                                           "Good: Throw-away open / Badge drop / "
                                           "Just three things / Wrong all along. "
                                           "Bad: Destructive negation / Authority "
                                           "signalling / Triadic structuring.",
                        },
                        "why_it_works": {
                            "type": "string",
                            "description": "Why this move works IN THIS CATEGORY. "
                                           "Explain the mechanism, don't summarise the "
                                           "videos. 2-3 sentences, English, plain words. "
                                           "Must point at something a viewer of this "
                                           "category specifically cares about.",
                        },
                        "hook_examples": {
                            "type": "array",
                            "description": "Exactly 3 real quotes, verbatim from the "
                                           "transcript or caption. Do not paraphrase, "
                                           "do not translate, do not clean them up.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "video_id": {"type": "string"},
                                    "quote": {"type": "string"},
                                },
                                "required": ["video_id", "quote"],
                            },
                        },
                    },
                    "required": ["id", "beat_signature", "move_name",
                                 "why_it_works", "hook_examples"],
                },
            },
        },
        "required": ["category", "assignments", "patterns"],
    },
}


# Prompt 用英文写，因为输出必须是英文 —— 实测中文 prompt 会让模型输出中文，
# 而产品默认语言是英文，中文是后面单独的翻译层。
SYSTEM = f"""You are analysing creator videos on TikTok that mention one brand.
Your job: find what these videos did right, in a way someone could reuse.

What these videos have in common is not luck. Every one of them got far more views
than that same creator normally gets. So something about the content itself worked.
Find that thing.

## Order of work — do not skip ahead

For EVERY video, first write down its `beats`: the ordered sequence of what the
video does, using the closed vocabulary (HOOK, PROOF, SPEC, DEMO, STORY,
CREDENTIAL, RESULT, CTA). Only after every video has a beat sequence do you group
them.

Do NOT think up a few tidy conclusions first and then sort videos into them.

## Group by STRUCTURE, not by topic

This is the part that gets checked. Two videos belong to the same pattern only if
their beat sequences closely match — same functions, same order.

  ✗ WRONG grouping — same topic, different structure:
      A: HOOK(result preview) → SPEC(names tech) → DEMO(steps) → RESULT
      B: HOOK(comedy skit) → DEMO(steps) → SPEC(names tech) → RESULT
    Both "walk through the product", but A opens on the payoff and B opens on a
    joke. A viewer copying A would build a different video than one copying B.
    These are two patterns, or B is unclustered.

  ✓ RIGHT grouping — same skeleton:
      A: HOOK(result preview) → SPEC(names tech) → DEMO(steps) → RESULT
      C: HOOK(result preview) → SPEC(names tech) → DEMO(steps)
      D: HOOK(result preview) → SPEC(names tech) → DEMO(steps) → CTA

If a video's structure doesn't line up with any group, its pattern_id is null.
A smaller, structurally tight group is far more useful than a large loose one.

## Output that will be rejected

These are failures, because a reader cannot do anything with them:

  ✗ "These videos all use an attention-grabbing opening"
  ✗ "Creators share authentic personal experiences"
  ✗ "They build trust through social proof"
  ✗ "The content is concise with a fast pace"

Every one of those is true of almost any video in any category. They say nothing.

## Output that is good

  ✓ move_name: "Throw-away open"
    why_it_works: Opens by binning a product the category treats as non-negotiable.
    Hair-care viewers have money sunk into the bottles on their shelf, so attacking
    that shelf directly is what stops the scroll. The discard has to land inside the
    first half-second, and it has to be destructive rather than additive.

  ✓ move_name: "Badge drop"
    why_it_works: States a job title in the opening line. In hair care the audience
    assumes everyone is being paid to say this, so a credential they can verify on
    the spot — licensed stylist, colourist, formulator — does more work than any
    adjective.

The difference: a good output points at one concrete, copyable action, and explains
why that action lands with people who care about THIS category.

## Hard rules

- At most {C.MAX_PATTERNS} patterns
- Each pattern needs at least {C.MIN_VIDEOS_PER_PATTERN} videos behind it
- **If the evidence only supports one pattern, output one.** Forcing unrelated
  videos into a group destroys the credibility of the whole analysis
- Videos that don't fit get pattern_id null. Report that honestly
- Write in English, in plain words. Someone who has never worked in marketing
  should understand it on the first read
- Banned vocabulary: cognitive load, social proof, value proposition, pain point,
  brand equity, salience, resonate, leverage
- Quotes in hook_examples must be verbatim. Never invent or polish a quote
"""


def _describe(v: Video, subtitle_text: str) -> dict:
    """喂给模型的单条视频描述。只给文字，不给图。"""
    d = {
        "video_id": v.id,
        "duration_seconds": v.duration,
        "caption": v.caption[:600],
        "hashtags": v.hashtags[:12],
        "plays": v.plays,
        "baseline_multiple": v.baseline_multiple,
        "creator_followers": v.author.followers,
    }
    if subtitle_text:
        d["spoken_transcript"] = subtitle_text[:1200]
    return d


def build_prompt(videos: list[Video], subtitles: dict[str, str],
                 *, brand: str, category_hint: str = "") -> str:
    payload = [_describe(v, subtitles.get(v.id, "")) for v in videos]
    hint = f"Brand account bio: {category_hint}\n" if category_hint else ""
    n_sub = sum(1 for v in videos if subtitles.get(v.id))
    return (
        f"Brand: {brand}\n"
        f"{hint}"
        f"{len(videos)} videos, {n_sub} of them have a spoken transcript.\n\n"
        # category 在 schema 里标了必填，但实测模型仍会漏掉（三次里三次），
        # 所以在正文里再要求一次
        f"Start by filling in `category` — 2-3 plain words for what this brand "
        f"sells, inferred from the bio and the videos. Never leave it blank.\n\n"
        f"Then go through every video below one at a time before grouping them.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def annotate_patterns(result: dict, videos: list[Video]) -> dict:
    """把模型的输出和真实数据对账，补上代码该算的数字。

    占比和基线倍数中位数由代码算，不让模型算 —— 模型算数不可靠，
    而这两个数字直接决定用户会选哪条路。
    """
    by_id = {v.id: v for v in videos}
    assign = {a["video_id"]: a.get("pattern_id")
              for a in result.get("assignments", [])}

    # 把归类结果写回 Video 对象
    for vid, pid in assign.items():
        if vid in by_id:
            by_id[vid].pattern_id = pid

    # 保留模型的原始输出，方便调试时看清是模型的问题还是过滤的问题
    result["raw_patterns"] = list(result.get("patterns", []))

    kept, dropped = [], []
    for p in result.get("patterns", []):
        members = [by_id[vid] for vid, pid in assign.items()
                   if pid == p["id"] and vid in by_id]
        p["share_count"] = len(members)
        p["share_total"] = len(videos)
        p["member_ids"] = [m.id for m in members]
        if len(members) < C.MIN_VIDEOS_PER_PATTERN:
            log.info("pattern %s 只有 %d 条支撑，低于下限 %d，丢弃",
                     p.get("move_name"), len(members), C.MIN_VIDEOS_PER_PATTERN)
            dropped.append(p)
            continue
        # 互动率是输出维度，不只是门槛。占比说明品牌推得多不多，
        # ER 说明观众买不买账 —— 两者交叉才有判断价值：
        #   占比高 + ER 高 → brief 里的招且有用
        #   占比高 + ER 低 → brief 让大家这么拍但没人买账   ← 最值钱
        #   占比低 + ER 高 → 少有人做但一做就灵
        p["median_engagement"] = round(
            statistics.median(m.engagement_rate for m in members), 4)
        p["median_plays"] = int(statistics.median(m.plays for m in members))
        p["median_score"] = round(statistics.median(m.score for m in members), 3)
        # 深度模式才有基线倍数，MVP 不填
        multiples = [m.baseline_multiple for m in members if m.baseline_multiple]
        p["median_multiple"] = (round(statistics.median(multiples), 1)
                                if multiples else None)
        # 占比薄的标出来让用户自己判断，而不是替他砍掉
        p["thin_evidence"] = (len(members) / max(len(videos), 1)) < C.THIN_EVIDENCE_SHARE
        kept.append(p)
    result["dropped_patterns"] = dropped

    # 占比 = 品牌推得多不多；median_score = 观众买不买账。
    # 两者交叉才有判断价值，而且必须用**占比**而不是排名来判断「大家都在拍」——
    # 三个 pattern 时排名第二可能只占 12%，那不叫「大家都在拍」。
    #
    # 效果用 median_score（0.7 播放 + 0.2 互动率 + 0.1 播放粉丝比）而不是单看 ER：
    # 实测有个 pattern ER 只有 4.5% 但播放中位数是别人的 26 倍 —— 只看 ER 会把
    # 传播力最强的那个误判成失败。
    kept.sort(key=lambda p: p["share_count"], reverse=True)
    for i, p in enumerate(kept, start=1):
        p["rank"] = i
        p["share_ratio"] = round(p["share_count"] / max(p["share_total"], 1), 3)
        p["highest_lift"] = False
        p["underperforms"] = False

    if len(kept) >= 2:
        by_eff = sorted(kept, key=lambda p: p["median_score"], reverse=True)
        best, worst = by_eff[0], by_eff[-1]
        # 少有人做但一做就灵：占比低，效果显著高于第二名
        if (best["share_ratio"] <= C.LOW_SHARE_RATIO
                and best["median_score"] >= by_eff[1]["median_score"] * C.HIGHEST_LIFT_MARGIN):
            best["highest_lift"] = True
        # 大家都在拍但观众不买账：占比高，效果却是最低的那个
        if (worst["share_ratio"] >= C.HIGH_SHARE_RATIO
                and worst is not best
                and worst["median_score"] * C.HIGHEST_LIFT_MARGIN <= best["median_score"]):
            worst["underperforms"] = True

    result["patterns"] = kept
    result["unclustered_count"] = sum(1 for pid in assign.values() if pid is None)
    # 模型偶尔会漏掉 category（schema 标了必填也不保证），给个兜底
    if not result.get("category"):
        result["category"] = "unknown"
        log.warning("模型没返回 category，已置为 unknown")
    return result


def run(videos: list[Video], subtitles: dict[str, str], *, brand: str,
        category_hint: str = "", api_key: str | None = None) -> dict:
    client = Anthropic(api_key=api_key or C.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=C.MODEL_CLUSTER,
        max_tokens=8000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_patterns"},
        messages=[{
            "role": "user",
            "content": build_prompt(videos, subtitles, brand=brand,
                                    category_hint=category_hint),
        }],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return annotate_patterns(dict(block.input), videos)
    raise RuntimeError("模型没有调用工具，输出：" + str(msg.content)[:500])
