# Spark — UI 设计需求书

发给 Claude Design。三个页面：搜索页、加载页、结果页。

> ## ⚠️ 先读这一段
>
> **这不是从零设计，是给一个已经跑起来的产品做视觉精修。**
>
> 三个页面都已经用真实数据跑通了（真实的 TikTok 数据、真实的封面、能点的筛选器）。
> 现在的问题是**它看起来像草稿**：布局对、信息对，但缺少设计师的手艺 —— 间距节奏、
> 层次对比、字重搭配、留白、微交互。
>
> 所以：
> - **信息架构和文案不要改**，那些是反复推敲过的产品决策
> - **视觉上请大胆重做** —— 排版、比例、密度、卡片质感、hover 反馈都可以推翻重来
> - 交付**可直接替换的 CSS**，类名沿用下面给的结构
>
> 下面所有数字都是真实跑出来的（1,702 条爬取 → 47 条过关），不是占位符。

---

## 0. 产品是什么

输入一个品牌名，10 分钟后拿到该品牌近 30 天内**过硬门槛的达人视频**
（最多 50 条），带封面、数据和来源标注，可按维度筛选。

**解决的痛点**：TikTok 搜索没有日期、播放量、格式的筛选器，研究竞品爆款要先人工
翻几百条视频。

**用途**：作者自用 + 作为作品集给面试官看。所以空状态、加载态、报错态都要有设计，
不能露出浏览器默认样式。

---

## 1. 视觉系统（已定，不要改）

浅色、TikTok 青洋红点缀、背景晕染。以下 token 直接沿用：

```css
--color-cyan:#00CFC8;      --color-cyan-wash:#E6FBFA;
--color-magenta:#FE2C55;   --color-magenta-hover:#E62149;
--color-bg:#FFFFFF;        --color-surface-sunken:#F6F6F7;
--color-border:rgba(10,10,11,.10);
--color-border-strong:rgba(10,10,11,.22);
--color-text:#0E0E10;      --color-text-secondary:#5C5C64;
--color-text-muted:#6B6B75;
--color-data:#0B7F7B;      /* 数值专用深青，青色在白底上太浅 */

--font-display:"Satoshi";  /* 大标题 900 */
--font-body:"Inter";
--font-mono:"Geist Mono";  /* 所有数字，必须配 tabular-nums */
```

**三条硬规则**

1. **晕染只在背景层。** 首页 hero 后方两团 radial-gradient（青一团洋红一团），
   `blur(130px)`、`opacity .2-.3`。数据区域完全平面。
2. **洋红不用于小字。** 只用于 ≥24px 大字、CTA 按钮实底、徽章。数值一律用
   `--color-data`。
3. **所有数字用等宽 + `font-variant-numeric: tabular-nums`。** 这是这个产品
   专业感最廉价的来源。

**PC 优先，最小 1280px。** 手机不做专门布局，靠 `grid auto-fill` 自然降级即可。

---

## 2. 搜索页

```
                        SPARK

                  Skip 900 videos.
                  Watch 50.

       TikTok's search filters suck — no date, no reach, no format.
       So researching a competitor's viral videos means digging
       through hundreds first. Spark does the digging so you can just watch.

       [Last 30 days] [10k+ views] [3%+ engagement] [10–90 sec]
              [English] [Video only] [Creators only]

            ┌──────────────────────┐  ┌───────────────┐
            │ wavytalk             │  │ Start digging │
            └──────────────────────┘  └───────────────┘
              ✓ Looks good — plenty to work with

              See a finished report — no wait
            ┌──────────────────────────────────────────┐
            │ WAVYTALK    hair tools · 47 videos     → │
            └──────────────────────────────────────────┘
```

### 示例入口只有一张，铺满整行

之前的稿子画了两张并排（WAVYTALK + Glow Recipe）。**改成一张。**

原因：我们实测跑了五个品牌（momcozy、dr dent、nailphoria、mellow sleep、nello），
只有 WavyTalk 一个的产出**同时满足数量和内容相关性**。其余要么条数太少
（nello 5 条、dr dent 2 条、mellow sleep 0 条），要么内容对不上口
（momcozy 29 条里近一半是挂了品牌标签的母婴情感视频）。

与其并排放一张 47 条和一张 5 条，不如只放最好的那张。**一张铺满整行**，
不要留一半空白，也不要用 "Examples" 这种复数措辞 —— 一张卡片配复数标题
会让人以为还有别的没加载出来。

这个入口是没有邀请码的访客唯一能看到真实产出的地方，所以它要显眼，
不能做成脚注。

### 规格

- 居中，内容最大宽 1120px，正文最大宽 560px
- H1 用 Satoshi 900，52px，字距 -.025em，两行
- 输入框 + 按钮**整组 480px**，不要撑满；按钮按内容宽，输入框吃掉剩下的
- 按钮洋红实底

### 按钮为什么叫 Start digging

不叫 `Search`：搜索框全世界都是敲完回车立刻出结果，而这个要跑十分钟。
按钮上的动词是用户对等待时长的第一个锚点，定成 Search 后面就救不回来了。
何况 H1 下面第一句就在否定 TikTok 的搜索，自己再叫 Search 会把自己归进
刚刚否定的那类东西。

不叫 `Analyze`：产品实际做的是筛选和归集，不是分析。用户点 Analyze 期待
拿到结论，实际拿到 47 张卡片，中间有落差。

`Start digging` 和副文案里的 "Spark does the **digging**" 闭环，
`Start` 又天然暗示这是一个过程而不是一次查询。

### 七个门槛标签

**这是陈述不是控件，不可点击。** 说明「我们已经替你筛了这些」。

- 两行居中排列（4 + 3），宽度对齐正文
- `background: --color-surface-sunken`，`border-radius: 999px`
- 12px，`--color-text-secondary`
- 数字部分（`10k+` `3%+` `10–90`）用等宽字体
- 和副标题间距 24px，和输入框间距 32px

**结果页的筛选器用同一套 pill 样式** —— 首页的 pill 是「已经筛好的」，
结果页的 pill 是「你还能再筛」。视觉语言一致，用户自然理解两者关系。

### 输入框下方的一行状态

用户输完品牌名失焦后，后台探 20 条视频（约 30 秒），返回一行状态。

**验证中要有文字，不能只有转圈。** 30 秒的空转会让人以为卡死了。
但**只有一个真实步骤**（拿品牌名搜一次，看回来几条），所以只写一行，
不要编成多阶段：

```
验证中   ◐ Searching TikTok for "wavytalk"
通过     ✓ Looks good — plenty to work with
太少     ⚠ Only 3 videos came back. Check the spelling?
```

验证中那行的品牌名取用户刚输入的值，加引号。

**结果只有一行，因为这是用户唯一判断得了的事。**

不要展示「我们会搜哪些关键词和标签」—— 那是实现细节。用户看到
`#wavytalk` 也无从判断对错，摆出来只会让他困惑或盲目点确认。
真正的搜索词列表放在**结果页**展示，那时我们已经挖出十几个，才算信息。

这一行的作用是在花掉 10 分钟之前拦住拼写错误和冷门品牌。

### 要画的状态

1. 默认（空输入框）
2. 检查中（输入框右侧小 spinner + `◐ Searching TikTok for "…"`）
3. ✓ 通过（青色勾）
4. ⚠ 素材太少（洋红警告）

---

## 2.5 邀请码弹窗（新增，本次重点）

### 为什么有这个东西

真正跑一次要抓 **1,700 条视频、17 次搜索**，是真金白银。所以：

- **前面的验证（20 条）对所有人免费**，不设任何门槛
- **真正的分析要邀请码**

这条边界是刻意的：访客能完整体验输入、验证、拿到真实反馈，只在最后一步遇到门。
**这是一个好演示，不是被封。**

文案上必须是 **beta / invite-only**，不能是「额度用完」「服务繁忙」。
同一堵墙，前者读起来是筛选，后者读起来是窘迫。

### 触发时机

用户点 **Start digging** → 弹窗**立刻出现**，不等任何网络请求。

（验证是在这之前、失焦时就跑完的。用户点 Start digging 时应该已经看到 ✓ 或 ⚠ 了。）

### 结构与文案

```
        ┌──────────────────────────────────────────────┐
        │                                              │
        │   Live runs are invite-only during beta      │
        │                                              │
        │   Each run crawls ~1,700 videos across        │
        │   17 searches, so access is limited for now.  │
        │                                              │
        │   ┌────────────────────────┐  ┌───────────┐  │
        │   │ invite code            │  │    Run    │  │
        │   └────────────────────────┘  └───────────┘  │
        │                                              │
        │   No code? See a finished report →           │
        │                                              │
        └──────────────────────────────────────────────┘
```

`~1,700 videos` 和 `17 searches` **都是真实数字**，不要改成约数或删掉。
用真数据解释限制的理由，比「beta」两个字有说服力得多 —— 它告诉访客这个限制
是有成本依据的，不是装样子。

`No code? See a finished report →` 是这个弹窗最重要的一行。**没有码的人必须
有出口**，否则整个站点对他就是死的。它链到已有的 demo 报告。

### 规格

沿用第 1 节已有的 token，只需要新增一个宽度：

| 项 | 值 |
|---|---|
| 弹窗宽度 | `--width-modal:420px`（新增） |
| 内边距 | `--space-6` 32px |
| 圆角 | `--radius-lg` 14px |
| 阴影 | `--shadow-popover` |
| 遮罩 | `--color-scrim` `rgba(10,10,11,.62)` |
| 标题 | `--text-lg` 18px / `--weight-medium` |
| 说明文字 | `--text-xs` 13px / `--color-text-secondary` |
| 输入框 | 沿用 `.search__input` 规格，高 `--height-control` 48px |
| Run 按钮 | 沿用 `.search__submit`（洋红实底） |
| 底部链接 | `--text-xs` / `--color-cyan-dim` |

**遮罩下面的首页要不要模糊？** 不要。我们在第 5 节明确说了不用毛玻璃。
遮罩本身的暗度已经够把焦点推到弹窗上。

弹窗入场动效沿用 `.pop` 那套：`opacity 0→1` + `translateY(-4px)→0`，
`--duration-fast` 120ms。遮罩同时淡入。**不要缩放弹跳。**

### 要画的状态

1. **默认** —— 输入框空，Run 按钮 disabled（`opacity:.45`，沿用 `.go:disabled`）
2. **输入了码** —— Run 变实心可点
3. **校验中** —— Run 按钮内换成 spinner，按钮宽度不变（**别让按钮宽度跳**）
4. **码错误** —— 输入框边框转洋红，下方一行 13px 洋红小字：

   ```
   That code isn't right.
   ```

   不要写 "try again"、不要写 "invalid"、不要抖动输入框。中性、安静。
5. **遮罩 + 首页背景** —— 完整构图，看遮罩浓度够不够

### 交互细节

- 打开时焦点**自动进输入框**
- **Enter 提交**，等同点 Run
- **Esc 关闭**，**点遮罩关闭**
- 关闭后回到首页，输入框里的品牌名**要保留**
- 错误提示挂 `aria-live="polite"`
- 弹窗 `role="dialog"` + `aria-modal="true"`，焦点锁在弹窗内

### 一个会影响你画稿的行为

**码正确之后种 cookie，同一浏览器后续再点 Start digging 不再弹窗**，直接开跑。

也就是说这个弹窗对同一个人**一辈子只出现一次**。所以：不要为它设计
「记住我」复选框（多余），也不要担心它烦人（它不会重复出现）。

---

## 3. 结果页

```
  SPARK                                            47 videos
  ──────────────────────────────────────────────────────────

  WAVYTALK

  Crawled 1,702 videos · 47 cleared every bar · max 3 per creator

  [Last 30 days] [10k+ views] [3%+ engagement] [10–90 sec]
  [English] [Video only] [Creators only]

  ──────────────────────────────────────────────────────────
  FOLLOWERS  All 47  <100k 12  100k–1M 16  1M+ 19
  VOICEOVER  All 47  Has VO 24  No VO 23                    ⓘ
  ──────────────────────────────────────────────────────────

  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │⚡Views 40×    │ │             │ │             │ │             │
  │  followers   │ │             │ │             │ │             │
  │   [封面]      │ │   [封面]     │ │   [封面]     │ │   [封面]     │
  │              │ │             │ │             │ │             │
  │         61s  │ │        21s  │ │        13s  │ │        51s  │
  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
  1.2M views ·     1.6M views ·    1.7M views ·    1.0M views ·
  4.5% eng · Has VO 9.6% eng·No VO 5.7% eng·No VO 8.4% eng·Has VO
  @rissas.hair ·   @marianamoragui1 @abigaillinnn · @themotherbird
  29.7k followers  · 194k followers 1.2M followers · 1.5M
  #wavytalkthermal  "wavytalk"      #wavytalkairshape #wavytalkhair
  brush
```

**三个信息层级，不要再混：**

```
① 视频表现    播放 · 互动率 · 有无口播      ← 都是这条视频的属性
② 达人        @账号 · 粉丝数                ← 都是这个人的属性
③ 来源        被哪个搜索词捞到的
```

原来 `Has VO` 和 `followers` 放在同一行是错的 —— 一个是视频属性，一个是达人属性。

### 卡片规格

- 封面 **9:16 竖版**，`aspect-ratio: 9/16`，`object-fit: cover`
- 网格 `repeat(auto-fill, minmax(212px, 1fr))`，间距 20px
- 整张卡片可点击，新标签页打开 TikTok 原视频
- hover 需要明确反馈，现在只有边框变色，**太弱了，请重做**

**三行文字的类名**（CSS 请沿用这些）

```html
<div class="perf">1.2M views · 4.5% engagement · Has VO</div>
<div class="who">@rissas.hair · 29.7k followers</div>
<div class="src mined">#wavytalkthermalbrush</div>
```

- `.perf` 数值用等宽 + `tabular-nums`，互动率用 `--color-data`
- `.who` 次色，超长省略
- `.src` 弱色；带 `.mined` 时用 `--color-data`（含义见下）

**封面上的两个角标**

- 左上 `⚡ Views 40× followers` —— 播放量达到粉丝数 3 倍以上才显示。洋红实底、白字、
  等宽。47 条里只有 4 条会有，**是稀缺标记，要显眼**
- 右下 `61s` —— 半透明黑底白字

### 来源颜色 + ⓘ 说明（重要）

第三行的颜色是有含义的：

- 灰色 = 搜品牌名或品牌标签就能找到
- **青色 = 只有通过 Spark 学到的标签或产品名才找到的**

47 条里有 **29 条是青色** —— 这是产品差异化唯一可见的地方，别弱化它。

**但不要用大段文字解释。** 原来那两行（`Found via: ...` 和 `47 shown · green
source = ...`）已删除，收敛成筛选栏右端的一个 **ⓘ 图标**，点击展开一个小浮层：

```
┌────────────────────────────────────────────┐
│  How Spark found these                     │
│                                            │
│  Searched 8 terms:                         │
│  "wavytalk" · #wavytalk ·                  │
│  #wavytalkthermalbrush · #wavytalkhair ·   │
│  #wavytalkairshape · #wavytalksteam ·      │
│  #wavytalkpowerwave · #wavytalkairstyler   │
│                                            │
│  ■ 29 of 47 were found only through a tag  │
│    or product name Spark learned — not by  │
│    searching the brand.                    │
└────────────────────────────────────────────┘
```

浮层里那个 ■ 用 `--color-data`，和卡片上的青色来源对应起来。
点击外部或 Esc 关闭。

**品牌名下面的 `last 30 days` 已删除** —— 筛选标签里已经有 `Last 30 days`，重复了。

### 筛选器

两组：Followers（4 个）、Voiceover（3 个）。用首页那套 pill 样式，
选中态 `background: --color-cyan-wash`、`border-color: --color-cyan`、
文字 `--color-data`。

每个 pill 后面跟一个数量（`<100k 12`），用等宽、透明度 .65。

点击即时过滤，**不刷新页面**，两组可叠加。过滤后更新右上角的「N videos」计数
（原来结果区上方那行「N shown」已删除，计数并到了顶栏）。

ⓘ 图标放在筛选栏最右端，和两组 pill 同一行、垂直居中。

### 要画的状态

1. 完整结果页（47 条）
2. 筛选后（比如只剩 12 条）
3. **筛选后无结果**（两组条件叠加导致空）
4. **ⓘ 浮层展开态**
5. 加载中 —— 见下

---

## 4. 加载态

整个流程要 **10-12 分钟**（召回、去重、过滤、抽帧都在这段时间里）。这不是性能
问题，是数据量决定的，优化不掉。

**不要转圈动画。** 用进度条 + 一行当前阶段文字：

```
                    Reading TikTok

        ████████████████░░░░░░░░░░░░░░░░  42%

              Crawling #wavytalkthermalbrush — 8 of 17
```

- 进度条细（3-4px），480px 宽与输入框对齐，填充用青→洋红横向渐变
- 百分比等宽 32px
- 阶段文字 14px 次色，**切换时 150ms 交叉淡入淡出**，不要生硬跳变
- 背景晕染光团在这一屏缓慢流动（周期 20s+，不要脉冲闪烁）
- 底部一行：`This takes about 10 minutes. You can close this tab.`

10 分钟的进度条一定不均匀（光召回就占一半），条子卡住不动时下面那行字是唯一
让人不焦虑的东西。

---

## 5. 明确不要做的

- 不要用 TikTok 的 logo、音符图标或 wordmark。**只借色系** —— 这是第三方工具，
  不能暗示官方关联
- 不要毛玻璃、噪点、3D、霓虹发光
- 不要 emoji（⚡ 那个角标除外，它是功能标记）
- 不要排序切换、不要 CSV 导出按钮、不要登录入口 —— 一期都不做
- 不要给卡片加播放按钮（我们不做站内播放，点击直接跳 TikTok）

---

## 6. 交付清单

| # | 画面 | 优先级 |
|---|---|---|
| 0 | 搜索页 · 单张示例卡片（铺满整行） | **P0** |
| 1 | **邀请码弹窗 · 默认态**（含遮罩与背景） | **P0** |
| 2 | **邀请码弹窗 · 码错误** | **P0** |
| 3 | 结果页 · 完整 47 条 | **P0** |
| 4 | 卡片组件细节稿（⚡ 角标 + 三行文字 + hover 态） | **P0** |
| 5 | 搜索页 · 默认态 | P0 |
| 6 | 加载态 | P0 |
| 7 | ⓘ 浮层展开态 | P0 |
| 8 | 邀请码弹窗 · 校验中 | P1 |
| 9 | 搜索页 · 状态行（验证中 / ✓ / ⚠ 三种） | P1 |
| 10 | 结果页 · 筛选后 | P1 |
| 11 | 筛选后无结果 | P1 |

**交付形式：可直接替换的 CSS**，类名沿用上面给出的（`.card` `.thumb` `.perf`
`.who` `.src` `.src.mined` `.badge` `.dur` `.f` `.f.on` `.ibtn` `.pop`）。
同时给出：色板 token、字号阶梯、间距阶梯、pill 和输入框的全部状态。

---

## 7. 现在最需要解决的：它看起来像草稿

当前实现的信息架构是对的，但**视觉完成度不够 —— 像一个能跑的原型，不像一个产品**。
最欢迎大改的地方，按重要性排：

1. **卡片。** 47 张卡片是这个产品 90% 的界面。现在只是「图 + 三行文字」堆着，
   缺层次、缺呼吸、hover 反馈几乎看不见。封面圆角、卡片留白、三行之间的间距和
   字重对比、hover 时到底发生什么 —— 全部可以推翻重做。
2. **密度与节奏。** 顶部（标题 → yield 行 → 7 个门槛标签 → 筛选栏）四段东西挤在
   一起，没有主次。谁该大、谁该退到背景里，请重新分配。
3. **⚡ 角标。** 47 条里只有 4 条有，是稀缺信号，但现在混在封面上不够跳。
4. **门槛标签那 7 个 pill。** 它们是「我们替你过滤掉了什么」的证据，但现在长得
   和筛选器 pill 一样，容易被误当成可点击。需要视觉上区分开：一个是**声明**，
   一个是**控件**。

## 8. 一句话总结设计张力

**首页和加载页可以放开用青洋红晕染，营造「在挖数据」的氛围；结果页要克制到接近
黑白** —— 那是一个要扫 47 张封面的工作界面，颜色只留给三个地方：
`⚡` 角标的洋红、数值的深青、以及那 29 条「挖词才找到」的来源标注。
