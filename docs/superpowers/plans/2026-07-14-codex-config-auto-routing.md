# Codex Provider Auto-Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `third-party-imagegen` automatically reuse the active Codex or CC Switch API route while preserving strict no-fallback behavior and the existing environment-variable workflow.

**Architecture:** Add a focused `codex_route.py` module that resolves one coherent `ResolvedRoute` from Codex live configuration or the legacy environment pair. Keep image request construction and file output in `generate_image.py`; it consumes the resolved route and never handles Codex credential storage details.

**Tech Stack:** Python 3.10+, `tomllib`/conditional `tomli`, OpenAI Python SDK 2.x, `unittest`, GitHub Actions.

## Global Constraints

- Default image model remains exactly `gpt-image-2`.
- Supported model overrides must begin with `gpt-image-`.
- Never silently default or fall back to `api.openai.com`.
- Never print or persist an API key, OAuth token, auth-command output, Authorization header, prompt, or full configuration.
- Never use Codex OAuth `tokens`, `access_token`, or `refresh_token` as an image API credential.
- Never read the CC Switch SQLite database or bypass its live local proxy.
- `PROXY_MANAGED` is valid only with `localhost`, `127.0.0.1`, or `::1`.
- A route is selected as a complete source; never combine a Codex URL with an environment key or the reverse.
- Existing `--prompt`, `--model`, `--size`, `--quality`, `--output-format`, `--out`, `--dry-run`, and `--force` behavior remains supported.
- Python 3.10 remains the minimum version.
- Tests must remain offline and must not make paid API calls.
- Per the user's explicit instruction, do not run local tests. Push the implementation and let GitHub Actions execute the offline suite.

---

## File Map

- Create `skills/third-party-imagegen/scripts/codex_route.py`: Codex home discovery, TOML/JSON parsing, provider selection, credential resolution, CC Switch compatibility, and route-source selection.
- Modify `skills/third-party-imagegen/scripts/generate_image.py`: new CLI options, route consumption, sanitized summary, and route-aware endpoint errors.
- Create `tests/test_codex_route.py`: offline route resolver fixtures and security cases.
- Modify `tests/test_generate_image.py`: integration coverage for `--source`, route injection, summaries, and backward-compatible env mode.
- Modify `tests/test_skill_contract.py`: documentation and metadata contract for Codex-follow and CC Switch support.
- Modify `skills/third-party-imagegen/SKILL.md`: default Codex-follow workflow and explicit source selection.
- Modify `README.md`: Codex native provider, DankoToken, CC Switch legacy/enhanced/proxy, and troubleshooting instructions.
- Modify `requirements.txt`: conditional TOML parser for Python 3.10.
- Modify `.github/workflows/test.yml`: retain Python 3.10/3.12/3.13 offline test matrix.

---

### Task 1: Core Codex Route Resolver

**Files:**
- Create: `skills/third-party-imagegen/scripts/codex_route.py`
- Create: `tests/test_codex_route.py`

**Interfaces:**
- Produces: `RouteError`, `RouteUnavailable`, `RouteInvalid`, `ResolvedRoute`, `resolve_codex_home()`, `resolve_codex_route()`, `resolve_env_route()`, and `resolve_route()`.
- Consumes later: `generate_image.py` imports `ResolvedRoute`, `RouteError`, and `resolve_route`.

- [ ] **Step 1: Add test loading and standard-provider fixtures**

Create `tests/test_codex_route.py` with a local module loader and helpers:

```python
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "skills" / "third-party-imagegen" / "scripts" / "codex_route.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("third_party_codex_route", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_codex_files(home: Path, config: str, auth: dict | None = None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(config, encoding="utf-8")
    if auth is not None:
        (home / "auth.json").write_text(json.dumps(auth), encoding="utf-8")
```

Add `CodexProviderTests` covering:

```python
def test_standard_provider_uses_active_base_url_and_env_key(self):
    with TemporaryDirectory() as directory:
        home = Path(directory)
        write_codex_files(
            home,
            """
model_provider = "dankotoken"
[model_providers.dankotoken]
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
""",
        )
        route = self.mod.resolve_codex_route(
            home, {"DANKOTOKEN_API_KEY": "secret"}, dry_run=False
        )
        self.assertEqual(route.base_url, "https://dankotoken.com/v1/")
        self.assertEqual(route.api_key, "secret")
        self.assertEqual(route.provider_id, "dankotoken")
        self.assertEqual(route.credential_source, "provider.env_key")

def test_non_active_provider_is_never_used(self):
    with TemporaryDirectory() as directory:
        home = Path(directory)
        write_codex_files(
            home,
            """
model_provider = "active"
[model_providers.active]
name = "Missing URL"
[model_providers.stale]
base_url = "https://stale.example/v1"
experimental_bearer_token = "stale-secret"
""",
        )
        with self.assertRaises(self.mod.RouteInvalid):
            self.mod.resolve_codex_route(home, {}, dry_run=False)
```

Add tests for:

- `--codex-home` value winning over `CODEX_HOME`.
- `CODEX_HOME` winning over `~/.codex`.
- `openai_base_url` being used only when provider is absent or `openai`.
- malformed TOML raising `RouteInvalid`, not `RouteUnavailable`.
- dry-run allowing a missing credential but still requiring a valid URL.

- [ ] **Step 2: Do not run the local suite**

Per the user's instruction, record in the task report:

```text
Local tests intentionally not run. The new tests are offline and will run in GitHub Actions after push.
```

- [ ] **Step 3: Implement the resolver types and safe file parsing**

Create `codex_route.py` with these exact public types:

```python
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


PROXY_PLACEHOLDER = "PROXY_MANAGED"
DEFAULT_CODEX_HOME = Path.home() / ".codex"


class RouteError(RuntimeError):
    pass


class RouteUnavailable(RouteError):
    pass


class RouteInvalid(RouteError):
    pass


@dataclass(frozen=True)
class ResolvedRoute:
    api_key: str
    base_url: str
    host: str
    source: str
    provider_id: str | None
    credential_source: str
    codex_home: Path | None
```

Implement:

```python
def resolve_codex_home(
    cli_value: str | None, env: Mapping[str, str]
) -> Path:
    raw = cli_value or env.get("CODEX_HOME")
    return Path(raw).expanduser() if raw else DEFAULT_CODEX_HOME


def load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise RouteUnavailable("Codex config.toml was not found") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RouteInvalid("Codex config.toml could not be read or parsed") from exc
    if not isinstance(data, dict):
        raise RouteInvalid("Codex config.toml must contain a TOML table")
    return data


def load_auth_api_key(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteInvalid("Codex auth.json could not be read or parsed") from exc
    if not isinstance(data, dict):
        raise RouteInvalid("Codex auth.json must contain a JSON object")
    value = data.get("OPENAI_API_KEY")
    return value.strip() if isinstance(value, str) else ""


def validate_base_url(value: str | None) -> str:
    normalized = value.strip() if value else ""
    if not normalized:
        raise RouteUnavailable("image API base URL is required")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RouteInvalid("image API base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RouteInvalid(
            "image API base URL must not contain credentials, query, or fragment"
        )
    try:
        parsed.port
    except ValueError as exc:
        raise RouteInvalid("image API base URL contains an invalid port") from exc
    return normalized.rstrip("/") + "/"
```

`load_auth_api_key` must never traverse other auth fields.

- [ ] **Step 4: Implement provider-scoped URL resolution**

Add:

```python
def active_provider(
    config: Mapping[str, Any],
) -> tuple[str | None, Mapping[str, Any]]:
    raw_id = config.get("model_provider")
    provider_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None
    providers = config.get("model_providers")
    if provider_id is None:
        return None, {}
    if provider_id == "openai":
        return provider_id, {}
    if not isinstance(providers, Mapping):
        raise RouteInvalid("active Codex model_provider has no provider table")
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        raise RouteInvalid("active Codex model_provider is not configured")
    return provider_id, provider


def resolve_codex_base_url(
    config: Mapping[str, Any],
    provider_id: str | None,
    provider: Mapping[str, Any],
) -> str:
    if provider_id is not None:
        value = provider.get("base_url")
        if isinstance(value, str) and value.strip():
            return validate_base_url(value)
        if provider_id != "openai":
            raise RouteInvalid("active Codex provider is missing base_url")

    value = config.get("openai_base_url")
    if isinstance(value, str) and value.strip():
        return validate_base_url(value)

    if provider_id is None:
        legacy = config.get("base_url")
        if isinstance(legacy, str) and legacy.strip():
            return validate_base_url(legacy)

    raise RouteUnavailable("current Codex route has no image API base URL")
```

Use the existing strict URL rules: absolute HTTP(S), hostname required, no embedded credentials, query, or fragment, and normalized trailing slash.

- [ ] **Step 5: Implement coherent source selection**

Add signatures:

```python
AuthCommandRunner = Callable[[Mapping[str, Any]], str]


def run_auth_command(auth: Mapping[str, Any]) -> str:
    raise RouteUnavailable("provider auth.command support is not available")


def provider_credential(
    config: Mapping[str, Any],
    provider: Mapping[str, Any],
    auth_path: Path,
    env: Mapping[str, str],
    auth_command_runner: AuthCommandRunner,
) -> tuple[str, str]:
    env_key = provider.get("env_key")
    if isinstance(env_key, str) and env_key.strip():
        value = env.get(env_key.strip(), "").strip()
        if value:
            return value, "provider.env_key"
    return "", "none"


def resolve_codex_route(
    codex_home: Path,
    env: Mapping[str, str],
    *,
    dry_run: bool,
    auth_command_runner: AuthCommandRunner = run_auth_command,
) -> ResolvedRoute:
    config = load_toml(codex_home / "config.toml")
    provider_id, provider = active_provider(config)
    base_url = resolve_codex_base_url(config, provider_id, provider)
    api_key, credential_source = provider_credential(
        config,
        provider,
        codex_home / "auth.json",
        env,
        auth_command_runner,
    )
    if not api_key and not dry_run:
        raise RouteUnavailable("current Codex route has no usable API credential")
    host = urlsplit(base_url).hostname or ""
    return ResolvedRoute(
        api_key=api_key,
        base_url=base_url,
        host=host,
        source="codex",
        provider_id=provider_id,
        credential_source=credential_source,
        codex_home=codex_home,
    )


def resolve_env_route(
    env: Mapping[str, str], *, dry_run: bool
) -> ResolvedRoute:
    base_url = validate_base_url(env.get("OPENAI_BASE_URL"))
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key and not dry_run:
        raise RouteUnavailable("OPENAI_API_KEY is required for env source")
    return ResolvedRoute(
        api_key=api_key,
        base_url=base_url,
        host=urlsplit(base_url).hostname or "",
        source="env",
        provider_id=None,
        credential_source="OPENAI_API_KEY" if api_key else "none",
        codex_home=None,
    )


def resolve_route(
    source: str,
    *,
    codex_home: Path,
    env: Mapping[str, str],
    dry_run: bool,
    auth_command_runner: AuthCommandRunner = run_auth_command,
) -> ResolvedRoute:
    if source == "codex":
        return resolve_codex_route(
            codex_home,
            env,
            dry_run=dry_run,
            auth_command_runner=auth_command_runner,
        )
    if source == "env":
        return resolve_env_route(env, dry_run=dry_run)
    if source != "auto":
        raise RouteInvalid("source must be auto, codex, or env")
    try:
        return resolve_codex_route(
            codex_home,
            env,
            dry_run=dry_run,
            auth_command_runner=auth_command_runner,
        )
    except RouteUnavailable:
        return resolve_env_route(env, dry_run=dry_run)
```

When source is `auto`, `resolve_route` may catch only `RouteUnavailable`.
It must never hide `RouteInvalid`; unsafe or malformed Codex configuration
must fail visibly.

`resolve_env_route` requires `OPENAI_BASE_URL`, and requires
`OPENAI_API_KEY` only for live mode. It returns `source="env"` and
`credential_source="OPENAI_API_KEY"`.

- [ ] **Step 6: Commit Task 1**

```bash
git add skills/third-party-imagegen/scripts/codex_route.py tests/test_codex_route.py
git commit -m "Add Codex provider route resolver"
```

---

### Task 2: CC Switch Credential Compatibility

**Files:**
- Modify: `skills/third-party-imagegen/scripts/codex_route.py`
- Modify: `tests/test_codex_route.py`

**Interfaces:**
- Consumes: `ResolvedRoute` and provider parsing from Task 1.
- Produces: CC Switch legacy, enhanced, and proxy-compatible credential resolution.

- [ ] **Step 1: Add offline CC Switch fixtures**

Add tests with these exact cases:

```python
def test_cc_switch_enhanced_mode_prefers_provider_token(self):
    config = """
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
experimental_bearer_token = "provider-secret"
requires_openai_auth = true
"""
    auth = {"tokens": {"access_token": "oauth-secret"}}
    # Assert provider-secret is selected and oauth-secret never appears.


def test_cc_switch_legacy_mode_reads_only_auth_json_api_key(self):
    config = """
model_provider = "custom"
[model_providers.custom]
base_url = "https://relay.example/v1"
"""
    auth = {
        "OPENAI_API_KEY": "legacy-secret",
        "tokens": {"access_token": "oauth-secret"},
    }
    # Assert legacy-secret is selected.


def test_proxy_managed_requires_loopback(self):
    # Assert http://127.0.0.1:15721/v1 succeeds.
    # Assert https://relay.example/v1 raises RouteInvalid.


def test_oauth_only_auth_json_is_not_an_api_key(self):
    # In live mode, assert RouteUnavailable.
```

Add fake-runner tests for provider `auth.command` and focused
`unittest.mock.patch` tests for `run_auth_command`: success, timeout, nonzero
exit, and empty stdout. No test may launch a real credential helper.

- [ ] **Step 2: Do not run the local suite**

Record the same local-test exception in the task report.

- [ ] **Step 3: Implement provider credential resolution**

Add:

```python
def provider_credential(
    config: Mapping[str, Any],
    provider: Mapping[str, Any],
    auth_path: Path,
    env: Mapping[str, str],
    auth_command_runner: AuthCommandRunner,
) -> tuple[str, str]:
    token = provider.get("experimental_bearer_token")
    if isinstance(token, str) and token.strip():
        return token.strip(), "provider.experimental_bearer_token"

    env_key = provider.get("env_key")
    if isinstance(env_key, str) and env_key.strip():
        value = env.get(env_key.strip(), "").strip()
        if value:
            return value, "provider.env_key"

    auth = provider.get("auth")
    if isinstance(auth, Mapping):
        value = auth_command_runner(auth)
        if value:
            return value, "provider.auth.command"

    top_level = config.get("experimental_bearer_token")
    if isinstance(top_level, str) and top_level.strip():
        return top_level.strip(), "experimental_bearer_token"

    legacy = load_auth_api_key(auth_path)
    if legacy:
        return legacy, "auth.json.OPENAI_API_KEY"

    return "", "none"
```

If `auth.command` is present together with provider token or `env_key`, the
earlier explicit source wins; do not execute the command unnecessarily.

- [ ] **Step 4: Implement command-backed auth safely**

```python
def run_auth_command(auth: Mapping[str, Any]) -> str:
    command = auth.get("command")
    args = auth.get("args", [])
    timeout_ms = auth.get("timeout_ms", 5000)
    if not isinstance(command, str) or not command.strip():
        raise RouteInvalid("provider auth.command is missing")
    if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
        raise RouteInvalid("provider auth.args must be an array")
    if not all(isinstance(item, str) for item in args):
        raise RouteInvalid("provider auth.args must contain only strings")
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise RouteInvalid("provider auth.timeout_ms must be a positive integer")
    try:
        completed = subprocess.run(
            [command, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout_ms / 1000,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RouteInvalid("provider auth command failed or timed out") from exc
    token = completed.stdout.strip()
    if completed.returncode != 0 or not token:
        raise RouteInvalid("provider auth command returned no usable credential")
    return token
```

Do not include `command`, `args`, stdout, or stderr in exceptions.

- [ ] **Step 5: Enforce the CC Switch proxy placeholder rule**

```python
def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_proxy_placeholder(api_key: str, host: str) -> None:
    if api_key == PROXY_PLACEHOLDER and not is_loopback_host(host):
        raise RouteInvalid(
            "PROXY_MANAGED is only valid for a loopback CC Switch route"
        )
```

Call this after URL and credential resolution. In dry-run, validate the rule if
a credential is present.

- [ ] **Step 6: Commit Task 2**

```bash
git add skills/third-party-imagegen/scripts/codex_route.py tests/test_codex_route.py
git commit -m "Support CC Switch Codex credentials"
```

---

### Task 3: Integrate Routing Into Image Generation

**Files:**
- Modify: `skills/third-party-imagegen/scripts/generate_image.py`
- Modify: `tests/test_generate_image.py`

**Interfaces:**
- Consumes: `ResolvedRoute`, `RouteError`, `resolve_codex_home`, and `resolve_route`.
- Preserves: `build_payload`, `decode_first_image`, `atomic_write`, and the live OpenAI SDK call.

- [ ] **Step 1: Add integration tests first**

Update the module loader so the scripts directory is temporarily available on
`sys.path`. Add tests that assert:

- default `--source` is `auto`;
- `--source codex` and `--source env` parse;
- `--codex-home` parses;
- a fake `route_resolver` feeds the exact key and URL to `client_factory`;
- sanitized summary contains `source`, `provider`, `credential_source`, and
  host, but no key;
- the existing env-only generation still works with `--source env`;
- a 404 through a loopback Codex route reports that the current CC Switch route
  may not expose `/images/generations`.

Use only fake clients and injected resolver functions.

- [ ] **Step 2: Do not run the local suite**

Record the local-test exception in the task report.

- [ ] **Step 3: Add imports and CLI options**

Use a package/direct-script compatible import:

```python
try:
    from .codex_route import (
        ResolvedRoute,
        RouteError,
        resolve_codex_home,
        resolve_route,
    )
except ImportError:
    from codex_route import (
        ResolvedRoute,
        RouteError,
        resolve_codex_home,
        resolve_route,
    )
```

Add:

```python
parser.add_argument(
    "--source",
    choices=("auto", "codex", "env"),
    default="auto",
)
parser.add_argument("--codex-home")
```

Remove `ApiConfig`, `load_config`, and duplicate URL validation from
`generate_image.py`.

- [ ] **Step 4: Consume one resolved route**

Update signatures:

```python
from typing import Protocol


class RouteResolver(Protocol):
    def __call__(
        self,
        source: str,
        *,
        codex_home: Path,
        env: Mapping[str, str],
        dry_run: bool,
    ) -> ResolvedRoute:
        pass


def create_client(route: ResolvedRoute) -> object:
    from openai import OpenAI
    return OpenAI(api_key=route.api_key, base_url=route.base_url)


def sanitized_summary(
    route: ResolvedRoute, payload: Mapping[str, object], out: Path
) -> str:
    return json.dumps(
        {
            "credential_source": route.credential_source,
            "host": route.host,
            "model": payload["model"],
            "output": str(out),
            "output_format": payload["output_format"],
            "provider": route.provider_id,
            "quality": payload["quality"],
            "size": payload["size"],
            "source": route.source,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def run(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    route_resolver: RouteResolver = resolve_route,
    client_factory: Callable[[ResolvedRoute], object] = create_client,
    stdout: TextIO = sys.stdout,
) -> Path | None:
    values = os.environ if env is None else env
    codex_home = resolve_codex_home(args.codex_home, values)
    route = route_resolver(
        args.source,
        codex_home=codex_home,
        env=values,
        dry_run=args.dry_run,
    )
    payload = build_payload(args)
    out = Path(args.out)
    summary = sanitized_summary(route, payload, out)
    if args.dry_run:
        print(summary, file=stdout)
        return None
    client = client_factory(route)
    response = client.images.generate(**payload)
    atomic_write(out, decode_first_image(response), force=args.force)
    print(summary, file=stdout)
    return out
```

Summary fields are exactly: `source`, `provider`, `credential_source`,
`host`, `model`, `output`, `output_format`, `quality`, and `size`.

- [ ] **Step 5: Update safe error messages**

Catch `RouteError` with the existing configuration error exit code. For HTTP
404, use:

```text
current provider does not expose the requested image endpoint or model; a CC Switch local route must forward /images/generations
```

Do not include exception bodies from the SDK in generic output.

- [ ] **Step 6: Commit Task 3**

```bash
git add skills/third-party-imagegen/scripts/generate_image.py tests/test_generate_image.py
git commit -m "Use active Codex route for image generation"
```

---

### Task 4: Skill Contract, Documentation, and CI

**Files:**
- Modify: `skills/third-party-imagegen/SKILL.md`
- Modify: `skills/third-party-imagegen/agents/openai.yaml`
- Modify: `README.md`
- Modify: `requirements.txt`
- Modify: `tests/test_skill_contract.py`
- Inspect: `.github/workflows/test.yml`

**Interfaces:**
- Documents the exact CLI and resolution behavior implemented by Tasks 1-3.

- [ ] **Step 1: Extend static contract tests**

Require README and Skill text to mention:

- `--source auto|codex|env`;
- `CODEX_HOME` and `--codex-home`;
- `model_provider`, `env_key`, and `experimental_bearer_token`;
- `auth.json.OPENAI_API_KEY`;
- `PROXY_MANAGED`;
- CC Switch local proxy image endpoint limitation;
- DankoToken example;
- no OAuth token use and no CC Switch database access.

The metadata description must still begin with `Use when`.

- [ ] **Step 2: Do not run the local suite**

Record the local-test exception in the task report.

- [ ] **Step 3: Update dependencies**

`requirements.txt` becomes:

```text
openai>=2.15.0,<3
tomli>=2.0.0,<3; python_version < "3.11"
```

Keep the existing CI matrix at Python 3.10, 3.12, and 3.13. Do not add secrets,
network calls, or paid API execution to CI.

- [ ] **Step 4: Update the Skill workflow**

`SKILL.md` must make Codex-follow the default:

1. Use `--source auto` unless the user explicitly selects another source.
2. Resolve the current Codex provider without exposing values.
3. Treat CC Switch live configuration as the source of truth.
4. Use `--source env` only for the legacy explicit pair.
5. Never use OAuth tokens, CC Switch database contents, or official-domain
   fallback.
6. Report only sanitized source, provider, host, model, and output path.

- [ ] **Step 5: Rewrite README configuration sections**

Add complete examples:

```toml
model_provider = "dankotoken"

[model_providers.dankotoken]
name = "DankoToken"
base_url = "https://dankotoken.com/v1"
env_key = "DANKOTOKEN_API_KEY"
wire_api = "responses"
```

Explain:

- default zero-duplicate configuration through Codex;
- CC Switch legacy mode;
- CC Switch official-auth-preservation mode;
- CC Switch localhost takeover and `PROXY_MANAGED`;
- local proxy compatibility with `/v1/images/generations`;
- explicit env fallback commands;
- dry-run output and credential safety;
- custom `CODEX_HOME`.

Do not include a real key or a URL query containing credentials.

- [ ] **Step 6: Commit Task 4**

```bash
git add README.md requirements.txt skills/third-party-imagegen/SKILL.md skills/third-party-imagegen/agents/openai.yaml tests/test_skill_contract.py .github/workflows/test.yml
git commit -m "Document Codex and CC Switch auto routing"
```

---

### Task 5: Static Review, Push, and Remote CI

**Files:**
- Review all changes from `bf7de35` to branch HEAD.
- Do not add internal review artifacts to the public repository.

**Interfaces:**
- Produces the published `main` branch update.

- [ ] **Step 1: Perform static-only security review**

Do not execute Python, tests, package installation, or API calls. Inspect the
diff and confirm:

- only the active provider is read;
- complete routes are never mixed;
- OAuth fields are ignored;
- key values cannot enter summaries or exceptions;
- `PROXY_MANAGED` is loopback-only;
- no real secrets or generated image artifacts are committed;
- README, Skill, tests, and implementation agree.

- [ ] **Step 2: Dispatch independent task review**

The reviewer must be read-only and must not run tests. Any Important or Critical
finding gets a fresh fix subagent and another static review.

- [ ] **Step 3: Push implementation branch**

```bash
git push -u origin codex/codex-config-auto-routing
```

- [ ] **Step 4: Fast-forward remote main**

After static approval, update `main` by fast-forward and push:

```bash
git switch main
git merge --ff-only codex/codex-config-auto-routing
git push origin main
```

- [ ] **Step 5: Verify remote files and CI**

Read `README.md`, `codex_route.py`, and `generate_image.py` from GitHub
`main` to confirm the push. Inspect the GitHub Actions run triggered by the
push. Do not run the suite locally.

If CI fails, inspect only the remote logs, dispatch a focused fix subagent,
commit and push the fix, and let CI rerun.

- [ ] **Step 6: Final report**

Report:

- repository URL;
- local path;
- final commit SHA;
- static-review result;
- GitHub Actions result if available;
- explicit statement that local tests and real image API calls were not run.
