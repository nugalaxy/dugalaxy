"""CLI entrypoint. Commands: dugalaxy gen / init / studio.

Wired as the `dugalaxy` console script via pyproject.toml [project.scripts].
"""

import typer

app = typer.Typer(
    help="Author a data template once, generate endless realistic samples forever.",
    no_args_is_help=True,
)


@app.callback()
def _main() -> None:
    """Dugalaxy command-line interface."""


@app.command()
def version() -> None:
    """Print the installed Dugalaxy version."""
    from dugalaxy import __version__

    typer.echo(f"dugalaxy {__version__}")


# TODO (build phase): `gen`, `init`, `studio` commands.

if __name__ == "__main__":
    app()
