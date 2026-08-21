# Spark — 改动清单

基准是你上一版的 `spark-search.html` / `spark-loading.html` / `spark-results.html`。
**在那三个文件上继续改**，输出 final 版。

产品背景、token、交互细节见 `UI-BRIEF.md`。

---

## 搜索页

**1. 主标题**

```
Skip the scroll.
Watch the 3% that hit.
```

两行长度是 15 / 22 字符，比原来更接近，断行和字距重新排。

**2. 副文案**：`digging through hundreds first` → `digging through thousands first`

**3. 按钮**已改为 `Start digging`（原 `Analyze`）。按钮变宽，重排输入框那一组的比例。
点击后文案变 `Starting…`，**宽度不能跳** —— 给 min-width。

**4. 七个门槛标签排成一行**（现在是 4 + 3 两行）。按内容区 1120px 排，约需 640px。
窗口不够时再换行。

**5. 示例卡片改成一张，铺满整行**

```
See a finished report — no wait
┌──────────────────────────────────────────────┐
│ WAVYTALK    hair tools · 47 videos         → │
└──────────────────────────────────────────────┘
```

- 删掉 Glow Recipe 那张
- 标题用单数（原 `Examples — finished reports, no wait`）
- 品牌名全大写
- 这是没有邀请码的访客唯一能看到真实产出的入口，要显眼

**6. 保持不动**：邀请码弹窗、验证状态行（`◐ Searching TikTok for "…"` / ✓ / ⚠）。

---

## 加载页

**7. 第一阶段文案改成**

```
Searching TikTok — "wavytalk" · #wavytalk
```

（原 `Searching "wavytalk" — 418 videos in`）

**8. 挖词阶段两拍，各停 3.5 秒**

```
Learning the brand's own hashtags — found 6 more ways creators tag it
Learning the brand's own hashtags — #wavytalkthermalbrush, #wavytalkhair
```

**9. `.stage` 去掉固定尺寸**

```css
.stage{ height:22px; width:var(--width-prose); }
```

阶段文案可能更长，加省略号兜底或放宽。

**10. 阶段文案里的数字不再用 `<span class="num">` 包裹**，改纯文本。加载页数字会失去
等宽样式，可接受。

**11. 保持不动**：阶段顺序、底部那行 `Go make coffee…`。

---

## 结果页

**12. 用真实封面重做一遍。** 附件 `design-results-REAL-COVERS.html` 是你的设计稿
＋ 47 条真实数据 ＋ 47 张真实封面。上一版是灰色占位块，真封面高饱和、有人脸、
有大字幕，整页密度和噪音完全不同 —— **final 必须在真图上定**。

**13. ⚡ 角标要在真封面上跳得出来。** 47 条里只有 4 条有。很多 TikTok 封面本身是
红色系，洋红实底可能糊掉。

**14. 保持不动**：

- 卡片两行结构（① 播放·互动率·VO ② @账号·粉丝数）
- **不要加第三行来源标注**
- `.m--eng.is-top` 条件青色，前 15% 分位。青色只给互动率，不给播放量
- 顶部 `■ 29 found only by a tag Spark learned` ＋ ⓘ 浮层
- 筛选栏、空状态

---

## 交付

**可直接替换的 CSS**，类名沿用现有结构。

| # | 画面 | 优先级 |
|---|---|---|
| 1 | 结果页 · 47 条 · **真实封面** | P0 |
| 2 | 卡片细节稿（⚡ + 两行 + hover） | P0 |
| 3 | 搜索页（新标题 + 一行标签 + 单张示例卡） | P0 |
| 4 | 邀请码弹窗（默认 / 码错误） | P0 |
| 5 | 加载态 | P0 |
| 6 | ⓘ 浮层展开态 | P1 |
| 7 | 结果页 · 筛选后 / 无结果 | P1 |
| 8 | 搜索页 · 验证中 / ✓ / ⚠ | P1 |
