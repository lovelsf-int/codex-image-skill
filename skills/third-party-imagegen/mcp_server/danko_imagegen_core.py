from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Callable, Mapping
from urllib.parse import urlsplit

try:
    from ..scripts.codex_route import (
        ResolvedRoute,
        RouteError,
        active_provider,
        load_toml,
        provider_credential,
        resolve_codex_home,
        resolve_codex_base_url,
        run_auth_command,
        validate_base_url,
        validate_proxy_placeholder,
    )
    from ..scripts.generate_image import ResponseError, atomic_write, decode_first_image
except ImportError:
    scripts_directory = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_directory not in sys.path:
        sys.path.insert(0, scripts_directory)
    from codex_route import (
        ResolvedRoute,
        RouteError,
        active_provider,
        load_toml,
        provider_credential,
        resolve_codex_home,
        resolve_codex_base_url,
        run_auth_command,
        validate_base_url,
        validate_proxy_placeholder,
    )
    from generate_image import ResponseError, atomic_write, decode_first_image


DEFAULT_DANKO_BASE_URL = "https://dankotoken.com/v1/"
DANKO_HOSTS = frozenset({"dankotoken.com", "www.dankotoken.com"})
DEFAULT_OUTPUT_DIRECTORY = Path("output") / "danko-imagegen"
SUPPORTED_QUALITIES = frozenset({"low", "medium", "high", "auto"})
SUPPORTED_OUTPUT_FORMATS = frozenset({"png", "jpeg", "webp"})
SUPPORTED_EDIT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
SIZE_PATTERN = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")


class DankoImageError(RuntimeError):
    """Raised when a Danko image request cannot be routed or persisted safely."""


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    model: str = "gpt-image-2"
    size: str = "1024x1024"
    quality: str = "medium"
    output_format: str = "png"

    def to_payload(self) -> dict[str, str]:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise DankoImageError("image prompt must not be empty")
        if not isinstance(self.model, str) or not self.model.startswith(
            "gpt-image-"
        ):
            raise DankoImageError("image model must start with gpt-image-")
        if not isinstance(self.size, str) or (
            self.size != "auto" and SIZE_PATTERN.fullmatch(self.size) is None
        ):
            raise DankoImageError(
                "image size must be auto or use positive WIDTHxHEIGHT values"
            )
        if (
            not isinstance(self.quality, str)
            or self.quality not in SUPPORTED_QUALITIES
        ):
            raise DankoImageError("image quality is unsupported")
        if (
            not isinstance(self.output_format, str)
            or self.output_format not in SUPPORTED_OUTPUT_FORMATS
        ):
            raise DankoImageError("image output format is unsupported")
        return {
            "model": self.model,
            "prompt": self.prompt,
            "size": self.size,
            "quality": self.quality,
            "output_format": self.output_format,
        }


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    output_path: Path
    source: str
    host: str
    model: str
    output_format: str


def resolve_danko_route(
    env: Mapping[str, str], codex_home: Path | None = None
) -> ResolvedRoute:
    """Resolve a dedicated Danko credential or a host-pinned Codex route."""
    api_key = env.get("DANKOTOKEN_API_KEY", "").strip()
    if api_key:
        try:
            base_url = validate_base_url(
                env.get("DANKOTOKEN_BASE_URL") or DEFAULT_DANKO_BASE_URL
            )
        except RouteError:
            raise DankoImageError("Danko image base URL is invalid") from None
        return ResolvedRoute(
            api_key=api_key,
            base_url=base_url,
            host=urlsplit(base_url).hostname or "",
            source="danko",
            provider_id="dankotoken",
            credential_source="DANKOTOKEN_API_KEY",
            codex_home=None,
        )

    if env.get("DANKOTOKEN_ALLOW_CODEX_FALLBACK", "").strip() != "1":
        raise DankoImageError(
            "configure DANKOTOKEN_API_KEY or set "
            "DANKOTOKEN_ALLOW_CODEX_FALLBACK=1"
        )

    home = codex_home if codex_home is not None else resolve_codex_home(None, env)
    try:
        config = load_toml(home / "config.toml")
        provider_id, provider = active_provider(config)
        base_url = resolve_codex_base_url(config, provider_id, provider)
    except RouteError:
        raise DankoImageError("Danko image route could not be resolved") from None
    host = (urlsplit(base_url).hostname or "").lower()
    if host not in DANKO_HOSTS:
        raise DankoImageError("Codex image route must use the DankoToken host")
    try:
        api_key, credential_source = provider_credential(
            config,
            provider,
            home / "auth.json",
            env,
            run_auth_command,
        )
        if not api_key:
            raise RouteError("Codex route has no usable API credential")
        validate_proxy_placeholder(api_key, host)
    except RouteError:
        raise DankoImageError("Danko image route could not be resolved") from None
    return ResolvedRoute(
        api_key=api_key,
        base_url=base_url,
        host=host,
        source="codex",
        provider_id=provider_id,
        credential_source=credential_source,
        codex_home=home,
    )


def _resolve_workspace(workspace: Path) -> Path:
    resolved = Path(workspace).resolve()
    if not resolved.is_dir():
        raise DankoImageError("workspace directory is unavailable")
    return resolved


def _resolve_within_workspace(path: Path, workspace: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise DankoImageError("image path must be inside the workspace") from None
    return resolved


def validate_input_image(input_image_path: Path, workspace: Path) -> Path:
    resolved_workspace = _resolve_workspace(workspace)
    image = _resolve_within_workspace(input_image_path, resolved_workspace)
    if not image.is_file():
        raise DankoImageError("input image file is unavailable")
    if image.suffix.lower() not in SUPPORTED_EDIT_SUFFIXES:
        raise DankoImageError("input image must be a PNG, JPEG, or WebP file")
    return image


def _resolve_output_path(
    output_path: Path | None, workspace: Path, output_format: str
) -> Path:
    resolved_workspace = _resolve_workspace(workspace)
    default_output = DEFAULT_OUTPUT_DIRECTORY / f"generated.{output_format}"
    output = _resolve_within_workspace(
        output_path if output_path is not None else default_output,
        resolved_workspace,
    )
    if output.exists():
        raise DankoImageError("image output already exists")
    return output


def persist_response(
    response: object,
    route: ResolvedRoute,
    request: ImageRequest,
    output: Path,
) -> GeneratedImage:
    try:
        content = decode_first_image(response)
    except ResponseError:
        raise DankoImageError("provider returned no valid base64 image") from None

    try:
        atomic_write(output, content, force=False)
    except FileExistsError:
        raise DankoImageError("image output already exists") from None
    except OSError:
        raise DankoImageError("image output could not be written") from None
    return GeneratedImage(
        content=content,
        output_path=output,
        source=route.source,
        host=route.host,
        model=request.model,
        output_format=request.output_format,
    )


def generate_image(
    request: ImageRequest,
    route: ResolvedRoute,
    client_factory: Callable[[ResolvedRoute], object],
    workspace: Path,
    output_path: Path | None = None,
) -> GeneratedImage:
    payload = request.to_payload()
    output = _resolve_output_path(output_path, workspace, request.output_format)
    try:
        response = client_factory(route).images.generate(**payload)
    except DankoImageError:
        raise
    except Exception as exc:
        raise DankoImageError(
            f"image generation request failed: {type(exc).__name__}"
        ) from None
    return persist_response(response, route, request, output)


def edit_image(
    request: ImageRequest,
    input_image_path: Path,
    route: ResolvedRoute,
    client_factory: Callable[[ResolvedRoute], object],
    workspace: Path,
    output_path: Path | None = None,
) -> GeneratedImage:
    payload = request.to_payload()
    image = validate_input_image(input_image_path, workspace)
    output = _resolve_output_path(output_path, workspace, request.output_format)
    try:
        with image.open("rb") as handle:
            response = client_factory(route).images.edit(
                image=handle, **payload
            )
    except DankoImageError:
        raise
    except OSError:
        raise DankoImageError("input image file is unavailable") from None
    except Exception as exc:
        raise DankoImageError(
            f"image edit request failed: {type(exc).__name__}"
        ) from None
    return persist_response(response, route, request, output)
