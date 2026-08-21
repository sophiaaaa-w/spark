# Spark — PRD

> 2026-08-19 定稿。产品范围已收敛到「爆款素材筛选」，内容结构拆解暂不交付。

---

## 一句话

输入一个品牌名，输出该品牌近 30 天内**过硬门槛的达人视频**（最多 50 条），
带封面、关键数据和来源标注，可按维度筛选。

**解决的痛点**：TikTok 搜索没有日期、播放量、格式的筛选，研究竞品爆款要先人工翻几百条。

---

## 两个页面

### 页面 1 · 搜索

```
                      SPARK

                Skip 900 videos.
                Watch 50.

     TikTok's search filters suck — no date, no reach, no format.
     So researching a competitor's viral videos means digging
     through hundreds first. Spark does the digging.

     Last 30 days · 10k+ views · 3%+ engagement · 10–90 sec
              English · Video only · Creators only

          ┌──────────────────────┐  ┌─────────┐
          │ wavytalk         │  │ Start digging │
          └──────────────────────┘  └─────────┘
            ✓ Looks good — plenty of videos to work with
```

**七个筛选标签是陈述不是控件**，说明「我们已经替你筛了这些」。
结果页的筛选器用同一套 pill 样式，形成视觉呼应。

**输入品牌名而不是官号 handle。** 输入的唯一用途是推导搜索词，
而品牌名推导得一样好（`wavy talk` → `#wavytalk`）。handle 唯一多给的信息是
官号 ID，实测它对结果的贡献是 **0 条** —— 品牌自己发的 169 条视频，
在轮到官号过滤之前就已经被互动率等门槛全部挡掉；去掉 ID 重跑结果一模一样。
既然输入什么都不影响结果，就用对用户最简单的。

**输入框下方只有一行状态**，不展示推导出的搜索词。用户看到 `#wavytalk`
也无从判断对错，摆出来只会让他盲目点确认。他唯一判断得了的是「素材够不够」，
所以后台探 20 条，返回一句话。这一行的作用是在花掉 10 分钟前拦住拼写错误。

### 页面 2 · 结果

```
  SPARK                                           50 videos
  ─────────────────────────────────────────────────────────

  wavytalk
  近 30 天

  Crawled 2,572 videos · 50 cleared every bar · max 3 per creator
  Last 30 days · 10k+ views · 3%+ engagement · 10–90 sec · English
  · Video only · Creators only

  ─────────────────────────────────────────────────────────
  FOLLOWERS   All 50 · <100k 12 · 100k–1M 19 · 1M+ 19
  VOICEOVER   All 50 · Has VO 27 · No VO 23
  ─────────────────────────────────────────────────────────

  Found via: "wavy talk" · #wavytalk · #wavytalkhair · +10 more
  50 shown · ■ 青色来源 = 只有靠挖词才找到的（23 of 50）

  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │⚡Views 40×    │ │              │ │              │
  │  followers   │ │              │ │              │
  │   [封面]      │ │   [封面]      │ │   [封面]      │
  │         61s  │ │         21s  │ │         13s  │
  └──────────────┘ └──────────────┘ └──────────────┘
  1.2M views ·     1.6M views ·     1.7M views ·
  4.5% engagement  9.6% engagement  5.6% engagement
  @rissas.hair     @marianamoragui1 @abigaillinnn
  29.7k followers  194k followers   1.2M followers
   · Has VO         · No VO           · No VO
  #wavytalkthermal "wavy talk"      "wavy talk"
  brush
```

---

## 交互

| 元素 | 行为 |
|---|---|
| 输入框失焦 | 后台探 20 条（约 30s），下方出现一行状态 ✓ / ⚠ |
| Start digging | 跳转进度页，完成后进结果页 |
| 筛选 pill | 点击即时过滤，不刷新，可多个维度叠加 |
| 卡片 | 整张可点，新标签页打开 TikTok 原视频 |
| 排序 | 固定按播放量降序，不做切换 |

**筛选器只有两个维度**：粉丝量级、有无口播。时长和广告标记先不做，避免筛选器
比内容还多。

---

## 每张卡片显示什么

```
封面帧                     本地抽的第一帧（CDN 封面链接会过期）
1.2M views · 4.5% engagement   标签写全，不要裸数字
@rissas.hair
29.7k followers · Has VO       真实粉丝数，不是量级档位
#wavytalkthermalbrush          来源：被哪个搜索词捞到的
⚡ Views 40× followers          播放 ≥ 粉丝 3 倍时显示，左上角
61s                            右下角
```

**「来源」这一栏是产品差异化的可见证明。** 灰色 = 搜品牌名或品牌标签就能找到，
青色 = 只有靠挖出来的词才找到。实测 50 条里有 **23 条是青色**。

**⚡ 的措辞必须是主谓宾。** `40× followers` 会被读成「粉丝多 40 倍」，
要写 `Views 40× followers`。

---

## 硬门槛（全部实测标定）

| 门槛 | 值 | 依据 |
|---|---|---|
| 时间窗 | 近 30 天 | 内容趋势半衰期以周计，陈旧样本稀释信号 |
| 播放量 | ≥ 10,000 | — |
| 互动率 | ≥ 3% | 行业基准 5% 只剩 27 条；买量视频特征是 0.2-0.7%，3% 足够挡住 |
| 时长 | 10-90 秒 | 超出这个区间的内容形态完全不同 |
| 语言 | 仅 `en` | 放行 `un` 会混入非英文（那批 caption 全是 hashtag + emoji） |
| 格式 | 非图文帖 | 实测图文帖占召回量一半以上 |
| 账号 | 剔除品牌官号 | 按用户名 token 前缀匹配（不需要官号 ID，实测贡献为 0） |
| 相关度 | ≥ 3 分 | hashtag +3 / @提及 +4 / caption +2 / 带货意图词 +2 |

**每作者最多 3 条**，避免单个达人的风格主导结果。
50 条来自 40 个账号，平均 1.25 条，cap 3 意味着单人最高占 6%，依然很紧。

---

## 召回机制（核心差异化）

TikTok 不提供「某品牌全部相关视频」的接口，只能从几个由它按相关性排序、
且有上限的切片里取并集。实测关键词路填充率只有 49-76%，**加数量无用，要加变体**。

```
第一轮   4 路探路（品牌名 / 品牌名+review / #品牌名 / @品牌名）
   ↓
挖词     从 caption 和 hashtag 里挖出品牌的真实词汇表
         #wavytalkthermalbrush 128 次 · #wavytalkhair 163 次
         #wavytalkpartner 20 次（品牌合作专用标签）
         thermal brush / blowout boost / airshape pro / power wave
   ↓
第二轮   13-17 路并行扩量
```

**效果**：只靠品牌名和品牌标签能找到 27/50 条，两段式召回全部 50 条 ——
**多找回约 2 倍**，其中 23 条是任何只搜品牌名的工具都找不到的。

---

## 实测数据

```
召回              4,312 条 → 去重 2,572 条唯一视频
过硬门槛           50 条（每作者≤3）
产出率            1.9%
耗时              约 12 分钟
成本              约 $7（Apify）
```

**对照人工**：搜索页只能看到缩略图和播放量，日期/评论/转发要点进视频。
人工需点开约 920 条，命中率 6%，纯筛选 3-5 小时。

---

## 一期不做

内容结构拆解（hook/body/CTA）· 基线倍数 · Instagram · 登录 · 历史记录 ·
排序切换 · CSV 导出 · 时长和广告标记筛选器 · 搜索词编辑
