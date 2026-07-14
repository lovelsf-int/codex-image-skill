# Codex API ImageGen Skill

通过用户自己的第三方 OpenAI-compatible Token 服务，从 Codex 生成单张图片。此 Skill 默认使用 `gpt-image-2`，并且只走 API/CLI 路径；它**不会修改、替换或调用** Codex 内置 `image_gen`。

## 功能与范围

- 生成单张图片，默认 `gpt-image-2`、`1024x1024`、`medium`、PNG。
- 可指定 `--model`（仅接受 `gpt-image-*`）、`--size`、`--quality`、`--output-format`、`--out`、`--dry-run` 和 `--force`。
- 首版不支持图片编辑、蒙版、批量生成或透明背景专用流程。

## 前置条件

- 支持个人 Skills 的 Codex
- Python 3.10+
- 支持 Bearer Token 的第三方 OpenAI-compatible 服务
- 服务需提供 `POST /v1/images/generations`，并返回 `data[].b64_json`

## 安装

### Windows (PowerShell)

```powershell
git clone https://github.com/lovelsf-int/codex-image-skill.git
Copy-Item -Recurse -Force .\codex-image-skill\skills\third-party-imagegen "$HOME\.codex\skills\third-party-imagegen"
python -m pip install -r .\codex-image-skill\requirements.txt
```

### macOS / Linux

```bash
git clone https://github.com/lovelsf-int/codex-image-skill.git
cp -R codex-image-skill/skills/third-party-imagegen "$HOME/.codex/skills/third-party-imagegen"
python -m pip install -r codex-image-skill/requirements.txt
```

安装后重启 Codex，使其发现新 Skill。

## 配置环境变量

请在本机终端或系统环境中设置变量，不要在 Codex 对话、截图或仓库中写入真实密钥。

### Windows (PowerShell)

```powershell
$env:OPENAI_API_KEY = "your-token-service-key"
$env:OPENAI_BASE_URL = "https://your-token-service.example/v1"
```

### macOS / Linux

```bash
export OPENAI_API_KEY='your-token-service-key'
export OPENAI_BASE_URL='https://your-token-service.example/v1'
```

## 在 Codex 中使用

```text
Use $third-party-imagegen to generate a cinematic product photo of a red mechanical keyboard and save it to output/keyboard.png.
```

也可直接说明“通过我的第三方 Token 服务”或“使用 `OPENAI_BASE_URL` 和 `gpt-image-2` 生成图片”，以触发该 Skill。

## CLI 示例

先检查参数与路由，不创建客户端、不访问网络：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --out output/keyboard.png \
  --dry-run
```

实际生成并允许覆盖同名文件：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --model gpt-image-2 \
  --size 1024x1024 \
  --quality medium \
  --output-format png \
  --out output/keyboard.png \
  --force
```

## 路由与安全

### No fallback

`OPENAI_BASE_URL` 是必填项。缺失或无效时，脚本会在导入 SDK 和创建客户端之前失败，绝不会回退到 `api.openai.com`。实时调用还必须有 `OPENAI_API_KEY`；dry-run 仍要求 base URL，但不要求密钥。

脚本会将 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 显式传给 OpenAI Python SDK。日志仅显示服务主机名、模型和输出路径，不打印密钥、Authorization 头、查询参数或提示词。已有文件不会被覆盖，除非添加 `--force`；图片会先写入同目录临时文件，再原子地落到最终路径。

## 兼容性提醒

服务必须兼容 OpenAI Python SDK 的 Bearer 认证，支持 `gpt-image-*` 模型（默认 `gpt-image-2`），暴露 `/v1/images/generations`，并在响应中返回 `data[].b64_json`。只返回 URL 的响应、仅支持 `/v1/responses` 或 `/v1/chat/completions` 的服务不兼容本 Skill。

不同 Token 服务对可选尺寸、质量档位或 `output_format` 的支持可能不同；服务端不支持时，脚本会报告对应的认证、端点/模型、配额或请求错误类别。

## 测试

测试使用 `unittest` 与 fake client/依赖注入，不发起网络请求或付费调用：

```bash
python -m unittest discover -s tests -v
```
