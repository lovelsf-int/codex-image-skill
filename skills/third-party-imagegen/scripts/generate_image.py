from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable, Mapping, Protocol, Sequence, TextIO

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


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_FORMAT = "png"
DEFAULT_OUT = "output/imagegen/output.png"


class ConfigError(RuntimeError):
    """Raised when local routing or request configuration is invalid."""


class ResponseError(RuntimeError):
    """Raised when a provider response cannot be saved as an image."""


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one image through a required custom OpenAI-compatible endpoint."
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument(
        "--quality",
        choices=("low", "medium", "high", "auto"),
        default=DEFAULT_QUALITY,
    )
    parser.add_argument(
        "--output-format",
        choices=("png", "jpeg", "webp"),
        default=DEFAULT_FORMAT,
    )
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--source",
        choices=("auto", "codex", "env"),
        default="auto",
    )
    parser.add_argument("--codex-home")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def build_payload(args: argparse.Namespace) -> dict[str, object]:
    if not args.model.startswith("gpt-image-"):
        raise ConfigError("model must start with gpt-image-")
    if not args.prompt.strip():
        raise ConfigError("prompt must not be empty")
    return {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
    }


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


def create_client(route: ResolvedRoute) -> object:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigError(
            "openai SDK is not installed; run: python -m pip install openai>=2.15.0,<3"
        ) from exc
    return OpenAI(api_key=route.api_key, base_url=route.base_url)


def decode_first_image(response: object) -> bytes:
    data = getattr(response, "data", None)
    encoded = getattr(data[0], "b64_json", None) if data else None
    if not encoded:
        raise ResponseError(
            "provider response must contain data[0].b64_json; URL-only responses are unsupported"
        )
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ResponseError("provider returned invalid base64 image data") from exc


def atomic_write(path: Path, content: bytes, *, force: bool) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"output already exists: {path}")

    handle = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temp_path, path)
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError as exc:
                raise FileExistsError(f"output already exists: {path}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


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


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    route_resolver: RouteResolver = resolve_route,
    client_factory: Callable[[ResolvedRoute], object] = create_client,
    stdout: TextIO = sys.stdout,
) -> int:
    try:
        run(
            parse_args(argv),
            env=env,
            route_resolver=route_resolver,
            client_factory=client_factory,
            stdout=stdout,
        )
        return 0
    except (ConfigError, RouteError, ResponseError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not write output: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in {401, 403}:
            message = "provider authentication failed; check the token service key"
        elif status == 404:
            message = (
                "current provider does not expose the requested image endpoint or model; "
                "a CC Switch local route must forward /images/generations"
            )
        elif status == 429:
            message = "provider rate limit or quota exceeded"
        else:
            message = f"provider request failed: {type(exc).__name__}"
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
