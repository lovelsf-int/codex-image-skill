# Root-Level Danko ImageGen Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository root directly installable as a Codex Plugin that automatically declares the existing Danko image MCP server.

**Architecture:** Keep the current Skill and Python MCP server in place. Add a root plugin manifest pointing at `./skills/` and a root MCP declaration that starts the existing server with plugin-relative paths. Extend static contract tests and bilingual documentation so Plugin installation is primary.

**Tech Stack:** Codex Plugin manifest JSON, local stdio MCP JSON, Python `unittest`, GitHub Actions.

## Global Constraints

- The repository root is the only plugin root; do not duplicate the Skill or MCP source.
- The MCP declaration starts `skills/third-party-imagegen/mcp_server/danko_imagegen_server.py` with `python` and `cwd` set to `.`.
- Forward only `DANKOTOKEN_API_KEY`, `DANKOTOKEN_BASE_URL`, and `DANKOTOKEN_ALLOW_CODEX_FALLBACK`; never store credential values.
- Preserve the explicit fallback gate and the statement that the plugin does not disable Codex's built-in image tool.
- Do not run local Python tests, package installation, or image API calls. GitHub Actions is the test environment.

---

### Task 1: Add the Root Plugin and MCP Declarations

**Files:**
- Create: `.codex-plugin/plugin.json`
- Create: `.mcp.json`
- Modify: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes: `skills/third-party-imagegen/mcp_server/danko_imagegen_server.py`
- Produces: `danko-imagegen`, one local stdio MCP server, and the existing Skill.

- [ ] **Step 1: Add static contract tests before the declarations**

Parse both root JSON files. Assert `manifest["name"] == "danko-imagegen"`, `manifest["skills"] == "./skills/"`, `manifest["mcpServers"] == "./.mcp.json"`, and exactly one `mcpServers["danko-imagegen"]` entry. Assert that entry has `command` `python`, `args` equal to `["./skills/third-party-imagegen/mcp_server/danko_imagegen_server.py"]`, `cwd` equal to `.`, and the exact three-variable `env_vars` list from Global Constraints.

- [ ] **Step 2: Create `.codex-plugin/plugin.json`**

Declare `name` `danko-imagegen`, version `0.1.0`, repository URLs for `https://github.com/lovelsf-int/codex-image-skill`, MIT license, `skills` `./skills/`, and `mcpServers` `./.mcp.json`. Include valid interface metadata: display name `Danko ImageGen`, category `Productivity`, `Interactive` and `Write` capabilities, and at most two short starter prompts.

- [ ] **Step 3: Create `.mcp.json`**

Write this exact server declaration:

```json
{"mcpServers":{"danko-imagegen":{"command":"python","args":["./skills/third-party-imagegen/mcp_server/danko_imagegen_server.py"],"cwd":".","env_vars":["DANKOTOKEN_API_KEY","DANKOTOKEN_BASE_URL","DANKOTOKEN_ALLOW_CODEX_FALLBACK"]}}}
```

- [ ] **Step 4: Static validation and commit**

Run `git diff --check` only. Do not run local Python tests. Commit with `git commit -m "Package Danko image MCP as a plugin"`.

### Task 2: Make Plugin Installation the Documented Path

**Files:**
- Modify: `README.en.md`
- Modify: `README.md`
- Modify: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes: root Plugin and MCP declarations from Task 1.
- Produces: bilingual installation directions that require Plugin installation and environment configuration only.

- [ ] **Step 1: Add static documentation assertions**

Require both READMEs to contain `danko-imagegen`, `.codex-plugin/plugin.json`, `.mcp.json`, `DANKOTOKEN_API_KEY`, and wording that manual MCP TOML is a compatibility option rather than the primary path.

- [ ] **Step 2: Update both READMEs**

Lead with Plugin installation from this repository. State that installing the Plugin automatically registers the local MCP server, while `DANKOTOKEN_API_KEY` remains an external environment setting. Retain manual TOML only under a compatibility heading. Keep the explicit `DANKOTOKEN_ALLOW_CODEX_FALLBACK=1` rule and the statement that the Plugin does not technically disable or remove Codex's built-in image tool.

- [ ] **Step 3: Static validation and commit**

Run `git diff --check` only. Do not run local Python tests. Commit with `git commit -m "Document Danko plugin installation"`.

### Task 3: Remote Verification and Release

**Files:**
- Verify: `.github/workflows/test.yml`

**Interfaces:**
- Consumes: the Plugin package and static contracts.
- Produces: pushed `main` with GitHub Actions results for Python 3.10, 3.12, and 3.13.

- [ ] **Step 1: Inspect scope**

Run `git status --short` and `git diff --check HEAD~2..HEAD`. Confirm only plugin metadata, MCP configuration, documentation, and contract-test changes.

- [ ] **Step 2: Push without local tests**

Run `git -c credential.interactive=never -c http.version=HTTP/1.1 push origin main`.

- [ ] **Step 3: Verify GitHub Actions**

Wait for the remote `python -m unittest discover -s tests -v` matrix to pass on Python 3.10, 3.12, and 3.13. Do not execute it locally.

## Self-Review

- Task 1 covers the root manifest and automatic MCP registration.
- Task 2 covers the Plugin-first user journey and all credential boundaries.
- Task 3 covers the user's remote-only test requirement.
- Manifest name, MCP server name, and environment-variable names are consistent across all tasks.
