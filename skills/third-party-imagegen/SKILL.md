---
name: third-party-imagegen
description: Use when generating images through the active Codex provider, a third-party OpenAI-compatible token service, or a gpt-image-2 request that must not use Codex built-in image generation.
---

# Third-Party Image Generation

Generate one image through the bundled API client and the current Codex route by default.

## Required Routing

- Never use the built-in `image_gen` tool for this workflow.
- The available source selector is `--source auto|codex|env`; default to `--source auto` unless the user explicitly asks for `codex` or `env`.
- `--source auto` follows the active Codex provider. It uses the live `CODEX_HOME` configuration (or `--codex-home PATH`) without asking the user to duplicate values.
- `--source codex` requires a usable Codex route. `--source env` is only for the legacy explicit `OPENAI_API_KEY` and `OPENAI_BASE_URL` pair.
- Never fall back to `api.openai.com`. Stop when the selected source cannot provide a valid image route.
- Never request, print, or place credentials in chat. Do not use OAuth tokens or read CC Switch database contents.
- Use `gpt-image-2` unless the user explicitly requests another model beginning with `gpt-image-`.
- This Skill supports single-image generation only. Do not add editing, masks, batch requests, or transparency-specific flows.

## Codex Route Resolution

- Read only the current `model_provider` from Codex live configuration. A provider can supply credentials through `experimental_bearer_token`, an `env_key`, or its supported auth command; legacy CC Switch configuration can use `auth.json.OPENAI_API_KEY`.
- A standard Codex provider such as DankoToken is selected only when its identifier is the current `model_provider`; this Skill never assigns provider priority.
- Treat CC Switch live Codex configuration as the source of truth. Do not infer a provider priority, inspect other provider entries, or combine a URL from one source with a key from another.
- CC Switch compatibility has three forms: legacy `auth.json.OPENAI_API_KEY`; enhanced official-auth-preservation with provider-scoped `experimental_bearer_token`; and loopback takeover using `PROXY_MANAGED`.
- `PROXY_MANAGED` is accepted only when the parsed hostname is exactly `localhost`, `127.0.0.1`, or `::1`. A local proxy must forward `/v1/images/generations`; otherwise image generation cannot work even if other Codex requests do.

## Workflow

1. Resolve `scripts/generate_image.py` from this Skill.
2. Choose the requested output path, or use `output/imagegen/output.png`.
3. Run with `--source auto` by default. Pass `--codex-home` only when the user selects a non-default Codex home; use `--source env` only for an explicit legacy environment route.
4. Resolve the selected route without exposing values, then run with the requested prompt and optional model, size, quality, output format, and output path.
5. Sanitized summary fields are exactly and only: `source`, `provider`, `credential_source`, `host`, `model`, `output`, `output_format`, `quality`, and `size`. `key`, `prompt`, `config`, OAuth data, and token values are never included.

Use `--dry-run` to validate routing and parameters without a network request. It does not construct an SDK client and never reveals credentials.
