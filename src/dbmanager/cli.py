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
    """Create the auth + servers tables in common_data, seed the first user,
    and register the DATABASE_URL server if the registry is empty."""
    from psycopg.conninfo import conninfo_to_dict
    from dbmanager import authdb, serverdb
    from dbmanager.config import Settings
    from dbmanager.passwords import hash_password

    settings = Settings.from_env()
    authdb.apply_schema(settings.common_data_url)
    serverdb.apply_schema(settings.common_data_url)

    with authdb.auth_conn(settings.common_data_url) as conn:
        if authdb.get_user_by_email(conn, email) is None:
            authdb.create_user(conn, email, hash_password(password),
                               must_change=True)
            click.echo(f"created user {email} — must change password "
                       f"on first login")
        else:
            click.echo(f"user {email} already exists — no change made")

        if not serverdb.list_servers(conn) and settings.database_url:
            p = conninfo_to_dict(settings.database_url)
            serverdb.create_server(
                conn,
                label=p.get("host") or "primary",
                host=p.get("host") or "127.0.0.1",
                port=int(p.get("port") or 5432),
                username=p.get("user") or "postgres",
                password=p.get("password") or "",
                maintenance_db=p.get("dbname") or "postgres",
                is_default=True)
            click.echo(f"registered server '{p.get('host')}' from DATABASE_URL")
        else:
            click.echo("server registry already populated — no server seeded")
