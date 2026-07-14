# Codex API 图片生成 Skill

[English](README.en.md)

本仓库包含两条独立的图片工作流。Danko 专用 MCP 是推荐路径，支持文本生成图像和基于本地
参考图的图生图；较早的内置 CLI 是仅文本生成图像的旧版路径，并跟随当前活动的 Codex 提供商。
除非明确指定其他 `gpt-image-*` 模型，否则两条工作流都使用 `gpt-image-2`。

## 适用范围

- **Danko MCP（推荐）：** Danko 专用的文本生成图像和基于本地参考图的图生图请求。
- **旧版 CLI：** 仅文本生成图像，复用当前 Codex 或 CC Switch 路由；在明确要求时支持旧式环境变量路由。
- 两条工作流都接收 `data[].b64_json` 中的 Base64 图片响应。

旧版 CLI 不支持图生图或图片编辑。遮罩、批量生成、透明背景专用流程和仅返回 URL 的响应不属于
两条工作流的范围。

## 使用要求

- 已启用个人 Skills 的 Codex
- Python 3.10+
- **Danko MCP：** 已转发的 `DANKOTOKEN_API_KEY`，或在显式授权后的一条完整、活动的 Danko Codex 路由；它必须支持
  Bearer 身份验证、`POST /v1/images/generations` 和 `POST /v1/images/edits`
- **旧版 CLI：** 当前提供商支持 Bearer 身份验证并实现 `POST /v1/images/generations`
- 当前账号能够使用请求的 `gpt-image-*` 模型
- 接口响应包含 `data[].b64_json`

## 安装

克隆仓库后，安装 Python 依赖，并将 Skill 复制到 Codex Skills 目录。

### Windows PowerShell

```powershell
python -m pip install -r .\requirements.txt
Copy-Item -Recurse -Force .\skills\third-party-imagegen "$HOME\.codex\skills\third-party-imagegen"
```

### macOS

```bash
python3 -m pip install -r ./requirements.txt
mkdir -p "$HOME/.codex/skills"
cp -R ./skills/third-party-imagegen "$HOME/.codex/skills/third-party-imagegen"
```

### Linux

```bash
python3 -m pip install -r ./requirements.txt
mkdir -p "$HOME/.codex/skills"
cp -R ./skills/third-party-imagegen "$HOME/.codex/skills/third-party-imagegen"
```

只有 Python 3.10 需要条件依赖 `tomli`（`python_version < '3.11'`）；Python 3.11 及更高版本使用标准库中的 TOML 解析器。

## Danko MCP 图像工具（推荐）

配置 Danko 专用 image MCP 后，它是正常 Codex 图像请求的预期替代路径：文本生成图像请使用
`generate_danko_image`，基于本地参考图的图生图请使用 `edit_danko_image`，而不是内置的
`image_gen` 工具。它不会跟随任意活动的 Codex 提供商。这是工作流选择，不会在技术上禁用、移除或修改 Codex 的内置工具。
下面的旧版 CLI 仍可用于仅文本生成图像的兼容性回退，但在 MCP 可用时不是默认路径。

将下面的无密钥 MCP 配置加入 Codex，并将占位路径替换为本机绝对路径。`env_vars` 只转发环境变量名，
不要在此文件中填写任何密钥值。

```toml
[mcp_servers.danko_imagegen]
command = "python"
args = ["/absolute/path/to/danko_imagegen_server.py"]
cwd = "/absolute/path/to/your/workspace"
env_vars = ["DANKOTOKEN_API_KEY", "DANKOTOKEN_BASE_URL", "DANKOTOKEN_ALLOW_CODEX_FALLBACK"]
default_tools_approval_mode = "writes"
```

路由遵循环境变量优先原则。转发 `DANKOTOKEN_API_KEY` 后，MCP 服务器只使用显式设置的
`DANKOTOKEN_BASE_URL`，或精确的 Danko 回退地址 `https://dankotoken.com/v1`。没有专用密钥时，必须设置
`DANKOTOKEN_ALLOW_CODEX_FALLBACK=1` 才会显式授权它接受一条完整、当前活动的 Danko Codex 路由；否则 MCP 会停止并报告配置错误。它绝不会从非 Danko Codex 提供商路由自动推断其他域名，
也不会回退到 `api.openai.com`。

显式授权后的便利性优先回退只会在精确验证 Danko 主机后，使用活动提供商的提供商身份验证命令或
旧式 `auth.json.OPENAI_API_KEY`。因此，过期的官方 API 密钥可能被发送到已确认的 DankoToken 主机。
永不读取 OAuth 字段。

省略 `output_path` 时，默认目标是 MCP 工作区内的
`output/danko-imagegen/generated.<format>`。

需要使用其他提供商域名时，必须显式设置 `DANKOTOKEN_BASE_URL`，或修改源码中的默认端点。MCP 不会推断
非 Danko Codex 路由。

### Windows 持久环境变量

在 Windows 的“环境变量”界面中，为当前用户添加 `DANKOTOKEN_API_KEY`。仅在需要覆盖 Danko 默认端点时添加
`DANKOTOKEN_BASE_URL`。只有在明确允许 MCP 在主机验证后使用活动 Codex Danko 凭据时，才设置
`DANKOTOKEN_ALLOW_CODEX_FALLBACK=1`。修改持久 Windows 环境变量后必须重启 Codex，MCP 服务器才能收到更新后的值。
MCP 配置只转发变量名，不包含密钥值。

### MCP 工具示例

使用 `generate_danko_image` 进行文本生成图像。两个 MCP 工具都会将结果写入配置的工作区文件。

```text
generate_danko_image(
  prompt="A polished product photo of a red mechanical keyboard",
  output_path="output/keyboard.png"
)
```

仅可使用 `edit_danko_image` 编辑工作区内的本地 PNG、JPEG 或 WebP 参考图像；`input_image_path` 不能是 URL，
也不能位于工作区外。

```text
edit_danko_image(
  prompt="Change the keyboard keycaps to matte white",
  input_image_path="assets/keyboard.png",
  output_path="output/keyboard-white.png"
)
```

## 旧版 CLI：跟随活动 Codex 提供商（仅文本生成图像）

本节仅适用于旧版的文本生成图像 CLI。路由选择参数是 `--source auto|codex|env`。省略
`--source` 时默认使用 `auto`，它会优先解析 Codex 当前选中的完整路由，因此用户通常不需要
重复配置 API URL 或密钥。

- `--source auto` 优先使用当前 Codex 路由。只有在 Codex 配置不可用，并且环境变量能
  满足当前运行模式的路由要求时，才回退到环境变量路由。
- `--source codex` 要求提供完整且有效的 Codex 路由，不会回退到环境变量。
- `--source env` 明确要求使用 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 环境变量路由。

每条路由都作为一个完整整体解析。本 Skill 不会把一个来源或提供商的 URL 与另一个
来源或提供商的密钥混合使用。当前配置无效或不安全时会直接报错，而不是静默切换提供商。

实时环境变量路由必须同时提供有效 URL 和密钥。使用 `--dry-run` 时必须提供有效 URL，但不要求提供密钥。

使用 `--dry-run` 可以在不创建 SDK 客户端、也不发送网络请求的情况下验证路由和请求参数：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "阳光窗边坐着一只小狗" \
  --out output/dog.png \
  --dry-run
```

### Codex Home 选择

`CODEX_HOME` 用于指定 Codex 配置目录。需要检查另一套 Codex 安装时，
`--codex-home` 参数的优先级高于 `CODEX_HOME`。

```bash
CODEX_HOME=/path/to/codex python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "红色机械键盘的棚拍照片" \
  --dry-run

python skills/third-party-imagegen/scripts/generate_image.py \
  --codex-home /path/to/codex \
  --source codex \
  --prompt "红色机械键盘的棚拍照片" \
  --out output/keyboard.png
```

### 标准 Codex 提供商示例

Codex 通过 `model_provider` 选择一个提供商。下面是标准的 DankoToken 配置示例，
并不代表优先级规则；当前启用的 `model_provider` 始终是唯一依据。

```toml
model_provider = "dankotoken"

[model_providers.dankotoken]
name = "DankoToken"
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
wire_api = "responses"
```

解析器只读取当前启用提供商的 `base_url`，并可从该提供商范围内的
`experimental_bearer_token`、由 `env_key` 指定的环境变量或受支持的提供商
身份验证命令获取凭证。它不会检查未启用的提供商条目。

### CC Switch 兼容性

开源 CC Switch 桌面应用写入的实时 Codex 配置是唯一依据。本 Skill 支持全部三种
CC Switch 接入模式：

1. **旧式模式。** CC Switch 将当前提供商 URL 写入 `config.toml`，并将密钥写入
   `auth.json.OPENAI_API_KEY`。
2. **增强型官方登录保留模式。** CC Switch 保留官方 Codex 登录数据，并将当前第三方
   凭证写入对应提供商的 `experimental_bearer_token`。本 Skill 不读取或使用 OAuth
   字段及 OAuth token。
3. **本机代理接管模式。** CC Switch 将当前提供商指向本机回环地址，并使用
   `PROXY_MANAGED` 作为凭证占位符。`PROXY_MANAGED` 的精确允许列表仅包含 `localhost`、`127.0.0.1` 和 `::1`。所有非允许地址都会被拒绝，因此该占位符不会被发送到外部服务。

本地 CC Switch 代理必须暴露 `/v1/images/generations` 图片路由，通常应使用以 `/v1`
结尾的 base URL。只实现 `/v1/responses` 或 `/v1/chat/completions` 的代理无法通过
本 Skill 生成图片；实时请求遇到 404 时会直接说明该兼容性要求。

本 Skill 从不读取 CC Switch SQLite 数据库，只跟随上述实时 Codex 文件以及受支持的
环境变量或身份验证命令来源。

### 显式环境变量回退

仅在维护现有显式配置或主动选择 `--source env` 时使用环境变量路由。实时生成必须同时
设置 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`；使用 `--dry-run` 时仍需有效 URL，
但可以不设置密钥。

### Windows PowerShell

```powershell
$env:OPENAI_API_KEY = "your-token-service-key"
$env:OPENAI_BASE_URL = "https://your-token-service.example/v1"
python skills/third-party-imagegen/scripts/generate_image.py `
  --source env `
  --prompt "红色机械键盘的电影感产品照片" `
  --out output/keyboard.png
```

### macOS 或 Linux

```bash
export OPENAI_API_KEY='your-token-service-key'
export OPENAI_BASE_URL='https://your-token-service.example/v1'
python skills/third-party-imagegen/scripts/generate_image.py \
  --source env \
  --prompt "红色机械键盘的电影感产品照片" \
  --out output/keyboard.png
```

### 命令行示例

跟随当前 Codex 提供商，并使用默认的 `gpt-image-2` 模型：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "阳光窗边坐着一只小狗" \
  --out output/dog.png
```

强制使用 Codex 配置，并选择另一个受支持的图片模型：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --source codex \
  --model gpt-image-1 \
  --prompt "城市自行车的简洁编辑插画" \
  --size 1024x1024 \
  --quality high \
  --out output/bicycle.png
```

仅在明确需要时覆盖现有输出文件：

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "极简纸艺雕塑的棚拍照片" \
  --out output/sculpture.png \
  --force
```

### 安全与输出契约

- 本 Skill 不会请求、打印或把凭证写入聊天输出。
- 不读取或使用 `tokens`、`access_token`、`refresh_token` 等 OAuth 字段。
- 不读取 CC Switch SQLite 数据库。
- 不会回退到 `api.openai.com`。
- 当前路由缺失、不完整、无效或不安全时会停止并报错。
- 除非提供 `--force`，否则保留已有输出文件。
- 返回的 Base64 数据经过验证后以原子方式写入。

脱敏摘要字段严格且仅限以下九项：`source`、`provider`、`credential_source`、`host`、`model`、`output`、`output_format`、`quality` 和 `size`。摘要绝不包含 `key`、`prompt`、`config`、OAuth 数据或任何 token 值。

### 提供商兼容性

对于旧版 CLI，所选提供商必须支持请求的 `gpt-image-*` 模型、Bearer 身份验证、
`/v1/images/generations` 和 `data[].b64_json`。Danko MCP 仅限其专用 Danko 路由，并使用
`/v1/images/edits` 进行基于本地参考图的图生图。不同提供商对 `size`、`quality`、
`output_format` 可选值的支持可能不同。本仓库不支持仅返回 URL 的响应。

## 测试与兼容矩阵

离线测试套件使用 `unittest`、假客户端和依赖注入，不需要调用付费图片 API：

```bash
python -m unittest discover -s tests -v
```

GitHub Actions 会在受支持的 Python 版本（包括 Python 3.10）上运行测试，以验证打包后的
Skill 和文档契约；工作流不会调用真实图片接口。
