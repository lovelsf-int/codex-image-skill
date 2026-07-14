# Codex 当前 Provider 自动路由设计

日期：2026-07-14

## 背景

当前 `third-party-imagegen` Skill 只从 `OPENAI_API_KEY` 和
`OPENAI_BASE_URL` 读取图片 API 路由。用户如果已经通过 Codex
`config.toml` 或开源桌面项目 CC Switch 配置第三方 Token 服务，
仍需重复设置环境变量。

本次改动让 Skill 默认跟随 Codex 当前生效的 provider，同时继续支持
原有环境变量方式。目标场景包括 DankoToken 等 OpenAI-compatible
Token 服务，以及 CC Switch 对 Codex 的直接切换、官方认证保留和本地
代理接管模式。

## 目标

1. 默认从当前 Codex live 配置中解析完整的 API URL 和凭据。
2. 支持 Codex 标准自定义 provider 配置。
3. 支持 CC Switch 当前和历史版本使用的三种凭据形态。
4. 不打印、持久化或跨 provider 混用任何密钥。
5. 无法得到完整、安全的路由时立即失败，不回退到
   `api.openai.com`。
6. 保留现有环境变量模式，避免破坏已部署用户。

## 非目标

- 不读取 CC Switch SQLite 数据库或供应商内部存储。
- 不提取或使用 Codex OAuth Access Token。
- 不绕过 CC Switch 本地代理以寻找真实上游凭据。
- 不为仅支持 Chat Completions 的服务实现图片协议转换。
- 不改变单图生成、默认 `gpt-image-2` 和输出文件行为。

## 方案选择

采用“读取 Codex 当前 live 配置”的方案。CC Switch 已把当前选择投影到
Codex 的 `config.toml` 和 `auth.json`；读取这两个 live 文件可以跟随
实际生效状态，而不依赖 CC Switch 私有数据库结构。

不采用直接读取 CC Switch 数据库的方案，因为数据库路径和 schema
属于内部实现，读取其中的原始密钥会扩大安全边界。

不要求 CC Switch 额外导出环境变量，因为这会重新引入重复配置。

## 命令行接口

新增参数：

- `--source auto|codex|env`，默认 `auto`。
- `--codex-home PATH`，覆盖 Codex 配置目录。

语义：

- `auto`：先尝试得到完整的 Codex 路由；若 Codex 路由不完整，再尝试
  完整的环境变量路由。
- `codex`：只允许 Codex 路由。
- `env`：只允许 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 路由。

路由必须按“完整来源”选择。脚本不得把 Codex URL 与环境变量 Key
拼接，也不得把环境变量 URL 与 Codex Key 拼接。

`--codex-home` 优先级高于 `CODEX_HOME`；未指定时使用
`~/.codex`。

## Codex 配置解析

Python 3.11 及以上使用标准库 `tomllib`。Python 3.10 使用
`tomli` 兼容包。

URL 解析顺序：

1. 读取顶层 `model_provider`。
2. 若存在当前 provider，读取
   `model_providers.<current>.base_url`。
3. 仅当当前 provider 未设置或为内置 `openai` 时，读取顶层
   `openai_base_url`。
4. 仅当当前 provider 未设置时，为兼容旧配置读取顶层 `base_url`。
5. 自定义 provider 缺少自己的 `base_url` 时立即失败。
6. 不读取任何非当前 provider 的 URL。

凭据解析顺序仅在同一当前 provider 内进行：

1. 当前 provider 的 `experimental_bearer_token`。
2. 当前 provider 的 `env_key` 所命名的环境变量。
3. 当前 provider 的 `auth.command`。
4. 顶层 `experimental_bearer_token`。
5. `auth.json` 顶层的 `OPENAI_API_KEY`。

`auth.command` 按 Codex 官方约定执行：无 stdin，使用配置中的
`args`，应用 `timeout_ms`，读取并 trim stdout。非零退出、超时或
空输出均为配置错误。命令和输出不得写入日志。

脚本只读取 `auth.json.OPENAI_API_KEY`。它不得访问 `tokens`、
`access_token`、`refresh_token` 或其他 OAuth 字段。

## CC Switch 兼容

### 旧版切换模式

CC Switch 可能把第三方 Key 写入
`auth.json.OPENAI_API_KEY`，并把当前 provider 与 URL 写入
`config.toml`。解析器使用这两个 live 文件组成一个 Codex 路由。

### 官方认证保留模式

CC Switch 保留 `auth.json` 中的官方 OAuth 登录，并把第三方 Key 写入
当前 provider 的 `experimental_bearer_token`。解析器优先使用
provider-scoped token，因此不会误用官方 OAuth 数据。

### 本地代理接管模式

CC Switch 可能把当前 provider URL 指向 `localhost`、`127.0.0.1`
或 `::1`，并使用 `PROXY_MANAGED` 作为 bearer token 占位符。

`PROXY_MANAGED` 仅在 URL 主机是 loopback 时有效。若它与非 loopback
URL 同时出现，脚本立即失败，避免把占位符发送到外部服务。

脚本把图片请求发送到 live loopback URL，不读取 CC Switch 数据库中的
真实上游 Key。若本地代理未实现 `/images/generations`，脚本返回明确
的图片端点不兼容错误。

## 数据结构

新增不可变路由对象 `ResolvedRoute`：

- `api_key`
- `base_url`
- `host`
- `source`：`codex` 或 `env`
- `provider_id`
- `credential_source`
- `codex_home`

`credential_source` 只记录类别，例如
`provider.experimental_bearer_token`、`provider.env_key`、
`provider.auth.command`、`auth.json.OPENAI_API_KEY` 或
`OPENAI_API_KEY`，绝不记录密钥值。

## 执行流程

1. 解析命令行参数。
2. 按 `--source` 解析一个完整 `ResolvedRoute`。
3. 校验 URL、loopback 占位符规则和密钥存在性。
4. 构造图片请求 payload，模型仍默认 `gpt-image-2`。
5. dry-run 输出脱敏摘要后结束。
6. live 模式显式把 `api_key` 和 `base_url` 传给 OpenAI SDK。
7. 保持现有 base64 解码、URL-only 拒绝和原子写文件逻辑。

## 安全与错误处理

- 所有日志和异常都不得包含密钥、auth command stdout、Authorization
  头或完整配置内容。
- 配置文件不存在、TOML/JSON 无效、provider 不存在、URL 缺失或凭据
  缺失时，错误信息指出检查位置和字段，但不显示字段值。
- `auto` 只有在 Codex 路由整体不可用时才尝试完整环境变量路由。
- dry-run 判断路由完整性时只要求 URL；live 模式同时要求 URL 和凭据。
- 不把官方 OAuth token 当作图片 API Key。
- 不默认连接 OpenAI 官方域名。
- dry-run 允许省略 live Key，但仍必须解析并验证 URL；摘要显示来源、
  provider、host、模型和输出路径。

## 文档更新

`README.md` 和 `SKILL.md` 将说明：

- 零重复配置的 Codex-follow 默认模式。
- DankoToken 等标准 `model_provider + base_url + env_key` 示例。
- CC Switch 三种兼容路径及限制。
- 本地代理必须支持 `/v1/images/generations`。
- 环境变量模式和显式 source 选择。
- Skill 不读取 CC Switch 数据库，不使用 OAuth token。

## 测试设计

新增离线单元测试覆盖：

1. Codex 标准 provider 的 `base_url + env_key`。
2. CC Switch 旧版 `auth.json.OPENAI_API_KEY`。
3. CC Switch 增强模式 provider-scoped
   `experimental_bearer_token`。
4. CC Switch loopback `PROXY_MANAGED`。
5. 非 loopback URL 搭配 `PROXY_MANAGED` 时拒绝。
6. OAuth-only `auth.json` 不被当作 API Key。
7. 不读取非当前 provider。
8. `auth.command` 成功、超时、非零退出和空输出。
9. Codex 路由不完整时 `auto` 使用完整 env 路由。
10. 防止 Codex URL 与 env Key 混用。
11. `CODEX_HOME` 和 `--codex-home` 优先级。
12. dry-run 摘要不泄露凭据。

按用户要求，本地不运行测试。测试由 GitHub Actions 在推送后执行。

## 参考

- Codex 自定义 provider：
  https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers
- Codex 认证与凭据存储：
  https://learn.chatgpt.com/docs/auth
- CC Switch 官方认证保留模式：
  https://github.com/farion1231/cc-switch/blob/main/docs/guides/codex-official-auth-preservation-guide-zh.md
- CC Switch Codex 配置实现：
  https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/codex_config.rs
