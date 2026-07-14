---
name: third-party-imagegen
description: Use when generating or editing images through the configured Danko MCP, or when a legacy text-to-image CLI request must follow the active Codex provider.
---

# Third-Party Image Generation

When the Danko-specific image MCP server is configured, use it as the intended
replacement path for normal Codex image work. It supports text-to-image through
`generate_danko_image` and local image-to-image through `edit_danko_image`,
instead of the built-in `image_gen` tool. This selects the configured MCP
workflow; it does not disable, remove, or modify Codex's built-in tool.

The bundled CLI remains a compatibility fallback for an explicitly requested
legacy workflow. It is not the default when the Danko MCP is available.

## Danko MCP Workflow

- Never use the built-in `image_gen` tool for an image request covered by the
  configured Danko MCP workflow.
- `generate_danko_image` and `edit_danko_image` both write the returned image
  to a file inside the MCP workspace. Use `output_path` when the user chooses a
  specific path; otherwise the server writes `generated.png`.
- `edit_danko_image` requires `input_image_path` to be a local PNG, JPEG, or
  WebP file inside that workspace. Never supply a URL or a path outside the
  workspace.
- Use `gpt-image-2` unless the user explicitly requests another model beginning
  with `gpt-image-`. Both tools accept `prompt`, `model`, `size`, `quality`,
  `output_format`, and `output_path`; editing also accepts `input_image_path`.
- Secrets come only from forwarded `DANKOTOKEN_API_KEY` and optional
  `DANKOTOKEN_BASE_URL` environment variables, or from one coherent active
  Codex Danko route. Never request, print, or place credentials in chat. Do not
  use OAuth tokens or read CC Switch database contents.
- Environment routing has priority: when `DANKOTOKEN_API_KEY` is present, use
  `DANKOTOKEN_BASE_URL` only when explicitly set, otherwise use the fixed
  default `https://dankotoken.com/v1`. Never fall back to `api.openai.com`.
- Without a forwarded dedicated key, use only an active Codex route whose host
  is `dankotoken.com` or `www.dankotoken.com`. Never infer another provider or
  domain from Codex. A different provider domain requires an explicit
  `DANKOTOKEN_BASE_URL` override or a source change to the default endpoint.

## CLI Compatibility Fallback

- Use `scripts/generate_image.py` only when the user explicitly needs the
  compatibility CLI. It is a legacy text-to-image-only path; it does not
  support image-to-image or image editing. Its available selector is
  `--source auto|codex|env` and it defaults to `--source auto`.
- `--source auto` follows the active Codex provider using live `CODEX_HOME`
  configuration (or `--codex-home PATH`). `--source codex` requires a usable
  Codex route; `--source env` is for the legacy explicit `OPENAI_API_KEY` and
  `OPENAI_BASE_URL` pair.
- Read only the active `model_provider`. A provider can supply credentials
  through `experimental_bearer_token`, an `env_key`, or its supported auth
  command; legacy CC Switch configuration can use `auth.json.OPENAI_API_KEY`.
- Treat CC Switch live configuration as the source of truth. Do not infer a
  provider priority, inspect inactive provider entries, or combine a URL from
  one source with a key from another. `PROXY_MANAGED` is accepted only for
  `localhost`, `127.0.0.1`, or `::1`.

## MCP Request Pattern

1. Confirm the Danko MCP is configured and select `generate_danko_image` or
   `edit_danko_image`.
2. For an edit, confirm that the requested source image is a local workspace
   image before calling the tool.
3. Send the prompt and requested output settings, with an explicit
   `output_path` when needed. Do not expose route or credential values.
4. Report the written output path. Sanitized summaries must never include a
   key, prompt, config, OAuth data, or token value.

For CLI compatibility work, use `--dry-run` to validate routing and parameters
without a network request. It does not construct an SDK client and never
reveals credentials.
