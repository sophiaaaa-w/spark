"""按 hook / body / CTA 三段分别找共性 —— 取代原来的「整体 pattern」聚类。

为什么废弃整体 pattern：实测分得太粗，把三个独立决策捆在了一起。两条视频可能
钩子一样但 CTA 完全不同，硬归成一个 pattern 就丢了信息。而真实的达人 brief
本来就是分段写的：开头怎么抓人、中间讲哪几个卖点、结尾怎么导流。

三个关键设计：

1. **hook 和 CTA 的原文由代码切好再喂给模型**，不让它在长转录里自己找。
   实测错误：@acquiredstyle 结尾被标成 CREDENTIAL(official endorser)，
   但原文最后一句是 "I'm so excited for you guys to try this out..."，
   那是软性 CTA。根因就是模型凭整体印象判断，没回去核对具体位置。

2. **先定封闭词表再逐条打标**。不让模型边看边造词，否则 50 条会出现 50 个标签，
   根本没法统计频次。

3. **hook 分类要是修辞手法，不是内容复述**。
   ✓ blowout result preview / salon 平替
   ✗ 「她说这个吹风机很好用」
"""
from __future__ import annotations

import base64
import json
import logging

from anthropic import Anthropic

from . import config as C
from .models import Video
from .subtitles import Cue

log = logging.getLogger(__name__)

OPENING_WINDOW_S = 8.0     # 给模型看的开头长度，让它自己判断 hook 在哪结束
CLOSING_WINDOW_S = 8.0


# ---------------------------------------------------------------- 原文切片

def slice_opening(cues: list[Cue], seconds: float = OPENING_WINDOW_S) -> str:
    return " ".join(c.text for c in cues if c.start < seconds).strip()


def slice_closing(cues: list[Cue], seconds: float = CLOSING_WINDOW_S) -> str:
    if not cues:
        return ""
    end = max(c.end for c in cues)
    return " ".join(c.text for c in cues if c.end >= end - seconds).strip()


def middle_transcript(cues: list[Cue], limit: int = 900) -> str:
    text = " ".join(c.text for c in cues)
    return text[:limit]


# ---------------------------------------------------------------- Schema

def _taxonomy(name: str, desc: str, n_lo: int, n_hi: int) -> dict:
    return {
        "type": "array",
        "description": f"{desc} Propose {n_lo}-{n_hi} types AFTER scanning all "
                       f"videos. This is a closed vocabulary — every video must be "
                       f"labelled with ids from this list, so keep it tight.",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string",
                         "description": "2-5 words, English, plain. Names the "
                                        "TECHNIQUE, not the content."},
                "description": {"type": "string",
                                "description": "One sentence: what the creator "
                                               "actually does. No theory."},
            },
            "required": ["id", "name", "description"],
        },
    }


TOOL = {
    "name": "report_breakdown",
    "description": "Define the taxonomies, then label every video section by section.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "REQUIRED. Product category in 2-3 plain words "
                               "(e.g. hair tools, skincare). Never leave blank.",
            },
            "hook_types": _taxonomy(
                "hook", "How the first few seconds grab attention. Name the RHETORICAL "
                "DEVICE, not the content. Good: 'Blowout result preview', "
                "'Salon dupe claim', 'Wrong all along'. "
                "Bad: 'She shows her hair' (that's a summary, not a device).",
                4, 8),
            "body_types": _taxonomy(
                "body", "How the middle of the video is organised. "
                "e.g. 'Step-by-step demo', 'Before/after split', 'Q&A with friend'.",
                3, 6),
            "cta_types": _taxonomy(
                "cta", "What the final line asks the viewer to do. "
                "e.g. 'Discount code', 'Link in bio', 'Soft encouragement', "
                "'Comment bait'. Use 'No CTA' as one type if many videos just end.",
                3, 6),
            "selling_points": {
                "type": "array",
                "description": "Closed vocabulary of the product benefits mentioned "
                               "across all videos. 6-14 entries. Short and concrete "
                               "so they can be counted. Phrase them so a reader "
                               "understands without explanation, but do NOT explain "
                               "why they persuade.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string",
                                 "description": "3-6 words. e.g. 'adds moisture while "
                                                "straightening', 'wraps hair "
                                                "automatically', 'no snagging or pull'."},
                    },
                    "required": ["id", "name"],
                },
            },
            "videos": {
                "type": "array",
                "description": "One entry per input video. Do not skip any.",
                "items": {
                    "type": "object",
                    "properties": {
                        "video_id": {"type": "string"},
                        "hook_type_ids": {
                            "type": "array",
                            "description": "Usually one. Use two only when the hook "
                                           "genuinely combines two devices.",
                            "items": {"type": "integer"},
                        },
                        "hook_ends_at": {
                            "type": "number",
                            "description": "Second at which the hook stops and the "
                                           "body begins. Judge from content, not a "
                                           "fixed number.",
                        },
                        "hook_quote": {
                            "type": "string",
                            "description": "The opening line, VERBATIM from the "
                                           "opening text supplied. Never paraphrase.",
                        },
                        "body_type_ids": {"type": "array", "items": {"type": "integer"}},
                        "selling_point_ids": {
                            "type": "array",
                            "description": "Which benefits this video actually "
                                           "mentions. Empty if none.",
                            "items": {"type": "integer"},
                        },
                        "cta_type_ids": {"type": "array", "items": {"type": "integer"}},
                        "cta_quote": {
                            "type": "string",
                            "description": "The final line, VERBATIM from the closing "
                                           "text supplied. Empty string if no CTA.",
                        },
                    },
                    "required": ["video_id", "hook_type_ids", "hook_ends_at",
                                 "hook_quote", "body_type_ids", "selling_point_ids",
                                 "cta_type_ids", "cta_quote"],
                },
            },
        },
        "required": ["category", "hook_types", "body_types", "cta_types",
                     "selling_points", "videos"],
    },
}


SYSTEM = """You are reverse-engineering the brief a brand gave to creators.

These videos all mention one brand and all cleared a quality bar. Many were seeded
by the brand, so they carry traces of the instructions the brand handed out. Your
job is to surface those traces by breaking every video into three slots and finding
what repeats in each slot.

## The three slots

HOOK   the first few seconds, until the video stops trying to stop the scroll
BODY   everything between the hook and the closing line
CTA    the final line or two — what the viewer is asked to do

These are independent choices. Two videos can share a hook device and use totally
different CTAs. Never assume they travel together.

## Order of work

1. Read the opening lines of ALL videos. Then propose the hook taxonomy.
2. Same for body, CTA, and selling points.
3. Only then go back and label each video using those closed vocabularies.

Do not invent a label while labelling. If a video fits nothing, that means your
taxonomy is wrong — revise it, don't add a one-off.

## Hook types must name the DEVICE

  ✓ "Blowout result preview"   — opens on the finished hair before any talking
  ✓ "Salon dupe claim"         — positions the tool against a salon visit
  ✓ "Wrong all along"          — tells the viewer they have been doing it wrong
  ✗ "She talks about her hair" — that is a summary, useless as a template

The test: could someone in the same category build a new video from this label
alone? If not, the label is a summary, not a device.

## A hook is VISUAL first

Every video is supplied with two frames from its first three seconds. Look at
them. In this format the opening shot usually does more work than the opening
sentence — a finished blowout on screen at 0.5s IS the hook, whether or not
anyone is talking.

**Roughly half of these videos have no speech at all. They still have hooks.**
"No spoken hook" is not a hook type — it is a failure to look at the frames.
Never create a category for the absence of speech. If there is no voiceover,
classify from what is on screen.

Same rule for body and CTA: a silent video still has a body (what it shows) and
often still has a CTA (on-screen text, a product held to camera, a caption ask).
Only use a "no CTA" label when the video genuinely just stops.

## Quotes must be verbatim

`hook_quote` comes from the supplied `opening` text. `cta_quote` comes from the
supplied `closing` text. Both are already sliced for you — do not go looking
elsewhere in the transcript, and never clean up, shorten or improve the wording.
Repeated exact phrasing across creators is the fingerprint of a brief; paraphrasing
destroys the very thing we are looking for.

If a video has no speech, use "" for the quotes and label from the caption.

## Selling points

Only list benefits the video ACTUALLY mentions. Keep each one short and concrete.
A reader should understand it without explanation — but do not explain why it
persuades anyone. That is not what this field is for.

## Language

Plain English. Banned: cognitive load, social proof, value proposition, pain point,
brand equity, salience, resonate, leverage.
"""


# ---------------------------------------------------------------- 调用

def describe(v: Video, cues: list[Cue], products: list[str]) -> dict:
    d = {
        "video_id": v.id,
        "duration": v.duration,
        "caption": v.caption[:400],
        "hashtags": v.hashtags[:10],
    }
    if products:
        d["products_mentioned"] = products
    if cues:
        d["opening"] = slice_opening(cues)
        d["closing"] = slice_closing(cues)
        d["transcript_middle"] = middle_transcript(cues)
    else:
        d["opening"] = ""
        d["closing"] = ""
        d["note"] = "NO SPEECH — classify hook/body/CTA from the frames and caption"
    return d


def _blocks(videos, cues, tags, hook_frames) -> list[dict]:
    """每条视频一段文字 + 前 3 秒的 2 张帧图。

    图必须紧跟在对应的文字后面，否则模型分不清哪张图属于哪条视频。
    """
    out: list[dict] = []
    for v in videos:
        out.append({
            "type": "text",
            "text": json.dumps(describe(v, cues.get(v.id, []), tags.get(v.id, [])),
                               ensure_ascii=False),
        })
        for f in hook_frames.get(v.id, []):
            out.append({"type": "text", "text": f"↑ frame at {f.t}s"})
            out.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg",
                           "data": base64.b64encode(f.path.read_bytes()).decode()},
            })
    return out


def run(videos: list[Video], cues: dict[str, list[Cue]],
        product_tags: dict[str, list[str]],
        hook_frames: dict | None = None, *, brand: str, bio: str = "",
        api_key: str | None = None) -> dict:
    hook_frames = hook_frames or {}
    n_speech = sum(1 for v in videos if cues.get(v.id))
    n_frames = sum(len(f) for f in hook_frames.values())

    header = (
        f"Brand: {brand}\n"
        f"{f'Brand bio: {bio}' if bio else ''}\n"
        f"{len(videos)} videos. {n_speech} have a spoken transcript — "
        f"the other {len(videos) - n_speech} are silent and must be classified "
        f"from their frames.\n"
        f"{n_frames} frames supplied, two per video from its first three seconds.\n\n"
        f"`opening` and `closing` are already sliced from the timestamped subtitles. "
        f"Quote from those fields only, verbatim.\n"
    )

    client = Anthropic(api_key=api_key or C.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=C.MODEL_CLUSTER,
        max_tokens=16000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_breakdown"},
        messages=[{"role": "user",
                   "content": [{"type": "text", "text": header}]
                   + _blocks(videos, cues, product_tags, hook_frames)}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise RuntimeError("模型没有调用工具")
