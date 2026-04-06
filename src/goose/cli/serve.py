"""goose serve — start the Goose REST API server."""

from __future__ import annotations

import click


@click.command()
@click.option("-h", "--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("-p", "--port", default=8000, show_default=True, help="Bind port")
@click.option("--reload", "live_reload", is_flag=True, default=False, help="Enable auto-reload for development")
def serve(host: str, port: int, live_reload: bool) -> None:
    """Start the Goose API server.

    Launches a uvicorn server hosting the FastAPI application defined in
    ``goose.web.app``.
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException(
            "uvicorn is required to run the server. Install it with: pip install uvicorn"
        ) from exc

    click.echo(f"Goose API server starting on {host}:{port}")
    uvicorn.run(
        "goose.web.app:app",
        host=host,
        port=port,
        reload=live_reload,
    )
