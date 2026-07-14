# Codex API ImageGen Skill

[简体中文](README.md)

Generate a single image through an OpenAI-compatible image endpoint while
following the active Codex provider by default. The Skill uses `gpt-image-2`
unless another `gpt-image-*` model is explicitly requested. It uses only its
bundled API and CLI path; it never modifies, replaces, or invokes Codex's
built-in `image_gen` tool.

## Scope

- Generate one image from a text prompt.
- Use the active Codex or CC Switch route without duplicating its URL or key.
- Support an explicit legacy environment route when requested.
- Accept base64 image responses in `data[].b64_json`.

Image editing, masks, batch generation, transparency-specific workflows, and
URL-only responses are outside this Skill's scope.

## Requirements

- Codex with personal Skills enabled
- Python 3.10+
- An active provider that accepts Bearer authentication and implements
  `POST /v1/images/generations`
- Access to the requested `gpt-image-*` model
- A response containing `data[].b64_json`

## Installation

Clone this repository, install its Python dependencies, and copy the Skill into
your Codex Skills directory.

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

Only Python 3.10 needs the conditional `tomli` compatibility dependency (`python_version < '3.11'`); Python 3.11 and newer use the standard-library TOML parser.

## Danko MCP Image Tools (Recommended)

When configured, the Danko image MCP is the intended replacement path for
normal Codex image work: use `generate_danko_image` for text-to-image and
`edit_danko_image` for edits instead of the built-in `image_gen` tool. This
selects an image-generation workflow; it does not technically disable, remove,
or modify Codex's built-in tool. The CLI documented below remains a
compatibility fallback, not the default when the MCP is available.

Add this secret-free MCP configuration to Codex, replacing the placeholder
paths with local absolute paths. `env_vars` forwards variable names only; never
put a key value in this file.

```toml
[mcp_servers.danko_imagegen]
command = "python"
args = ["/absolute/path/to/danko_imagegen_server.py"]
cwd = "/absolute/path/to/your/workspace"
env_vars = ["DANKOTOKEN_API_KEY", "DANKOTOKEN_BASE_URL"]
default_tools_approval_mode = "writes"
```

Routing is environment-first. When `DANKOTOKEN_API_KEY` is forwarded to the
MCP server, it uses an explicitly supplied `DANKOTOKEN_BASE_URL`, or the exact
Danko fallback `https://dankotoken.com/v1`. Without that dedicated key, it
accepts only one coherent active Codex route on the Danko host. It never
auto-infers another provider or domain from a non-Danko Codex route, and it
never falls back to `api.openai.com`.

To use another provider domain, explicitly set `DANKOTOKEN_BASE_URL` or modify
the source default endpoint. The MCP does not infer a non-Danko Codex route.

### Persistent Windows Environment

In Windows **Environment Variables**, add `DANKOTOKEN_API_KEY` for your user.
Add `DANKOTOKEN_BASE_URL` only when you need to override the Danko default.
Restart Codex after persistent Windows environment-variable changes so the MCP
server receives the updated values. The MCP configuration forwards these names;
it does not contain secret values.

### MCP Tool Examples

Use `generate_danko_image` for text-to-image. Both MCP tools write the result
to a file in the configured workspace.

```text
generate_danko_image(
  prompt="A polished product photo of a red mechanical keyboard",
  output_path="output/keyboard.png"
)
```

Use `edit_danko_image` only with a local PNG, JPEG, or WebP reference image
inside the workspace; `input_image_path` cannot be a URL or a path outside it.

```text
edit_danko_image(
  prompt="Change the keyboard keycaps to matte white",
  input_image_path="assets/keyboard.png",
  output_path="output/keyboard-white.png"
)
```

## Default Behavior: Follow Codex

The route selector is `--source auto|codex|env`. When `--source` is omitted,
`auto` is used. It first resolves the complete route currently selected by
Codex, so users normally do not need to duplicate an API URL or credential.

- `--source auto` first uses the active Codex route. It falls back to the
  environment route only when Codex configuration is unavailable and the
  environment satisfies the current run mode's routing requirements.
- `--source codex` requires a complete, valid Codex route and does not fall back
  to the environment.
- `--source env` requires the explicit `OPENAI_API_KEY` and
  `OPENAI_BASE_URL` pair.

Each route is resolved as a coherent pair. The Skill never combines a URL from
one source or provider with a credential from another. Invalid or unsafe active
configuration is reported instead of silently switching providers.

Live environment routing requires both a valid URL and a key. With `--dry-run`, a valid URL is required but the key is not.

Use `--dry-run` to validate routing and request parameters without constructing
an SDK client or making a network request:

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --out output/keyboard.png \
  --dry-run
```

## Codex Home Selection

`CODEX_HOME` selects the Codex configuration directory. The `--codex-home`
option takes priority when a command must inspect another Codex installation.

```bash
CODEX_HOME=/path/to/codex python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A studio photo of a red mechanical keyboard" \
  --dry-run

python skills/third-party-imagegen/scripts/generate_image.py \
  --codex-home /path/to/codex \
  --source codex \
  --prompt "A studio photo of a red mechanical keyboard" \
  --out output/keyboard.png
```

## Standard Codex Provider Example

Codex selects one provider through `model_provider`. The configuration below is
a standard DankoToken example. DankoToken has no hardcoded priority: the active
`model_provider` is always the source of truth.

```toml
model_provider = "dankotoken"

[model_providers.dankotoken]
name = "DankoToken"
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
wire_api = "responses"
```

For the active provider only, the resolver reads its `base_url` and can obtain
the credential from provider-scoped `experimental_bearer_token`, the environment
variable named by `env_key`, or a supported provider auth command. It does not
inspect inactive provider entries.

## CC Switch Compatibility

The live Codex configuration written by the open-source CC Switch desktop app is
the source of truth. The Skill supports all three CC Switch integration modes:

1. **Legacy mode.** CC Switch writes the selected provider URL to `config.toml`
   and its key to `auth.json.OPENAI_API_KEY`.
2. **Enhanced official-auth-preservation mode.** CC Switch keeps the official
   Codex login data and writes the active third-party credential to that
   provider's `experimental_bearer_token`. The Skill does not read or use OAuth
   fields or OAuth tokens.
3. **Localhost takeover mode.** CC Switch points the active provider at an exact
   loopback host, using `PROXY_MANAGED` as the credential placeholder. The exact `PROXY_MANAGED` allowlist contains only `localhost`, `127.0.0.1`, and `::1`.
   `PROXY_MANAGED` is rejected for every non-loopback destination and therefore
   cannot be sent to an external service.

A local CC Switch proxy must expose the image route at
`/v1/images/generations`, normally by using a base URL that ends in `/v1`. A
proxy that only implements `/v1/responses` or `/v1/chat/completions` cannot
generate images with this Skill. A live 404 explains this compatibility
requirement.

The Skill never reads the CC Switch SQLite database. It only follows the live
Codex files and supported environment or auth-command sources described above.

## Explicit Environment Fallback

Use the environment route only for an existing explicit setup or when
`--source env` is intentionally selected. Live generation requires both
`OPENAI_BASE_URL` and `OPENAI_API_KEY`; `--dry-run` still requires a valid URL
but does not require the key.

### Windows PowerShell

```powershell
$env:OPENAI_API_KEY = "your-token-service-key"
$env:OPENAI_BASE_URL = "https://your-token-service.example/v1"
python skills/third-party-imagegen/scripts/generate_image.py `
  --source env `
  --prompt "A cinematic product photo of a red mechanical keyboard" `
  --out output/keyboard.png
```

### macOS or Linux

```bash
export OPENAI_API_KEY='your-token-service-key'
export OPENAI_BASE_URL='https://your-token-service.example/v1'
python skills/third-party-imagegen/scripts/generate_image.py \
  --source env \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --out output/keyboard.png
```

## CLI Examples

Follow the current Codex provider and use the default `gpt-image-2` model:

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A small dog sitting beside a sunny window" \
  --out output/dog.png
```

Require Codex configuration and choose another supported image model:

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --source codex \
  --model gpt-image-1 \
  --prompt "A clean editorial illustration of a city bicycle" \
  --size 1024x1024 \
  --quality high \
  --out output/bicycle.png
```

Replace an existing output file only when that is intentional:

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A minimalist paper sculpture photographed in a studio" \
  --out output/sculpture.png \
  --force
```

## Security and Output Contract

- The Skill never requests, prints, or writes credentials into chat output.
- OAuth fields including `tokens`, `access_token`, and `refresh_token` are not
  read or used.
- The CC Switch SQLite database is not read.
- There is no fallback to `api.openai.com`.
- A missing, incomplete, invalid, or unsafe selected route stops with an error.
- Existing files are preserved unless `--force` is supplied.
- Returned base64 data is validated and written atomically.

Sanitized summary fields are exactly and only: `source`, `provider`, `credential_source`, `host`, `model`, `output`, `output_format`, `quality`, and `size`. `key`, `prompt`, `config`, OAuth data, and token values are never included.

## Provider Compatibility

The provider must support the requested `gpt-image-*` model, Bearer
authentication, `/v1/images/generations`, and `data[].b64_json`. Providers may
differ in their accepted `size`, `quality`, and `output_format` values. URL-only
responses are unsupported.

## Testing and Compatibility Matrix

The offline test suite uses `unittest`, fake clients, and dependency injection,
so it does not require a paid image API request:

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the suite on supported Python versions, including Python
3.10, to validate the packaged Skill and its documentation contract. No real
image endpoint is called by the workflow.
