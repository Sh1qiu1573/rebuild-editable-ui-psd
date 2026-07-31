# rebuild-editable-ui-psd
将扁平化的 App、网页或游戏 UI 截图，重建为具有语义图层、可编辑文字、可编辑形状和独立透明素材的 Photoshop PSD。

本项目是面向 **Codex Desktop + Windows + Adobe Photoshop** 的 Codex skill。它会调用 Codex 的 `$imagegen` skill 重建完整场景和残缺组件，使用 GPU 优先、CPU 自动回退的 `rembg` 进行抠图，并通过 Photoshop 自动装配最终 PSD。

> 这是一套根据可见像素进行的受控重建流程，不是对原始设计源文件或原始 PSD 的恢复。

## 主要功能

- 自动响应“把图片拆解为 PSD”“截图转分层 PSD”“图片转可编辑 PSD”等常用表达。
- 默认调用 Codex `$imagegen` 的内置模式，不需要 `OPENAI_API_KEY`。
- 将普通 UI 文案重建为可编辑 Photoshop 文字图层，只要求视觉风格大致相似。
- 将艺术字、装饰性标题和 Logo 式文字作为独立图案或栅格素材处理。
- 将按钮、面板、进度条和常规几何元素尽可能重建为可编辑形状。
- 使用固定版本 `rembg 2.0.77` 抠图，NVIDIA GPU 优先，失败时自动切换到独立 CPU 环境。
- 对被遮挡、残缺或损坏的图案进行完整组件重绘，不拼接原图碎片和生成像素。
- 设置两次强制人工审核：对象分类与蒙版审核、最终组合效果审核。
- 通过 Photoshop Bridge 自动创建分组、文字、形状、智能对象和最终 PSD。
- 将每个非参考图层及图层组导出为保持原画布坐标的透明 PNG。

## 适用场景

- 游戏 UI 截图拆层
- App 或网页截图转可编辑 PSD
- 运营活动页面和弹窗界面重建
- 扁平设计稿的语义化图层整理
- 从参考截图制作可继续编辑的美术资源包

不适合以下场景：

- 要求恢复原始设计文件中的隐藏内容、原始字体或原始矢量路径
- 要求所有像素与截图完全一致，同时又要求重新生成被 UI 遮挡的完整场景
- 没有 Windows Photoshop，但要求直接交付原生 PSD

## 系统要求

- Codex Desktop
- Windows 10 或 Windows 11
- Adobe Photoshop，可通过 `Photoshop.Application` 调用
- Python 3.11、3.12 或 3.13
- 首次安装和模型下载时可访问网络
- NVIDIA GPU 为可选项；无 NVIDIA GPU 时自动使用 CPU
- NVIDIA 环境建议至少预留 8 GB 磁盘空间，用于隔离的 CUDA、cuDNN、ONNX Runtime 和模型文件

## 安装

从 GitHub Releases 下载最新的 Windows ZIP 发行包，完整解压后运行包内的安装器。

普通安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

升级或覆盖已安装版本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Force
```

指定 Codex Home：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -CodexHome "D:\CodexHome"
```

默认安装位置：

```text
%USERPROFILE%\.codex\skills\rebuild-editable-ui-psd
```

使用 `-Force` 升级时，安装器会先将旧版本移动到：

```text
<CodexHome>\skill-backups\rebuild-editable-ui-psd-<时间戳>
```

如果安装后 Codex 没有立即显示该 skill，请新建任务或重新启动 Codex Desktop。

## 使用方法

在 Codex Desktop 中附加一张 PNG 或 JPG 截图，然后直接输入类似指令：

```text
把这张图片拆解为 PSD
```

也可以使用：

```text
把截图拆成 PSD 图层
图片转可编辑 PSD
截图转分层 PSD
拆图做 PSD
UI 截图还原成 PSD
```

如需显式调用 skill：

```text
使用 $rebuild-editable-ui-psd 把这张 UI 截图拆解为 PSD。
```

## 工作流程

| 阶段 | 内容 | 是否需要用户确认 |
|---|---|---:|
| 1. 环境预检 | 检查 Photoshop、Python、GPU/CPU rembg 和输出路径 | 否 |
| 2. 对象盘点 | 识别场景、文字、形状、按钮、图标和独立装饰 | 否 |
| 3. 分类与蒙版审核 | 展示编号覆盖图、对象清单和初步蒙版 | **是** |
| 4. 图层规划 | 建立语义命名、父子关系和明确的 `z` 顺序 | 否 |
| 5. 场景重建 | 使用 `$imagegen` 生成完整无 UI 场景 | 否 |
| 6. 组件重建 | 抠取完整对象；残缺对象使用 `$imagegen` 整体重绘 | 否 |
| 7. 最终组合审核 | 展示与最终 PSD 相同内容的完整合成图 | **是** |
| 8. PSD 装配 | Photoshop 自动创建图层、保存 PSD 并导出透明 PNG | 否 |

两次人工审核都是阻塞步骤。未经确认，skill 不会继续进入下一阶段或把未经审核的视觉内容装配到最终 PSD。

## 图像生成策略

所有需要生成或编辑图像的步骤都必须调用 Codex 的 `$imagegen` skill：

- 默认使用 `$imagegen` 的内置工具模式和当前登录的 Codex 账号。
- 默认不请求或使用 `OPENAI_API_KEY`。
- 遵循 `$imagegen` 对参考图、提示词、输出检查、单项迭代和保存路径的规则。
- 项目实际使用的生成结果会复制或移动到任务工作区，不会只保留在临时生成目录。
- 只有用户明确要求 CLI/API，或明确确认 `$imagegen` 所要求的特殊降级方案时，才允许切换路径。

## rembg GPU 与 CPU 策略

安装器会维护两个互相隔离的运行环境，避免 `onnxruntime` 和 `onnxruntime-gpu` 冲突：

```text
%LOCALAPPDATA%\Codex\skill-runtime\rebuild-editable-ui-psd\rembg-3.6.1-gpu
%LOCALAPPDATA%\Codex\skill-runtime\rebuild-editable-ui-psd\rembg-3.6.1-cpu
```

选择规则：

1. 始终准备 CPU 回退环境。
2. 检测到 NVIDIA GPU 时安装 GPU 环境。
3. 只有 `CUDAExecutionProvider` 可用且真实 rembg 推理通过时，才选择 GPU。
4. 单次 GPU 抠图失败时，自动使用 CPU 重试。
5. 每次任务记录请求后端、实际后端和是否发生回退。

GPU 环境自带固定版本的 ONNX Runtime、CUDA 13 和 cuDNN DLL，不要求另外安装 CUDA Toolkit。

## 输出内容

完整任务通常包含：

```text
final.psd                     # 最终可编辑 PSD
preview.png                   # 最终预览图
png/                          # 每个非参考图层和图层组的透明 PNG
review-composite.png          # 第二次人工审核使用的完整合成图
classification-review.png     # 第一次人工审核使用的分类覆盖图
human-review.json             # 两次审核记录
clean_scene.png               # 完整无 UI 场景
clean-scene-job.json          # 场景生成记录
layer-manifest.json           # 图层、父子关系、坐标和 z 顺序
objects/                      # 独立栅格对象
masks/                        # 对象蒙版
gpt-image-log.json            # imagegen 生成与重绘记录
limitations.md                # 字体替换、近似项和生成区域
task-audit.json               # 版本、工具路由和执行审计
photoshop-report.json         # Photoshop 装配与导出报告
```

## PSD 图层约定

- 普通文字图层使用 `@` 前缀，例如 `@TitleText`。
- 按钮组使用 `Btn_` 或 `Button_`。
- 图案和普通栅格素材使用 `Img_` 或 `Image_`。
- 图标使用 `Icon_`。
- 背景使用 `Bg_` 或 `BG_`。
- 面板和弹窗使用 `Panel_` 或 `Popup_`。
- `00_REFERENCE` 是唯一允许不遵循普通命名规则的隐藏参考分支。
- 所有同级图层必须具有唯一、明确的数字 `z`；数值越低越靠后。

每个按钮必须是独立的顶层组，并包含自己的背景、装饰、图标和文字，不与其他界面元素混合。

## 仓库结构

```text
rebuild-editable-ui-psd/
├─ SKILL.md                    # skill 入口与核心工作流
├─ skill-metadata.json         # 版本和更新时间
├─ agents/
│  └─ openai.yaml              # Codex UI 元数据与默认提示词
├─ references/                 # 分类、重绘、图层和 Photoshop 规范
├─ scripts/                    # 环境检查、rembg、审计和 Photoshop 自动化
├─ requirements-rembg-cpu.txt  # 固定 CPU 依赖
└─ requirements-rembg-gpu.txt  # 固定 GPU/CUDA 依赖
```

发行包根目录还包含：

```text
install.ps1
README.md
rebuild-editable-ui-psd/
```

不要将本机虚拟环境、模型缓存、`__pycache__` 或 `.pyc` 文件提交到仓库或打入发行包。

## 环境验证

```powershell
$skill = Join-Path $env:USERPROFILE ".codex\skills\rebuild-editable-ui-psd"

python (Join-Path $skill "scripts\install_rembg.py") --ensure
python (Join-Path $skill "scripts\check_environment.py") --json
```

重点检查：

- `rembg.managed.ready` 为 `true`
- `rembg.managed.cpu.inference_probe.passed` 为 `true`
- NVIDIA 环境下 `rembg.managed.selected_backend` 通常为 `gpu`
- GPU 探针的 `active_provider` 为 `CUDAExecutionProvider`

`check_environment.py` 还会报告 Photoshop、PSD 工具和完整工作流依赖。缺少这些依赖不一定意味着 rembg 安装失败，应根据对应字段分别处理。

## 已知限制

- 普通文字可编辑，但字体和字形只保证大致相似，不保证恢复原始字体。
- 艺术字默认作为图案处理，不提供逐字编辑能力。
- 完整场景采用整体重新生成，视觉细节可能与原截图存在漂移。
- 残缺组件采用整体重绘，不保留原图可见部分的逐像素一致性。
- 自动 PSD 装配仅支持 Windows Photoshop 路径。
- 最终视觉质量由第二次人工审核决定，不使用后置 AI 评分替代人工确认。

## 第三方项目

背景移除功能基于 [danielgatis/rembg](https://github.com/danielgatis/rembg)。第三方组件仍遵循各自的许可证和分发条款。

## 当前版本

- Skill：`3.6.2`
- rembg：`2.0.77`
- rembg GPU 运行时：ONNX Runtime GPU `1.28.0`、CUDA 13、cuDNN
- 更新日期：`2026-07-31`
