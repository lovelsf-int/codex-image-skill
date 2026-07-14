# Danko ImageGen MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local stdio MCP server that exposes secure DankoToken text-to-image and image-to-image tools, then integrate that tool-first workflow into the existing Skill.

**Architecture:** Keep the generic Codex route resolver unchanged. Add a Danko-specific core module that resolves a dedicated API key first and a complete active Codex Danko route second, validates image paths, invokes the OpenAI-compatible Images API, and returns image bytes. Add a thin MCP adapter that converts core results into direct image content plus sanitized text.

**Tech Stack:** Python 3.10+, MCP Python SDK over stdio, existing OpenAI SDK, unittest, GitHub Actions.

## Global Constraints

- Default endpoint: `https://dankotoken.com/v1`.
- Dedicated credentials: `DANKOTOKEN_API_KEY` and optional `DANKOTOKEN_BASE_URL`.
- Priority: dedicated complete route first; otherwise active Codex route only if hostname is exactly `dankotoken.com` or `www.dankotoken.com`.
- Never mix a URL and key from different sources; never read OAuth fields or the CC Switch database; never fall back to `api.openai.com`.
- Defaults: `gpt-image-2`, `1024x1024`, `medium`, and `png`.
- Text-to-image uses `/v1/images/generations`; image-to-image uses `/v1/images/edits` with multipart local files.
- Image-to-image accepts only regular `.png`, `.jpg`, `.jpeg`, or `.webp` files inside the MCP working directory.
- Return MCP image content and secret-free text; atomically write the same bytes under `output/danko-imagegen/` by default.
- Do not overwrite files silently.
- Do not run Python, tests, package installation, or real image calls locally. GitHub Actions is the execution verifier.

---

## File Structure

- Create `skills/third-party-imagegen/mcp_server/danko_imagegen_core.py`: route policy, input/output validation, provider invocation, response decode, and atomic persistence.
- Create `skills/third-party-imagegen/mcp_server/danko_imagegen_server.py`: stdio MCP adapter exposing two tool schemas.
- Create `tests/test_danko_imagegen_core.py`: fake-client coverage for routing, file safety, output persistence, and sanitized errors.
- Create `tests/test_danko_imagegen_server.py`: tool adapter coverage with injected core functions.
- Modify `requirements.txt`: bounded MCP SDK dependency.
- Modify `skills/third-party-imagegen/SKILL.md`, `README.md`, `README.en.md`, and `tests/test_skill_contract.py`.

### Task 1: Danko Core Routing And Image Operations

**Files:**
- Create: `skills/third-party-imagegen/mcp_server/danko_imagegen_core.py`
- Test: `tests/test_danko_imagegen_core.py`

**Interfaces:**
- Consumes: `ResolvedRoute`, `RouteError`, `resolve_codex_home`, and `resolve_route` from `skills/third-party-imagegen/scripts/codex_route.py`.
- Produces: `resolve_danko_route`, `generate_image`, `edit_image`, `ImageRequest`, `GeneratedImage`, and `DankoImageError`.

- [ ] **Step 1: Write unexecuted failing route tests**

```python
def test_dedicated_danko_key_uses_default_base_url() -> None:
    route = mod.resolve_danko_route({"DANKOTOKEN_API_KEY": "dedicated-secret"}, Path("codex"))
    self.assertEqual("https://dankotoken.com/v1/", route.base_url)

def test_codex_fallback_accepts_only_dankotoken_host() -> None:
    self.assertEqual("codex", mod.resolve_danko_route({}, danko_home).source)
    with self.assertRaises(mod.DankoImageError):
        mod.resolve_danko_route({}, non_danko_home)
```

- [ ] **Step 2: Implement value objects and coherent route resolution**

```python
@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    model: str = "gpt-image-2"
    size: str = "1024x1024"
    quality: str = "medium"
    output_format: str = "png"

@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    output_path: Path
    source: str
    host: str
    model: str
    output_format: str
```

Dedicated keys use only `DANKOTOKEN_BASE_URL` or the Danko default. Without that key, call `resolve_route("codex", ...)`, require the exact Danko hostname, and convert failures to secret-free `DankoImageError`.

- [ ] **Step 3: Write unexecuted fake-client generation, edit, and file-boundary tests**

```python
def test_generate_writes_and_returns_base64_image() -> None:
    result = mod.generate_image(request, route, fake_client, workspace)
    self.assertEqual(PNG_BYTES, result.content)

def test_edit_passes_local_image_to_images_edit() -> None:
    result = mod.edit_image(request, source_png, route, fake_client, workspace)
    fake_client.images.edit.assert_called_once()

def test_edit_rejects_path_outside_workspace() -> None:
    with self.assertRaises(mod.DankoImageError):
        mod.validate_input_image(Path("C:/outside.png"), workspace)
```

- [ ] **Step 4: Implement generation, editing, response decode, and atomic write**

```python
def generate_image(request, route, client_factory, workspace, output_path=None):
    response = client_factory(route).images.generate(**request.to_payload())
    return persist_response(response, route, request, workspace, output_path)

def edit_image(request, input_image_path, route, client_factory, workspace, output_path=None):
    image = validate_input_image(input_image_path, workspace)
    with image.open("rb") as handle:
        response = client_factory(route).images.edit(image=handle, **request.to_payload())
    return persist_response(response, route, request, workspace, output_path)
```

Reuse the existing base64 validation and atomic-write semantics through focused imports or a small extraction. Reject URL-only responses and output collisions.

- [ ] **Step 5: Static check and commit**

Run `git diff --check`; do not run tests. Commit:

```bash
git add skills/third-party-imagegen/mcp_server/danko_imagegen_core.py tests/test_danko_imagegen_core.py
git commit -m "Add Danko image MCP core"
```

### Task 2: Stdio MCP Server Adapter

**Files:**
- Create: `skills/third-party-imagegen/mcp_server/danko_imagegen_server.py`
- Test: `tests/test_danko_imagegen_server.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: Task 1 `ImageRequest`, `GeneratedImage`, `generate_image`, `edit_image`, `resolve_danko_route`, and `DankoImageError`.
- Produces: stdio MCP tools named `generate_danko_image` and `edit_danko_image`.

- [ ] **Step 1: Write unexecuted adapter tests**

```python
def test_generate_tool_returns_image_and_sanitized_text() -> None:
    content = mod.generate_danko_image("red dog", core=fake_core)
    self.assertEqual("image", content[0].type)
    self.assertNotIn("secret", content[1].text)

def test_edit_tool_rejects_non_local_input_path() -> None:
    with self.assertRaises(mod.ToolError):
        mod.edit_danko_image("change fur", "https://example.com/dog.png", core=fake_core)
```

- [ ] **Step 2: Add a bounded MCP SDK dependency and implement FastMCP**

```python
mcp = FastMCP(
    "danko-imagegen",
    instructions="Use generate_danko_image for text-to-image and edit_danko_image only with a local reference image path. Both tools write files.",
)

@mcp.tool()
def generate_danko_image(prompt: str, model: str = "gpt-image-2", ...):
    result = core.generate(...)
    return [image_content(result.content, result.output_format), text_content(result)]
```

Use the current SDK direct image-content return type. Tool wrappers obtain the working directory, resolve a route, call core, and expose only source, host, model, format, and saved path as text.

- [ ] **Step 3: Add the stdio entry point and sanitized tool errors**

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Convert route, validation, and provider failures into actionable secret-free MCP errors. Do not include the prompt, token, config contents, or raw provider response.

- [ ] **Step 4: Static check and commit**

Run `git diff --check`; do not run tests. Commit:

```bash
git add requirements.txt skills/third-party-imagegen/mcp_server/danko_imagegen_server.py tests/test_danko_imagegen_server.py
git commit -m "Expose Danko image tools over MCP"
```

### Task 3: Skill, Documentation, And Distribution Contract

**Files:**
- Modify: `skills/third-party-imagegen/SKILL.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `tests/test_skill_contract.py`

**Interfaces:**
- Consumes: Task 2 server path, tool names, environment-variable policy, and default values.
- Produces: installable documentation that directs Codex to use the MCP tools securely.

- [ ] **Step 1: Write unexecuted static contract tests**

```python
def test_skill_describes_danko_mcp_tools_and_security_policy(self) -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    self.assertIn("generate_danko_image", skill)
    self.assertIn("edit_danko_image", skill)
    self.assertIn("DANKOTOKEN_API_KEY", skill)
    self.assertIn("api.openai.com", skill)
```

- [ ] **Step 2: Update Skill with MCP-first instructions**

Document MCP tool preference with CLI compatibility fallback. State both tools write files, editing requires a local workspace image, and secrets come only from forwarded dedicated variables or a coherent active Codex Danko route.

- [ ] **Step 3: Update Chinese and English README files**

Add equivalent sections with this secret-free shape:

```toml
[mcp_servers.danko_imagegen]
command = "python"
args = ["/absolute/path/to/danko_imagegen_server.py"]
cwd = "/absolute/path/to/your/workspace"
env_vars = ["DANKOTOKEN_API_KEY", "DANKOTOKEN_BASE_URL"]
default_tools_approval_mode = "writes"
```

Document environment-first priority, exact Danko host fallback, restart after persistent Windows variable changes, and examples for both tools.

- [ ] **Step 4: Static check and commit**

Run `git diff --check`; do not run tests. Commit:

```bash
git add skills/third-party-imagegen/SKILL.md README.md README.en.md tests/test_skill_contract.py
git commit -m "Document Danko image MCP workflow"
```

### Task 4: Whole-Branch Review, Push, And Remote CI

**Files:**
- Review: all changes since `093e1e1`.

**Interfaces:**
- Consumes: Tasks 1-3 and the design specification.
- Produces: reviewed, pushed branch and remote Python matrix evidence.

- [ ] **Step 1: Produce a full review package and obtain static approval**

Review route coherence, exact Danko host fallback, direct image return, local input containment, multipart editing, secret redaction, documentation parity, and unexecuted-local-test policy.

- [ ] **Step 2: Push only after approval**

Push `codex/danko-imagegen-mcp`, fast-forward `main`, and push `main` without a merge commit.

- [ ] **Step 3: Verify GitHub Actions remotely**

Inspect the run for the pushed main SHA. All Python matrix jobs must pass. If a job fails, diagnose from remote logs, apply the smallest scoped fix, push, and inspect a new run.
