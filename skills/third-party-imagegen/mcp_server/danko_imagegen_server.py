from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ImageContent, TextContent
from openai import OpenAI

try:
    from . import danko_imagegen_core as danko_core
except ImportError:
    import danko_imagegen_core as danko_core


mcp = FastMCP(
    "danko-imagegen",
    instructions=(
        "When a DankoToken route is configured, use generate_danko_image and "
        "edit_danko_image as the intended replacement path for built-in "
        "image_gen. Use edit_danko_image only with a local reference image "
        "path. Both tools write files."
    ),
)


def _client_for_route(route: Any) -> OpenAI:
    return OpenAI(api_key=route.api_key, base_url=route.base_url)


def _result_content(result: Any) -> list[ImageContent | TextContent]:
    image = Image(data=result.content, format=result.output_format)
    return [
        image.to_image_content(),
        TextContent(
            type="text",
            text=(
                f"source: {result.source}\n"
                f"host: {result.host}\n"
                f"model: {result.model}\n"
                f"format: {result.output_format}\n"
                f"saved_path: {result.output_path}"
            ),
        ),
    ]


def _resolve_route(core: Any) -> Any:
    try:
        return core.resolve_danko_route(os.environ)
    except core.DankoImageError:
        raise ToolError(
            "Unable to resolve the Danko image route. Configure a DankoToken "
            "credential or a DankoToken-hosted Codex route."
        ) from None


def _local_input_path(input_image_path: str) -> Path:
    path = Path(input_image_path)
    parsed = urlsplit(input_image_path)
    if not path.drive and (parsed.scheme or parsed.netloc):
        raise ToolError("input_image_path must be a local file path")
    return path


def generate_danko_image(
    prompt: str,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "medium",
    output_format: str = "png",
    output_path: str | None = None,
    *,
    core: Any | None = None,
) -> list[ImageContent | TextContent]:
    """Generate an image through the configured DankoToken route."""
    implementation = danko_core if core is None else core
    request = implementation.ImageRequest(
        prompt=prompt,
        model=model,
        size=size,
        quality=quality,
        output_format=output_format,
    )
    route = _resolve_route(implementation)
    try:
        result = implementation.generate_image(
            request,
            route,
            _client_for_route,
            Path.cwd(),
            Path(output_path) if output_path is not None else None,
        )
    except implementation.DankoImageError:
        raise ToolError(
            "Danko image generation failed. Verify the image request and local "
            "output path."
        ) from None
    return _result_content(result)


def edit_danko_image(
    prompt: str,
    input_image_path: str,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "medium",
    output_format: str = "png",
    output_path: str | None = None,
    *,
    core: Any | None = None,
) -> list[ImageContent | TextContent]:
    """Edit a local image through the configured DankoToken route."""
    implementation = danko_core if core is None else core
    input_path = _local_input_path(input_image_path)
    request = implementation.ImageRequest(
        prompt=prompt,
        model=model,
        size=size,
        quality=quality,
        output_format=output_format,
    )
    route = _resolve_route(implementation)
    try:
        result = implementation.edit_image(
            request,
            input_path,
            route,
            _client_for_route,
            Path.cwd(),
            Path(output_path) if output_path is not None else None,
        )
    except implementation.DankoImageError:
        raise ToolError(
            "Danko image editing failed. Verify the local input image and output "
            "path."
        ) from None
    return _result_content(result)


@mcp.tool(name="generate_danko_image")
def generate_danko_image_tool(
    prompt: str,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "medium",
    output_format: str = "png",
    output_path: str | None = None,
) -> list[ImageContent | TextContent]:
    return generate_danko_image(
        prompt, model, size, quality, output_format, output_path
    )


@mcp.tool(name="edit_danko_image")
def edit_danko_image_tool(
    prompt: str,
    input_image_path: str,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "medium",
    output_format: str = "png",
    output_path: str | None = None,
) -> list[ImageContent | TextContent]:
    return edit_danko_image(
        prompt,
        input_image_path,
        model,
        size,
        quality,
        output_format,
        output_path,
    )


def run_stdio() -> None:
    """Start the MCP server on its standard input/output transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
