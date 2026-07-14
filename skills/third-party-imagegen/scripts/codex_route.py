from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
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
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
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
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise RouteInvalid("image API base URL is malformed") from exc
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


AuthCommandRunner = Callable[[Mapping[str, Any]], str]


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
    if api_key:
        validate_proxy_placeholder(api_key, host)
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
