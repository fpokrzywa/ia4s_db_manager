"""Command-line entry point."""
from __future__ import annotations
import click
import uvicorn


@click.group()
def cli() -> None:
    """Database Manager."""


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address.")
@click.option("--port", default=8000, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, help="Auto-reload on code change.")
def web(host: str, port: int, reload: bool) -> None:
    """Run the web app."""
    uvicorn.run("dbmanager.webapp:app", host=host, port=port, reload=reload)
