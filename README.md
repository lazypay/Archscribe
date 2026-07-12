# Archscribe

Archscribe 是一套面向 Codex 的手绘动态架构图 Skill 与本地渲染器。它可以把系统说明、流程、文章或参考图转成 PNG、GIF、MP4、SVG、可编辑 Excalidraw 和交互 HTML。

## 能力

- 7 种布局：`panorama`、`pipeline`、`layers`、`hub`、`swimlane`、`sequence`、`graph`(自由节点/边 + 自动 DAG 布局 + 专属回路通道)
- 7 套风格：`default`、`blueprint`、`terminal`、`candy`、`chalkboard`、`editorial`、`cyber-grid`
- 6 种动画：`flow`、`draw`、`relay`、`trace`、`chapter`、`failure-recovery`
- Browser 与 Pillow 双渲染器
- 严格 Spec 校验、精确格式输出、自动输出契约检查
- 本地字体、图标与 rough.js；Chromium 和 ffmpeg 是可选运行依赖
- `outline / illustrated / hero` 三级图标，以及脑部脉冲、齿轮旋转、眼睛扫描、记忆写入等确定性微动画

## 快速开始

```powershell
python scripts/render_animated_diagram.py --spec assets/default-spec.json --outdir outputs --basename diagram --formats png --check
```

完整发布：

```powershell
python scripts/render_animated_diagram.py --spec assets/default-spec.json --outdir outputs --basename diagram --formats gif,mp4,png,excalidraw,svg,html --verify --check
```

新布局样例位于 `assets/examples/`。完整字段参考见 `references/spec-format.md`。

具象插画示例：`assets/examples/illustrated-loop-spec.json`。

## 开发验证

```powershell
python -m pytest -q
```

每次发布前还应渲染七种布局的 PNG，并检查重叠、连线穿越、文字可读性和移动端缩略效果。
