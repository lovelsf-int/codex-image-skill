from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable, Mapping, Sequence, TextIO
from urllib.parse import urlsplit


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_FORMAT = "png"
DEFAULT_OUT = "output/imagegen/output.png"


class ConfigError(RuntimeError):
    """Raised when local routing or request configuration is invalid."""


class ResponseError(RuntimeError):
    """Raised when a provider response cannot be saved as an image."""


@dataclass(frozen=True)
class ApiConfig:
    api_key: str
    base_url: str
    host: str


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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def validate_base_url(value: str | None) -> str:
    normalized = value.strip() if value else ""
    if not normalized:
        raise ConfigError(
            "OPENAI_BASE_URL is required; refusing to fall back to api.openai.com"
        )

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("OPENAI_BASE_URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError(
            "OPENAI_BASE_URL must not contain credentials, query parameters, or fragments"
        )
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigError("OPENAI_BASE_URL contains an invalid port") from exc
    return normalized.rstrip("/") + "/"


def load_config(
    env: Mapping[str, str] | None = None, *, dry_run: bool
) -> ApiConfig:
    values = os.environ if env is None else env
    base_url = validate_base_url(values.get("OPENAI_BASE_URL"))
    api_key = values.get("OPENAI_API_KEY", "")
    if not api_key and not dry_run:
        raise ConfigError("OPENAI_API_KEY is required for live generation")
    return ApiConfig(
        api_key=api_key,
        base_url=base_url,
        host=urlsplit(base_url).hostname or "",
    )


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
    config: ApiConfig, payload: Mapping[str, object], out: Path
) -> str:
    return json.dumps(
        {
            "host": config.host,
            "model": payload["model"],
            "output": str(out),
            "output_format": payload["output_format"],
            "quality": payload["quality"],
            "size": payload["size"],
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def create_client(config: ApiConfig) -> object:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigError(
            "openai SDK is not installed; run: python -m pip install openai>=2.15.0,<3"
        ) from exc
    return OpenAI(api_key=config.api_key, base_url=config.base_url)


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
    client_factory: Callable[[ApiConfig], object] = create_client,
    stdout: TextIO = sys.stdout,
) -> Path | None:
    config = load_config(env, dry_run=args.dry_run)
    payload = build_payload(args)
    out = Path(args.out)
    summary = sanitized_summary(config, payload, out)

    if args.dry_run:
        print(summary, file=stdout)
        return None

    client = client_factory(config)
    response = client.images.generate(**payload)
    atomic_write(out, decode_first_image(response), force=args.force)
    print(summary, file=stdout)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    try:
        run(parse_args(argv))
        return 0
    except (ConfigError, ResponseError, FileExistsError) as exc:
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
            message = "provider does not expose the requested image endpoint or model"
        elif status == 429:
            message = "provider rate limit or quota exceeded"
        else:
            message = f"provider request failed: {type(exc).__name__}"
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
