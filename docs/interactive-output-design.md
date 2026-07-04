# Archscribe 2.0 更新方案 — 模板系统 × 动画引擎 × 可交互输出

> 状态:**已完成落地**(Phase 0–5 全部实现;首批 3 布局上线,`hub` / `timeline` 留作第二批)
> 运行环境:**仅 Codex**(Linux 沙箱,Playwright + Chromium 可用,可联网装依赖)
> 本版新增输入:
> 1. 单一 panorama 模板是硬伤,限制了日常使用范围;
> 2. 现有动画(匀速流点 + 轮播脉冲)单调、缺乏记忆点;
> 3. 交互需求保留(点击节点高亮链路),但从"独立项目"降级为整体架构的一个产物。

---

## 1. 现状诊断:三个短板一个根因

| 短板 | 表现 | 根因 |
|---|---|---|
| 模板唯一 | 只能画"4 输入 + 3 核心卡 + 决策 + 3 面板"一种拓扑,内容必须削足适履 | 坐标全部硬编码在 `render_static`,连线路径硬编码在 `animate_frame` |
| 动画无新意 | 流点匀速跑圈 + 模块轮流脉冲,2 秒循环,没有叙事感 | Pillow 逐帧手画,做不了缓动/描边生长/焦点叙事这类高级效果 |
| 无交互 | GIF 是位图,天然无交互 | 缺一个矢量(SVG)形态的产物 |
| (隐藏)观感退化 | 在 Codex Linux 沙箱里,`font_candidates()` 只有 Windows/macOS 路径,实际落到 Pillow 位图默认字体,**手绘感直接丢失** | 未捆绑字体 |

**根因收敛**:三个短板都指向同一个架构问题——渲染逻辑与图结构耦合、且被 Pillow 的能力上限锁死。

**关键机会**:`icon_browser.py` 已经跑通了「Playwright 加载 HTML → JS 逐帧驱动 → 截图合成 GIF」的完整管线,只是目前只用于渲染小图标。既然运行环境锁定 Codex(Chromium 必然可用),这条管线可以直接升级为**整图主渲染器**。

---

## 2. 目标架构:一份图模型,一个 SVG 主渲染器,五种产物

```
spec (v2 JSON)
   │
   ▼
graph 模型(nodes / edges / groups,布局器计算坐标)
   │
   ├─► SVG 主渲染器(Chromium 内,rough.js 手绘形状 + 手写 webfont)
   │      ├── <basename>.svg          矢量静态图(新增)
   │      ├── <basename>.png          Playwright 截图
   │      ├── <basename>.gif / .mp4   JS 驱动动画逐帧截图合成
   │      └── <basename>.html         同一 SVG + ~80 行交互 JS(新增)
   │
   ├─► Excalidraw 生成器(由 graph 直接生成,沿用现有 Excal builder)
   │      └── <basename>.excalidraw
   │
   └─► Pillow 渲染器(降级兜底,保留现有代码,仅 panorama + flow)
```

设计要点:

- **graph 是唯一数据源**:节点/边/坐标只算一次,SVG、Excalidraw、交互 HTML、动画路径全部消费同一份数据,不存在"两套渲染漂移"。
- **rough.js(MIT,单文件,vendor 进 `assets/vendor/`)画所有形状**:Excalidraw 本身就用 rough.js,这一步之后输出观感才是真正的"Excalidraw 风",超过现在 Pillow 的直线近似。
- **捆绑字体进 `assets/fonts/`**:手写体用 Excalifont(OFL),CJK 用 Noto Sans SC 子集(OFL)。SVG 渲染器以 webfont 方式加载,Pillow 兜底路径也读同一份文件,彻底修掉 Linux 沙箱字体退化。
- **Pillow 不删**:作为 `--renderer pillow` 兜底保留(仅支持 panorama + flow),Chromium 意外不可用时仍能出图。默认 `--renderer browser`。

---

## 3. Track A — 模板系统(布局 preset)

### 3.1 spec v2 结构

```jsonc
{
  "version": 2,
  "layout": "pipeline",          // 布局 preset,见 3.2
  "style": "terminal",           // 沿用现有 4 套配色
  "animation": "draw",           // 动画 preset,见 Track B
  "canvas": { "width": 1210, "fps": 20, "seconds": 3.5 },  // height 由布局器按内容算出
  "title": { "prefix": "...", "highlight": "...", "subtitle": "..." },
  "signature": "@archscribe",
  "content": { /* 各布局专属字段,见 3.2 */ }
}
```

- **v1 兼容**:无 `version` 字段的 spec 自动按 `layout: panorama` + `animation: flow` 解释,现有 spec 零破坏。
- `--layout` / `--animation` CLI 参数覆盖 spec 字段(与 `--style` 同规则)。

### 3.2 布局 preset 清单(首批 5 种)

| preset | 拓扑 | 弹性范围 | 适用内容 |
|---|---|---|---|
| `panorama` | 现有全景模板 | 输入 2–6 个、核心卡 2–4 张、三面板可省略任意个 | 完整系统内幕图(现状的超集) |
| `pipeline` | 横向线性流水线 | 2–6 个阶段,可选决策菱形 + 回环,可选每阶段下挂 1–3 个说明卡 | 流程讲解、CI/CD、数据管道 |
| `layers` | 纵向分层架构 | 2–5 层,每层 1–5 个组件,层间垂直连线 | 技术栈、分层架构、协议栈 |
| `hub` | 中心辐射 | 1 个 hub + 3–8 个 spoke,双向边可选 | Agent 与工具、微服务网关、生态图 |
| `timeline` | 横向时间线 | 3–8 个里程碑,上下交替布卡 | 演进史、路线图、版本对比 |

实现方式:每个 preset 是一个**布局器函数** `layout_<preset>(content) -> graph`,输入内容计数,输出带坐标的 nodes/edges。坐标不再是常量,而是由"卡片尺寸 + 间距 + 均分"规则计算;画布高度随内容自适应。

`panorama` 的弹性化规则(替代现有硬编码):

- 输入条:按数量均分横向排布(2–6 个);
- 核心卡:2–4 张均分,连线随之生成;
- 三个底部面板:任意面板省略时,剩余面板均分宽度;全部省略时画布收短。

### 3.3 SKILL.md 配套:选型决策表

SKILL.md 的 Workflow 增加一步"选布局":内容是流程 → `pipeline`;是系统全景 → `panorama`;是架构分层 → `layers`;是围绕一个中心 → `hub`;是演进 → `timeline`。让 agent 不再把所有题材硬塞进全景模板。

---

## 4. Track B — 动画引擎 2.0(动画 preset)

动画在 Chromium 内用 JS 驱动(`window.setProgress(t)` 模式,复用 `icon_browser.py` 的成熟做法),逐帧截图合成。**所有 preset 全部 seek 式确定性渲染**(帧 = f(t)),保证可复现、可测试。

### 4.1 preset 清单(首批 3 种 + 1 个氛围层)

**`draw` — 手绘生长(主打,最出片)**

模拟"有人正在白板上画这张图":

- 按拓扑顺序(标题 → 输入 → 核心 → 决策 → 面板)逐元素出现;
- 形状用 rough.js 路径 + `stroke-dashoffset` 做真实描边生长,文字淡入,图标最后"点"上去;
- 画完整图后定格约 1 秒,再快速淡出重来;
- 循环时长 3–4 秒(约 70–80 帧 @20fps)。

**`relay` — 接力点亮(叙事感)**

信号在系统中传递的故事:

- 任意时刻只有**一个焦点节点**:高亮描边 + 轻微放大(缓动),其余节点压暗到 ~55%;
- 焦点沿数据流顺序移动,节点间由一束能量光沿边流过(带缓动的加速-减速,不是匀速);
- 光到达下一节点时一个短促的涟漪扩散;
- 一轮走完全部主链路,循环 4–5 秒。

**`flow` — 流动升级版(兼容现状,默认值)**

保留现有流点语言,修掉"low"的部分:

- 匀速 → `ease-in-out` 变速,彗星尾随速度拉伸;
- 到达节点端点时加涟漪 + 2–3 个粒子迸溅;
- 模块脉冲从"轮播闪烁"改为沿数据流顺序的**波次呼吸**;
- 边的高亮改为渐变描边流动(`stroke-dasharray` 渐变),不再只是叠加圆点。

**氛围层(所有 preset 共享,跟随 style)**

- `default`:标题高亮胶囊低频呼吸 + 签名手写微抖;
- `terminal`:细扫描线缓慢下移 + 字符微闪;
- `blueprint`:背景网格波纹一次/循环;
- `candy`:入场用 spring/bounce 缓动,粒子改为圆点糖果色。

### 4.2 输出格式升级:GIF 之外增加 MP4

`draw` / `relay` 循环变长后 GIF 体积会涨(帧数 41 → 70–100)。对策:

- GIF:全局调色板 + 帧间差分(Pillow `optimize` + 可选 `gifsicle -O3`),目标 < 8 MB;
- **新增 `<basename>.mp4`**(ffmpeg h264, yuv420p):体积约为 GIF 的 1/5、无 256 色限制,X / 微信公众号原生支持,日常发布首选;
- 产物开关:`--formats gif,mp4,html,png,svg,excalidraw`(默认 `gif,png,excalidraw` 与现状一致)。

---

## 5. Track C — 可交互 HTML(继承第一版方案,大幅简化)

第一版方案里"PNG 覆盖层(Phase 1)vs 原生 SVG(Phase 2)"的两期路线**不再需要**:主渲染器本身就产出带 `data-node` / `data-edge` 的 SVG,交互件是它的自然副产品。

### 5.1 产物形态

`<basename>.html` = 内嵌同一份 SVG + 内嵌 graph JSON + 约 80 行原生 JS,**单文件、双击即开、离线可用**;可直接丢 GitHub Pages 当"点此体验"链接。

### 5.2 交互行为规格(沿用第一版 §8,已验证过的设计)

- **点击节点**:该节点描边加亮,相邻边高亮并开始流动,相邻节点保持正常,其余整体压暗;
- **再次点击 / 点空白**:复位全亮;
- **hover(桌面)**:轻微提亮 + tooltip(节点全名);
- **键盘**:`Tab` 移动 / `Enter` 选中 / `Esc` 复位;
- **移动端**:点击即选中,保证热区尺寸;
- **动画策略**:未选中时整图静止,选中后仅相邻边流动(清晰 + 有反馈);
- 高亮配色跟随当前 style 的 THEME。

默认一跳高亮;"整条链路 BFS 高亮"作为 HTML 里的一个 toggle,不另做版本。

---

## 6. 分期计划

| Phase | 内容 | 用户可感收益 | 依赖 |
|---|---|---|---|
| **0. 地基 ✅ 已完成** | ① 捆绑 Excalifont + Noto Sans SC 子集(`assets/fonts/`,`scripts/prepare_fonts.py` 再生),字体加载链改为捆绑优先 + 生僻字系统回退;② `scripts/graph_model.py` graph 模型(panorama 节点/边/组,`tests/test_graph_model.py` 断言与渲染器坐标一致);③ rough.js 4.6.6 vendor 到 `assets/vendor/` | 现有图在 Codex 里立刻恢复手写观感 | 无 |
| **1. SVG 主渲染器 ✅ 已完成** | 实现方式微调:不重放 graph 而是重放 `render_static` 的 primitive-op 流(`render_static_with_ops` 录制,`scripts/svg_renderer.py` 在 Chromium 里用 rough.js 重放),布局零重复、四风格通用;产出 `.svg`(内嵌字体)+ `.png`;`--renderer` 落地,Pillow 保留为兜底 | 静态观感升级为真·Excalidraw 风 | Phase 0 |
| **2. 动画引擎 ✅ 已完成** | `flow` 升级版(缓动光束+白色轨道头+到站涟漪+波次呼吸)、`draw`(白板生长,≥72帧)、`relay`(压暗+接力光束+已访问链路留亮,≥88帧)、按风格氛围层;GIF 全局调色板量化(17MB→约1.1MB)+ MP4 输出(约176KB);`--animation` / `--formats` 落地;`--check` 扩展 mp4/svg 契约 | 动画从"流点跑圈"变成有叙事感的成片 | Phase 1 |
| **3. 模板系统 ✅ 已完成** | 实现方式微调:布局器统一为 `graph_model.build_plan(spec)`,产出含几何/动画路径/图拓扑的 plan,Pillow 与浏览器渲染器共同消费;`panorama` 弹性化(输入 2–6、核心卡 2–4、面板可省;默认 spec 与旧版像素一致)+ `pipeline`(2–6 阶段、可选判定/回路/备注)+ `layers`(2–5 层 × 0–5 项);`hub` / `timeline` 留作第二批;`validate_spec` 前置校验(字段级 path/message/fix,`--validate-only`);SKILL.md 加选型决策表 | 覆盖题材扩大一个量级 | Phase 1(与 Phase 2 可并行/换序) |
| **4. 交互 HTML ✅ 已完成** | `--formats html` 落地(`svg_renderer.py` 内嵌 graph JSON + 原生 JS);点击高亮邻接、BFS 整链 toggle、hover tooltip、Tab/Enter/Esc 键盘、点空白复位;`--check` 校验热区数与 graph 一致 | 读者可点击探索 | Phase 1 |
| **5. 收尾 ✅ 已完成** | `--check` 扩展(见 §7,含 html 热区);`tests/test_graph_model.py` 全量重写(legacy golden 坐标 + 三布局弹性)+ `tests/test_ops_and_browser.py` 扩展(graph 块、交互 HTML 真浏览器点击、pipeline/layers ops、validate_spec);README(中文默认) / README.en / SKILL.md / spec-format.md 全量更新;三布局 × 三动画抽样渲染 + 预览图更新 | 质量护栏 + 传播素材 | 全部 |

> 换序建议:若"模板不够用"比"动画不够炫"更急,Phase 3 可提到 Phase 2 之前,两者只共同依赖 Phase 1。

---

## 7. 校验扩展(--check)

在现有契约(尺寸/帧数/motion/Excalidraw ID/字体族)基础上新增:

- `fonts_bundled`:webfont 文件存在且被 SVG 引用;
- `layout_bounds`:节点数量在所选 preset 的弹性范围内,任意两节点不重叠;
- `animation_nonstatic`:逐 preset 的帧差校验(draw 校验"末帧元素数 > 首帧",relay 校验焦点移动);
- `mp4_valid`:时长/分辨率/像素格式(ffprobe);
- `html_interactive`:节点数 == graph 节点数,每个 `data-node` id 唯一,JS 无语法错误(Chromium 加载无 console error);
- `spec_valid`:渲染前 schema 校验(未知 icon key、未知 layout/animation、文案超长,给出**具体到字段**的错误),agent 可据此自动改 spec。

---

## 8. 风险与取舍

| 风险 | 影响 | 缓解 |
|---|---|---|
| 逐帧截图渲染变慢(70–100 帧 × Playwright screenshot) | 单图渲染 1–3 分钟 | 帧并行截图(同页面多 viewport 或降 scale);Codex 场景对分钟级耗时可接受;`--formats png` 快速预览先行 |
| rough.js 随机抖动破坏确定性 | 帧间形状漂移、快照测试不稳 | rough.js 支持 `seed` 参数,固定 seed;动画中形状只画一次,仅动效层逐帧变化 |
| 字体子集化 CJK 覆盖不全 | 生僻字缺字 | Noto Sans SC 子集保留常用 6763 字 + 渲染前检测缺字并回退全量字体 |
| 新布局器的视觉质量不如手工排版 | 图变"generic" | 每个 preset 保留艺术指导常量(间距/比例/留白),布局器只解决"数量弹性",不做通用自动布局 |
| GIF 体积超标 | 发布受限 | MP4 为主推产物;GIF 提供 `--gif-budget` 自动降帧率/降色板 |
| Chromium 意外不可用 | 无法出图 | Pillow 兜底渲染器保留(panorama + flow) |

---

## 9. 已确认决策(2026-07-04)

- **A. Phase 顺序**:✅ 动画优先(Phase 2 动画引擎在前,Phase 3 模板系统在后)。
- **B. 默认动画 preset**:✅ 升级版 `flow`;SKILL.md 写明引导规则——讲解/教学类内容主动选 `draw` 或 `relay`。
- **C. MP4**:✅ 进默认产物,默认 `--formats gif,mp4,png,excalidraw`。
- **D. 手写字体**:✅ Excalifont(OFL)+ Noto Sans SC 子集补 CJK;Phase 0 出 CJK 混排样张验证。
- **E. 首批布局**:✅ 3 种——`panorama` 弹性化 + `pipeline` + `layers`;`hub` / `timeline` 放第二批。

---

## 附录 A:graph schema(沿用第一版设计,字段微调)

```jsonc
{
  "canvas": { "width": 1210, "height": 1138 },
  "nodes": [
    { "id": "in.codex",       "kind": "input",    "x": 423, "y": 174, "w": 78,  "h": 80,  "label": "Codex", "icon": "terminal", "group": "inputs" },
    { "id": "core.scan",      "kind": "card",     "x": 95,  "y": 366, "w": 260, "h": 90,  "label": "Scan",  "group": "core" },
    { "id": "decision.ready", "kind": "decision", "x": 706, "y": 508, "w": 120, "h": 120, "label": "Ready?" }
  ],
  "edges": [
    { "id": "e.scan_import", "from": "core.scan", "to": "core.import",
      "points": [[355,411],[472,411]], "label": null, "style": "solid" }
  ]
}
```

- `kind`:`input | card | decision | output | panel | panel-card`,决定形状与高亮配色;
- `group`:支持"高亮整组"与面板整体动画;
- `points`:panorama 首版直接迁移现有 `animate_frame` 的 11 条路径(见附录 B),其余布局由布局器生成。

## 附录 B:panorama 布局的节点与边清单(从现有硬编码迁移)

节点:

- 输入条:`in.codex` `in.claude` `in.project` `in.notes`
- 核心管线:`core.scan` `core.import` `core.index`
- 决策 / 输出:`decision.ready` / `out.report`
- 左面板:`src.codex` `src.claude` `src.project`
- 中面板:`layer.sources` `layer.records` `layer.versions` `layer.manifest`
- 右面板:`pack.bootstrap` `pack.cases` `pack.userskills`

边(几何来自 `animate_frame` 现有 `paths`):

| 边 | from → to | 几何 | 标签 |
|---|---|---|---|
| 输入→核心 | inputs → core.scan | (605,239)-(605,316) | — |
| scan→import | core.scan → core.import | (355,411)-(472,411) | — |
| import→index | core.import → core.index | (732,411)-(850,411) | — |
| index→决策 | core.index → decision.ready | (982,456)…(768,508) | — |
| 决策→报告 | decision.ready → out.report | (826,568)-(1022,568) | Yes |
| 决策→scan 回环 | decision.ready → core.scan | (707,568)…(222,456) | No |
| 核心↔左面板 | core ↔ 左面板 | (156,637)-(156,736) / 反向 | Read / Context |
| 层链 | layer.sources→…→manifest | (458,890)…(766,890) | — |
| 中→右面板 | layer.manifest → pack | (855,890)-(904,890) | Compile |
| 右面板→决策 | pack → decision.ready | (1036,735)…(766,628) | Reusable |
