# Codex API ImageGen Skill

Generate one image through an OpenAI-compatible image endpoint while following
the active Codex provider by default. The Skill uses `gpt-image-2` unless a
different `gpt-image-*` model is requested. It only uses the bundled API/CLI
path and never modifies, replaces, or invokes Codex built-in `image_gen`.

## Requirements

- Codex with personal Skills enabled
- Python 3.10+
- An active route that accepts Bearer authentication and implements
  `POST /v1/images/generations`
- A response containing `data[].b64_json`

Install the repository dependencies after cloning and copying the Skill to your
Codex Skills directory:

```powershell
python -m pip install -r .\requirements.txt
Copy-Item -Recurse -Force .\skills\third-party-imagegen "$HOME\.codex\skills\third-party-imagegen"
```

On macOS or Linux, use the corresponding `cp -R` command to copy the Skill.

## Default: Follow Codex

The default CLI source is `--source auto|codex|env`, with `auto` selected when
`--source` is omitted. `auto` first resolves the complete route selected by
Codex, so no duplicate API configuration is needed. It only uses the legacy
environment route when Codex is unavailable and the environment provides a
complete explicit pair. Use `--source codex` to require Codex configuration,
or `--source env` to require that legacy pair.

```bash
python skills/third-party-imagegen/scripts/generate_image.py \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --out output/keyboard.png \
  --dry-run
```

`CODEX_HOME` selects the Codex configuration directory. `--codex-home` has
priority when a command needs to inspect a different installation:

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

Codex selects one provider through `model_provider`. The following is a
standard DankoToken provider example, not a priority rule: the active
`model_provider` is always the source of truth.

```toml
model_provider = "dankotoken"

[model_providers.dankotoken]
name = "DankoToken"
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
wire_api = "responses"
```

For the active provider only, the route resolver reads its `base_url` and can
obtain a credential from `experimental_bearer_token`, the environment variable
named by `env_key`, or a supported provider auth command. It does not inspect
other provider entries or mix a URL from one route with a credential from
another.

## CC Switch Compatibility

CC Switch live Codex configuration is the source of truth. The Skill supports
these three shapes without reading the CC Switch database:

1. **Legacy mode.** CC Switch writes the selected provider URL to
   `config.toml` and the key to `auth.json.OPENAI_API_KEY`.
2. **Enhanced official-auth-preservation mode.** CC Switch retains official
   Codex login data and stores the active third-party credential in that
   provider's `experimental_bearer_token`. The Skill does not read or use any
   OAuth token.
3. **Localhost takeover.** CC Switch routes the active provider to a loopback
   host such as `localhost`, `127.0.0.1`, or `::1` and uses `PROXY_MANAGED` as
   the credential placeholder. `PROXY_MANAGED` is rejected for non-loopback
   destinations, so it cannot be sent to an external service.

A local CC Switch proxy must forward the image endpoint at
`/v1/images/generations` (normally with a `/v1` base URL). A proxy that only
implements `/v1/responses` or `/v1/chat/completions` cannot generate images
with this Skill. A live 404 reports this compatibility limitation directly.

## Legacy Explicit Environment Route

Use this only when explicitly requested or when maintaining an existing
environment-based setup. Both variables are required for live calls:

```powershell
$env:OPENAI_API_KEY = "your-token-service-key"
$env:OPENAI_BASE_URL = "https://your-token-service.example/v1"
python skills/third-party-imagegen/scripts/generate_image.py `
  --source env `
  --prompt "A cinematic product photo of a red mechanical keyboard" `
  --out output/keyboard.png
```

```bash
export OPENAI_API_KEY='your-token-service-key'
export OPENAI_BASE_URL='https://your-token-service.example/v1'
python skills/third-party-imagegen/scripts/generate_image.py \
  --source env \
  --prompt "A cinematic product photo of a red mechanical keyboard" \
  --out output/keyboard.png
```

## Safety and Output

Use `--dry-run` to validate the selected route and request parameters without
creating an SDK client or making a network request. Its JSON summary is
sanitized: it identifies the source, provider, credential source category,
host, model, and output path, but never prints a key, Authorization header,
OAuth token, URL query credential, auth-command output, or prompt.

The Skill never reads CC Switch database contents, never uses OAuth tokens, and
never falls back to `api.openai.com`. It stops when a selected route is missing
or invalid. Existing output files are preserved unless `--force` is supplied;
image data is written atomically after validating the returned base64 payload.

## Compatibility

The provider must support the requested `gpt-image-*` model, Bearer
authentication, `/v1/images/generations`, and `data[].b64_json`. URL-only
responses are unsupported. Providers can differ in their support for optional
size, quality, and `output_format` values.

## Tests

The repository test suite uses `unittest` with fake clients and dependency
injection; it does not require a paid image API call:

```bash
python -m unittest discover -s tests -v
```
