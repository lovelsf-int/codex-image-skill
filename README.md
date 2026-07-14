# Codex API 图片生成 Skill

[English](README.en.md)

通过兼容 OpenAI 的图片接口生成单张图片，并默认跟随 Codex 当前启用的提供商。
除非明确指定其他 `gpt-image-*` 模型，否则本 Skill 使用 `gpt-image-2`。它只使用
仓库内置的 API 和命令行流程，不会修改、替换或调用 Codex 内置的 `image_gen` 工具。

## 适用范围

- 根据文本提示词生成单张图片。
- 复用当前 Codex 或 CC Switch 路由，无需重复填写 URL 或密钥。
- 在明确要求时支持旧式环境变量路由。
- 接收 `data[].b64_json` 中的 Base64 图片响应。

本 Skill 不支持图片编辑、遮罩、批量生成、透明背景专用流程或仅返回 URL 的响应。

## 使用要求

- 已启用个人 Skills 的 Codex
- Python 3.10+
- 当前提供商支持 Bearer 身份验证并实现 `POST /v1/images/generations`
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

## 默认行为：跟随 Codex

路由选择参数是 `--source auto|codex|env`。省略 `--source` 时默认使用 `auto`，
它会优先解析 Codex 当前选中的完整路由，因此用户通常不需要重复配置 API URL 或密钥。

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

## Codex Home 选择

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

## 标准 Codex 提供商示例

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

## CC Switch 兼容性

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

## 显式环境变量回退

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

## 命令行示例

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

## 安全与输出契约

- 本 Skill 不会请求、打印或把凭证写入聊天输出。
- 不读取或使用 `tokens`、`access_token`、`refresh_token` 等 OAuth 字段。
- 不读取 CC Switch SQLite 数据库。
- 不会回退到 `api.openai.com`。
- 当前路由缺失、不完整、无效或不安全时会停止并报错。
- 除非提供 `--force`，否则保留已有输出文件。
- 返回的 Base64 数据经过验证后以原子方式写入。

脱敏摘要字段严格且仅限以下九项：`source`、`provider`、`credential_source`、`host`、`model`、`output`、`output_format`、`quality` 和 `size`。摘要绝不包含 `key`、`prompt`、`config`、OAuth 数据或任何 token 值。

## 提供商兼容性

提供商必须支持请求的 `gpt-image-*` 模型、Bearer 身份验证、
`/v1/images/generations` 和 `data[].b64_json`。不同提供商对 `size`、`quality`、
`output_format` 可选值的支持可能不同。本 Skill 不支持仅返回 URL 的响应。

## 测试与兼容矩阵

离线测试套件使用 `unittest`、假客户端和依赖注入，不需要调用付费图片 API：

```bash
python -m unittest discover -s tests -v
```

GitHub Actions 会在受支持的 Python 版本（包括 Python 3.10）上运行测试，以验证打包后的
Skill 和文档契约；工作流不会调用真实图片接口。
