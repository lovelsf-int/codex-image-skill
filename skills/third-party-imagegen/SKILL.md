---
name: third-party-imagegen
description: Use when generating images through a third-party OpenAI-compatible token service, custom OPENAI_BASE_URL endpoint, API-key image billing, or a gpt-image-2 request that must not use Codex built-in image generation.
---

# Third-Party Image Generation

Generate one image through the bundled API client and a user-configured third-party service.

## Required Routing

- Never use the built-in `image_gen` tool for this workflow.
- `OPENAI_BASE_URL` is mandatory. Stop on a missing or invalid value; never fall back to `api.openai.com`.
- `OPENAI_API_KEY` is required for live calls. Never request, print, or place it in chat.
- Use `gpt-image-2` unless the user explicitly requests another model beginning with `gpt-image-`.
- This Skill supports single-image generation only. Do not add editing, masks, batch requests, or transparency-specific flows.

## Workflow

1. Resolve `scripts/generate_image.py` from this Skill.
2. Choose the requested output path, or use `output/imagegen/output.png`.
3. Check environment-variable presence only, without exposing values.
4. Run the script with the requested prompt and optional model, size, quality, output format, and output path.
5. Report the sanitized API host, selected model, and saved path.

Use `--dry-run` to validate routing and parameters without a network request. It still requires `OPENAI_BASE_URL`, but does not require a key or construct an SDK client.
