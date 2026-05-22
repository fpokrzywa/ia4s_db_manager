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


@cli.command("init-auth")
@click.option("--email", required=True, help="Email of the first user.")
@click.option("--password", required=True, help="Temporary password.")
def init_auth(email: str, password: str) -> None:
    """Create the auth tables in common_data and seed the first user."""
    from dbmanager import authdb
    from dbmanager.config import Settings
    from dbmanager.passwords import hash_password

    settings = Settings.from_env()
    authdb.apply_schema(settings.common_data_url)
    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_email(conn, email) is not None:
            click.echo(f"user {email} already exists — tables ensured, "
                       f"no change made")
            return
        authdb.create_user(conn, email, hash_password(password),
                           must_change=True)
    click.echo(f"created user {email} — must change password on first login")
