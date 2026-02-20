# 图像生成 API 测试工具

[English](README.md)

一个面向生成接口的极简测试工具，支持 CLI 与 TUI 两种使用方式。

## 功能范围

- 提供商：`alibaba`、`google`、`glm`
- 图像任务：`text_to_image`、`image_to_image`
- CLI 命令：`single`、`compare`、`batch`、`models`、`history`
- TUI 页面：`Generate`、`Video`、`Speech`、`Models`、`History`、`Config`
- 复用服务层：`core/services/`

## 环境要求

- Python `>=3.11`

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

可选依赖：

```bash
pip install -e .[dev]   # pytest + ruff + build
pip install -e .[tui]   # textual
```

入口命令：

```bash
igt --help
image-gen-test --help
igt-tui
```

## 环境变量配置

先复制模板：

```bash
copy .env.example .env
```

常用字段：

- `ALIBABA_API_KEY`
- `ALIBABA_REGION`（`intl` 或 `cn`）
- `GOOGLE_API_KEY`
- `GLM_API_KEY`

常用可选字段：

- `IGT_OUTPUT_DIR`：默认输出目录
- `IGT_BIN_ALIAS_FORMAT`：下载 `.bin` 的别名格式（`png` 或 `jpg`）
- `IGT_ALIBABA_IMAGE2IMAGE_AUTOCROP`：`on` / `off`（默认 `off`）
- `IGT_PERSIST_PREPROCESSED_INPUT`：是否持久化自动裁剪输入图（默认 `off`）
- `IGT_CUSTOM_MODELS_PATH`：自定义模型注册表 JSON 路径

## CLI 快速开始

### single

```bash
igt single --provider alibaba --model qwen-image-max --task-type text_to_image --prompt "A cozy wooden cabin in snow" --size 1024x1024 --n 1
```

图生图示例：

```bash
igt single --provider google --model gemini-2.5-flash-image --task-type image_to_image --prompt "Turn this photo into anime style" --input-image "C:\path\to\input.png"
```

说明：

- `image_to_image` 必须传 `--input-image`。
- `image_to_image` 不传 `--size` 时，会优先自动使用原图尺寸（可解析时）。
- 反向提示词默认关闭，开启方式：
  - `--negative-prompt-enabled on --negative-prompt "..."`
- Alibaba 自动裁剪默认关闭，开启方式：
  - `--auto-crop on`
- 持久化自动裁剪输入图：
  - `--persist-preprocessed-input on`

### compare

```bash
igt compare --prompt "A red sports car drifting on wet road" --task-type text_to_image --provider-a alibaba --model-a qwen-image-max --provider-b google --model-b gemini-2.5-flash-image
```

会生成 `compare_summary.csv`。

### batch

```bash
igt batch --provider glm --model cogview-4-250304 --task-type text_to_image --prompts-file prompts.txt
```

会生成 `batch_summary.csv`。

### models（模型目录）

```bash
igt models
igt models --provider alibaba
igt models --provider alibaba --task-type image_to_image
igt models --recommend
igt models --format json
```

### history（历史记录）

```bash
igt history list --limit 10
igt history show --run-id 20260219-120301_alibaba_text_to_image_req_abc
```

## TUI（`igt-tui`）

### Generate 页

- 支持 `single` / `compare` / `batch`
- 模型下拉随 provider/task 自动过滤
- 宽高使用受约束下拉选项
- 提示词输入框固定在页面底部
- 快捷键：
  - `Enter`：提交当前模式
  - `Ctrl+J`：换行
- 输入框自动换行，并可自动拉伸（最大半屏）
- `Ctrl+C` 可复制当前焦点内容

### Video 页（Alibaba）

- 任务：`text_to_video`、`image_to_video`
- 默认模型：`wan2.6-i2v-flash`
- 使用 Alibaba 异步视频工作流
- `image_to_video` 必须传输入图路径/URL
- 反向提示词可选（开关控制）
- 提示词输入行为与 Generate 一致（底部输入框、`Enter` 提交、`Ctrl+J` 换行）

### Speech 页（Alibaba）

- 任务：`text_to_speech`
- 默认模型：`qwen3-tts-vd-realtime-2026-01-15`
- 使用 Alibaba 实时 websocket 会话流
- 运行依赖：`dashscope`（`pip install dashscope`）
- 必填字段：`voice`、`prompt`
- 提示词输入行为与 Generate 一致（底部输入框、`Enter` 提交、`Ctrl+J` 换行）

### Models 页

- 支持 provider/task/recommend 过滤
- 同时展示内置与自定义模型
- 仅允许删除自定义模型
- 聚焦模型表格后按 `Delete` 可直接删除选中自定义条目

### History 页

- 浏览运行历史
- 按 run id / 路径查看详细信息

### Config 页

- 在 TUI 内管理 API Key 与运行配置
- 支持 `Load Current Env`、`Apply Session`、`Save .env + Apply`
- 可配置项包括：
  - 输出目录
  - `.bin` 别名格式（`png` / `jpg`）
  - Alibaba 自动裁剪开关
  - 自动裁剪输入图持久化开关
  - 现有供应商下的自定义模型注册

## 输出目录结构

默认根目录：`runs/`

```text
runs/{timestamp}_{provider}_{task_type}_{request_id}/
  request.json
  response.json
  saved_images.json
  images/
  preprocessed_inputs.json   # 可选
  preprocessed_inputs/       # 可选
```

视频输出保存在运行目录下的 `videos/`，语音输出保存在 `audios/`。

## 开发命令

```bash
pytest -q
ruff check .
```

构建发布产物：

```bash
python -m pip install -e .[release]
python -m build
```

