"""Claude 调用 B —— 把一个 pattern 拆成左右两栏的结构时间轴。

输入：骨架视频的关键帧 + 带时间戳的字幕 + 该 pattern 的真实原话
输出：4-6 段，每段左栏是「真实视频做了什么」，右栏是「这一招叫什么、起什么作用」

设计上的三个关键决定：

1. **整条时间轴来自同一条骨架视频**，不是多条合成。
   时间段、截图、口播全部出自它，可以点开原视频逐帧核对。合成的话截图和文字
   会对不上，用户一眼看穿。

2. **先抽帧再划段落**。段落是模型看完 12 张帧图之后才划分的，所以流程必须是
   抽帧 → 全部喂给模型 → 模型输出段落并为每段指定 frame_index。

3. **右栏要短**。它的职能是给左边那句话命名和定性，不是解释原理 ——
   原理只在 pattern 头部的 why_it_works 写一次。模型天然倾向于解释「为什么
   有效」，一放开就写三行，所以 function 硬性限制 25 词。
"""
from __future__ import annotations

import base64
import json
import logging
import re

from anthropic import Anthropic

from . import config as C
from .frames import Clip
from .subtitles import Cue

log = logging.getLogger(__name__)


TOOL = {
    "name": "report_timeline",
    "description": "Break this one video into 4-6 structural segments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "description": f"{C.TIMELINE_MIN_SEGMENTS}-{C.TIMELINE_MAX_SEGMENTS} "
                               "segments covering the whole video in order. "
                               "Do not go second-by-second — this is a template, "
                               "not a shooting script.",
                "items": {
                    "type": "object",
                    "properties": {
                        "t_start": {"type": "number"},
                        "t_end": {"type": "number"},
                        "label": {
                            "type": "string",
                            "description": "What this segment does structurally, "
                                           "1-2 words, uppercase. "
                                           "e.g. HOOK / PROOF / CREDIBILITY / "
                                           "PAYOFF / CTA",
                        },
                        "frame_index": {
                            "type": "integer",
                            "description": "Which of the supplied frames best shows "
                                           "this segment. Use the index printed on "
                                           "the frame.",
                        },
                        "visual": {
                            "type": "string",
                            "description": "What is physically on screen. Describe the "
                                           "action and the framing. No interpretation. "
                                           "One sentence.",
                        },
                        "vo": {
                            "type": "string",
                            "description": "The spoken words in this segment, verbatim "
                                           "from the transcript. Empty string if the "
                                           "segment has no speech.",
                        },
                        "move_name": {
                            "type": "string",
                            "description": "Name for what the creator is doing here. "
                                           "2-4 words a content team would say out "
                                           "loud. Good: Throw-away open / Badge drop / "
                                           "Just three things. "
                                           "Bad: Destructive negation / Authority "
                                           "signalling.",
                        },
                        "function": {
                            "type": "string",
                            "description": f"What this move does for the viewer. "
                                           f"HARD LIMIT {C.FUNCTION_MAX_WORDS} WORDS. "
                                           "Plain English. Do NOT explain the "
                                           "underlying psychology — that is written "
                                           "once in why_it_works. Just name the effect.",
                        },
                    },
                    "required": ["t_start", "t_end", "label", "frame_index",
                                 "visual", "vo", "move_name", "function"],
                },
            },
        },
        "required": ["segments"],
    },
}


SYSTEM = f"""You are breaking down one TikTok video into a reusable structure.

The frames are given in order with their timestamp and index. The transcript is
timestamped. Use both.

## What each column is for

LEFT (visual + vo): what actually happened. Facts only, no interpretation.
RIGHT (move_name + function): what to call this move and what it does.

## The right column must be SHORT

`function` is capped at {C.FUNCTION_MAX_WORDS} words. Its job is to NAME and
CLASSIFY, not to explain. The underlying reasoning is written once elsewhere —
repeating it here is a failed output.

  ✓ move_name: "Throw-away open"
    function: "Bins a product almost everyone owns, so the viewer feels their own
    shelf is being called out"

  ✗ function: "This creates cognitive dissonance by challenging the viewer's prior
    beliefs about their purchasing decisions, which increases attention and drives
    higher retention in the critical first three seconds..."

## Language rules

- Plain English. Someone who never worked in marketing should get it first read.
- Banned: cognitive load, social proof, value proposition, pain point, brand
  equity, salience, resonate, leverage, engagement.
- `move_name` must be sayable in a meeting. Not academic.
- The right column may use category vocabulary (heat damage, sectioning, blowout)
  but must NOT name a specific brand, product model, or creator handle. Someone
  in the same category with a different product should be able to reuse it.

## Segments

- {C.TIMELINE_MIN_SEGMENTS}-{C.TIMELINE_MAX_SEGMENTS} segments, in order, covering
  the video
- `vo` must be verbatim from the transcript. If a segment is silent, use ""
- `frame_index` must be one of the indices actually supplied
"""


def _frame_blocks(clip: Clip) -> list[dict]:
    """把帧图转成多模态输入。每张前面标上序号和时间，模型才能引用。"""
    blocks: list[dict] = []
    for f in clip.frames:
        blocks.append({"type": "text", "text": f"frame {f.index} @ {f.t:.1f}s"})
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(f.path.read_bytes()).decode(),
            },
        })
    return blocks


def _transcript(cues: list[Cue]) -> str:
    if not cues:
        return "(no speech in this video)"
    return "\n".join(f"[{c.start:.1f}-{c.end:.1f}] {c.text}" for c in cues)


def run(clip: Clip, cues: list[Cue], *, pattern: dict, category: str,
        api_key: str | None = None) -> dict:
    """拆解一个 pattern 的骨架视频。"""
    client = Anthropic(api_key=api_key or C.ANTHROPIC_API_KEY)

    header = (
        f"Category: {category}\n"
        f"Pattern being illustrated: {pattern.get('move_name')}\n"
        f"Why it works (already written, do NOT repeat in the right column):\n"
        f"  {pattern.get('why_it_works')}\n\n"
        f"Video duration: {clip.video.duration}s\n"
        f"Caption: {clip.video.caption[:400]}\n\n"
        f"Transcript:\n{_transcript(cues)}\n\n"
        f"{len(clip.frames)} frames follow, in order."
    )

    msg = client.messages.create(
        model=C.MODEL_PATTERN,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_timeline"},
        messages=[{"role": "user",
                   "content": [{"type": "text", "text": header}] + _frame_blocks(clip)}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            out = _attach_frames(dict(block.input), clip)
            return verify_verbatim(out, cues)
    raise RuntimeError("模型没有调用工具")


def _normalize(s: str) -> str:
    """去标点、压空格、转小写，用于比对口播是否逐字。"""
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def verify_verbatim(result: dict, cues: list[Cue]) -> dict:
    """校验每段的 vo 是否真的逐字来自字幕。

    不能只靠 prompt 要求「必须逐字」—— 字幕文件在我们手里，直接对一遍就是保证。

    为什么逐字这么重要：
      · 重复出现的原句就是品牌 brief 的指纹。允许改写，各人的措辞会被规整成
        不同表达，那个指纹当场消失 —— 而挖 brief 正是这个产品的目标
      · hook 的价值全在措辞，转述之后只剩一个谁都想得到的概念
      · 左栏的全部价值是「可点开原视频核对」，一处对不上，整份 brief 都被打折
      · 最危险的是善意润色：模型会顺手改对 ASR 错别字、删掉口语重复，
        用户以为在看达人原话，其实在看模型的文笔 —— 这种错误是隐形的

    截断是允许的（一段长口播塞不进一行）。ASR 本身的错别字要原样保留。
    """
    full = _normalize(" ".join(c.text for c in cues))
    bad = []
    for seg in result.get("segments", []):
        vo = (seg.get("vo") or "").strip().rstrip("…").rstrip(".")
        if not vo:
            seg["vo_verified"] = None          # 本段无口播
            continue
        ok = _normalize(vo) in full
        seg["vo_verified"] = ok
        if not ok:
            bad.append(vo[:60])
    result["vo_unverified"] = bad
    if bad:
        log.warning("有 %d 段口播不是逐字原话：%s", len(bad), bad[:2])
    return result


def _attach_frames(result: dict, clip: Clip) -> dict:
    """把 frame_index 换成真实的图片 URL，并做边界修正。"""
    by_index = {f.index: f for f in clip.frames}
    fallback = clip.frames[0] if clip.frames else None
    for seg in result.get("segments", []):
        f = by_index.get(seg.get("frame_index"), fallback)
        seg["frame_url"] = f.url if f else None
        seg["frame_t"] = f.t if f else None
        # 模型偶尔会给超出视频长度的时间
        seg["t_end"] = min(float(seg.get("t_end", 0)), float(clip.video.duration))
    result["skeleton_video_id"] = clip.video.id
    result["skeleton_video_url"] = clip.video.url
    result["skeleton_author"] = clip.video.author.username
    return result


def pick_skeleton(members, subtitles: dict[str, list[Cue]]):
    """挑骨架视频：优先有口播的，其次得分最高的。

    砍掉屏幕字之后，没口播的视频左栏会空掉一半，所以有字幕是硬要求。
    但某些品类（服饰试穿、工具演示）大量内容本来就没口播 —— 若整组都没有，
    退而取得分最高的那条，时间轴只出画面描述并注明原因。
    """
    with_speech = [m for m in members if subtitles.get(m.id)]
    pool = with_speech or list(members)
    return max(pool, key=lambda v: v.score), bool(with_speech)
