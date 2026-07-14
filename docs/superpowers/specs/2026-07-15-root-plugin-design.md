# Root-Level Danko ImageGen Plugin Design

## Goal

Package this repository as a directly installable Codex Plugin so users can
install one artifact that exposes the existing Danko image MCP tools and the
associated Skill. Users should no longer need to create an MCP server entry by
hand.

## Scope

The repository root becomes the plugin root. The existing
`skills/third-party-imagegen` directory remains the single source of the Skill,
MCP server, and supporting Python code. The plugin does not duplicate or move
the implementation.

Add these root files:

- `.codex-plugin/plugin.json`: valid plugin metadata with `skills` and
  `mcpServers` references.
- `.mcp.json`: registers one local `danko-imagegen` stdio server and starts the
  existing `danko_imagegen_server.py` from the plugin root.

The MCP configuration forwards only credential variable names:

- `DANKOTOKEN_API_KEY`
- `DANKOTOKEN_BASE_URL`
- `DANKOTOKEN_ALLOW_CODEX_FALLBACK`

No secret values are committed to the repository or plugin manifest.

## User Experience

After the plugin is installed, Codex discovers `generate_danko_image` and
`edit_danko_image` through the plugin's MCP declaration. The user configures a
dedicated `DANKOTOKEN_API_KEY` in the host environment. If they intentionally
want to reuse the active Codex Danko route instead, they set
`DANKOTOKEN_ALLOW_CODEX_FALLBACK=1`.

The plugin is the preferred user-owned image workflow, but it does not disable,
remove, or intercept Codex's built-in image tool.

## Documentation and Validation

The bilingual READMEs will lead with Plugin installation and identify direct
MCP configuration as a compatibility option. Contract tests will statically
verify manifest shape, the MCP server declaration, relative paths, the three
forwarded environment-variable names, and the documentation language.

No local Python test execution, package installation, or real image API request
is part of this work. GitHub Actions remains the test execution environment.
