# Danko ImageGen MCP Design

## Goal

Add a local stdio MCP server that exposes DankoToken text-to-image and
image-to-image generation as structured tools. The tools should feel like
native Codex image capabilities while using the user's third-party DankoToken
route.

When configured, this MCP is the intended replacement path for Codex's default
image-generation tool: the bundled Skill must direct image-generation requests
to these Danko tools instead of the built-in `image_gen` tool. It does not
modify, uninstall, or technically disable the built-in tool.

## Scope

- Add `generate_danko_image` and `edit_danko_image` MCP tools.
- Generate through the OpenAI-compatible `/v1/images/generations` endpoint.
- Edit through the OpenAI-compatible `/v1/images/edits` endpoint.
- Return the generated image to the MCP client and save the same bytes under
  the workspace.
- Update the existing Skill so it directs Codex to use the MCP tool when
  available while keeping the CLI as a compatibility fallback.
- Document installation and secure configuration in Chinese and English.

Masks, batch generation, remote HTTP MCP hosting, and provider selection beyond
DankoToken are out of scope.

## Tool Contract

The tool accepts these inputs:

- `prompt` (required)
- `model` (default: `gpt-image-2`)
- `size` (default: `1024x1024`)
- `quality` (default: `medium`)
- `output_format` (default: `png`)
- `output_path` (optional)

`edit_danko_image` accepts the same generation controls plus a required
`input_image_path`. It accepts only a local regular image file in the MCP
working tree and uploads it as multipart form data. It never fetches arbitrary
remote image URLs.

Both tools return MCP image content for direct display and a concise text result
with only the saved path plus non-secret generation metadata. With no explicit
output path, they write beneath `output/danko-imagegen/` in the MCP process
working directory. Existing files are never overwritten silently.

## Credential And Route Policy

1. If `DANKOTOKEN_API_KEY` is present, use it with
   `DANKOTOKEN_BASE_URL` or the default `https://dankotoken.com/v1`.
2. If the dedicated key is absent and `DANKOTOKEN_ALLOW_CODEX_FALLBACK=1`,
   resolve the active Codex route using the existing resolver.
3. Otherwise, stop with a secret-free configuration error that names the
   dedicated key and the explicit fallback switch.
4. Accept the Codex fallback only when its parsed host is exactly
   `dankotoken.com` or `www.dankotoken.com`.
5. After that host validation only, allow the existing Codex active-provider
   credential order, including provider auth commands and the legacy
   `auth.json.OPENAI_API_KEY` API-key field. This is an explicit
   convenience-first user choice: a stale official API key may be sent to the
   confirmed DankoToken host.
6. Reject incomplete, unsafe, or non-DankoToken fallback routes. Never mix a
   Codex URL with a dedicated key or an environment URL with a Codex key.
7. Never read OAuth fields (`tokens`, `access_token`, `refresh_token`), never
   inspect the CC Switch database, and never fall back to `api.openai.com`.

The server reads `DANKOTOKEN_API_KEY` from its inherited environment. Codex
MCP configuration should forward only named environment variables using
`env_vars`, including `DANKOTOKEN_ALLOW_CODEX_FALLBACK` only when convenience
mode is desired; the repository and Skill must not contain secret values.

The default endpoint is intentionally DankoToken-only. Users who need another
domain must set `DANKOTOKEN_BASE_URL` explicitly or modify the source default;
the MCP server does not silently treat another active Codex provider as
DankoToken.

## Components

- `mcp/danko_imagegen_server.py`: stdio MCP server and tool schemas.
- Reused route and image helpers: existing `codex_route.py` and narrowly
  extracted generation functions from `generate_image.py` where doing so avoids
  duplicated request, base64 validation, and atomic-write logic.
- `tests/test_danko_imagegen_mcp.py`: fake-client tests for both tool contracts,
  route policy, direct image output, saved bytes, multipart image editing, and
  secret-free errors.
- Existing Skill and bilingual READMEs: tool-first workflow and MCP setup.

## Error Handling And Security

- Validate tool inputs before creating a client or issuing a request.
- Translate provider failures into sanitized tool errors; do not return raw
  SDK exceptions, token values, prompt text, or configuration contents.
- Require `data[0].b64_json`; URL-only responses are unsupported.
- Verify that an image-to-image input path stays under the MCP working
  directory, is a regular file, and has an allowed image extension before
  uploading it.
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
