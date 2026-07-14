# Danko ImageGen MCP Design

## Goal

Add a local stdio MCP server that exposes DankoToken image generation as a
structured `generate_danko_image` tool. The tool should feel like a native
Codex image capability while using the user's third-party DankoToken route.

## Scope

- Add one `generate_danko_image` MCP tool.
- Generate through the OpenAI-compatible `/v1/images/generations` endpoint.
- Return the generated image to the MCP client and save the same bytes under
  the workspace.
- Update the existing Skill so it directs Codex to use the MCP tool when
  available while keeping the CLI as a compatibility fallback.
- Document installation and secure configuration in Chinese and English.

Image editing, masks, batch generation, remote HTTP MCP hosting, and provider
selection beyond DankoToken are out of scope.

## Tool Contract

The tool accepts these inputs:

- `prompt` (required)
- `model` (default: `gpt-image-2`)
- `size` (default: `1024x1024`)
- `quality` (default: `medium`)
- `output_format` (default: `png`)
- `output_path` (optional)

It returns MCP image content for direct display and a concise text result with
only the saved path plus non-secret generation metadata. With no explicit
output path, it writes beneath `output/danko-imagegen/` in the MCP process
working directory. Existing files are never overwritten silently.

## Credential And Route Policy

1. If `DANKOTOKEN_API_KEY` is present, use it with
   `DANKOTOKEN_BASE_URL` or the default `https://dankotoken.com/v1`.
2. If the dedicated key is absent, resolve the active Codex route using the
   existing resolver.
3. Accept the Codex fallback only when its parsed host is exactly
   `dankotoken.com` or `www.dankotoken.com`.
4. Reject incomplete, unsafe, or non-DankoToken fallback routes. Never mix a
   Codex URL with a dedicated key or an environment URL with a Codex key.
5. Never read OAuth fields (`tokens`, `access_token`, `refresh_token`), never
   inspect the CC Switch database, and never fall back to `api.openai.com`.

The server reads `DANKOTOKEN_API_KEY` from its inherited environment. Codex
MCP configuration should forward only named environment variables using
`env_vars`; the repository and Skill must not contain secret values.

## Components

- `mcp/danko_imagegen_server.py`: stdio MCP server and tool schema.
- Reused route and image helpers: existing `codex_route.py` and narrowly
  extracted generation functions from `generate_image.py` where doing so avoids
  duplicated request, base64 validation, and atomic-write logic.
- `tests/test_danko_imagegen_mcp.py`: fake-client tests for contract, route
  policy, direct image output, saved bytes, and secret-free errors.
- Existing Skill and bilingual READMEs: tool-first workflow and MCP setup.

## Error Handling And Security

- Validate tool inputs before creating a client or issuing a request.
- Translate provider failures into sanitized tool errors; do not return raw
  SDK exceptions, token values, prompt text, or configuration contents.
- Require `data[0].b64_json`; URL-only responses are unsupported.
- Use the existing atomic-write behavior.
- Mark the MCP tool as writing because it saves output files.

## Validation

Add offline unit coverage with fake clients and route fixtures. Do not make
real image calls. Per user preference, do not run tests locally; push the
branch and rely on the existing GitHub Actions Python matrix for execution.

## Installation Shape

The documentation will provide a `config.toml` example that starts the local
stdio server with Python and forwards `DANKOTOKEN_API_KEY` plus optional
`DANKOTOKEN_BASE_URL`. It will not place the secret in TOML.
