from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

try:
    from ..scripts.codex_route import (
        ResolvedRoute,
        RouteError,
        resolve_codex_home,
        resolve_route,
        validate_base_url,
    )
    from ..scripts.generate_image import ResponseError, atomic_write, decode_first_image
except ImportError:
    from codex_route import (
        ResolvedRoute,
        RouteError,
        resolve_codex_home,
        resolve_route,
        validate_base_url,
    )
    from generate_image import ResponseError, atomic_write, decode_first_image


DEFAULT_DANKO_BASE_URL = "https://dankotoken.com/v1/"
DANKO_HOST = "dankotoken.com"
DEFAULT_OUTPUT_NAME = "generated.png"


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
        if not self.prompt.strip():
            raise DankoImageError("image prompt must not be empty")
        if not self.model.startswith("gpt-image-"):
            raise DankoImageError("image model must start with gpt-image-")
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

    home = codex_home if codex_home is not None else resolve_codex_home(None, env)
    try:
        route = resolve_route(
            "codex", codex_home=home, env=env, dry_run=False
        )
    except RouteError:
        raise DankoImageError("Danko image route could not be resolved") from None
    if route.host.lower() != DANKO_HOST:
        raise DankoImageError("Codex image route must use the DankoToken host")
    return route


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
    return image


def _resolve_output_path(
    output_path: Path | None, workspace: Path
) -> Path:
    resolved_workspace = _resolve_workspace(workspace)
    return _resolve_within_workspace(
        output_path if output_path is not None else Path(DEFAULT_OUTPUT_NAME),
        resolved_workspace,
    )


def persist_response(
    response: object,
    route: ResolvedRoute,
    request: ImageRequest,
    workspace: Path,
    output_path: Path | None,
) -> GeneratedImage:
    try:
        content = decode_first_image(response)
    except ResponseError:
        raise DankoImageError("provider returned no valid base64 image") from None

    output = _resolve_output_path(output_path, workspace)
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
    try:
        response = client_factory(route).images.generate(**request.to_payload())
    except DankoImageError:
        raise
    except Exception as exc:
        raise DankoImageError(
            f"image generation request failed: {type(exc).__name__}"
        ) from None
    return persist_response(response, route, request, workspace, output_path)


def edit_image(
    request: ImageRequest,
    input_image_path: Path,
    route: ResolvedRoute,
    client_factory: Callable[[ResolvedRoute], object],
    workspace: Path,
    output_path: Path | None = None,
) -> GeneratedImage:
    image = validate_input_image(input_image_path, workspace)
    try:
        with image.open("rb") as handle:
            response = client_factory(route).images.edit(
                image=handle, **request.to_payload()
            )
    except DankoImageError:
        raise
    except OSError:
        raise DankoImageError("input image file is unavailable") from None
    except Exception as exc:
        raise DankoImageError(
            f"image edit request failed: {type(exc).__name__}"
        ) from None
    return persist_response(response, route, request, workspace, output_path)
