"""goose serve — start the embedded web UI."""

from __future__ import annotations

import click


@click.command()
@click.option("-p", "--port", default=8080, help="Port to serve on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
def serve(port: int, host: str, no_browser: bool) -> None:
    """Start the Goose web UI for interactive flight analysis."""
    try:
        import uvicorn
    except ImportError:
        click.echo("Error: uvicorn not installed. Run: pip install goose-flight[web]")
        raise SystemExit(1)

    click.echo(f"Starting Goose web UI at http://{host}:{port}")
    if not no_browser:
        import webbrowser
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    from goose.web.app import create_app
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
