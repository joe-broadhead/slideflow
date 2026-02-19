"""Template catalog CLI commands.

Provides read-only commands for discovering available chart templates and
inspecting their parameter contracts.
"""

from typing import Any

import typer

from slideflow.builtins.template_engine import get_template_engine


def templates_list_command(show_details: bool = False) -> list[str]:
    """List available template names.

    Args:
        show_details: If True, include template descriptions.

    Returns:
        List of template names discovered by the template engine.
    """
    engine = get_template_engine()
    template_names = engine.list_templates()

    if not template_names:
        typer.echo("No templates found in configured template paths.")
        return []

    if show_details:
        for template_name in template_names:
            info = engine.get_template_info(template_name)
            typer.echo(f"{template_name}: {info['description']}")
    else:
        for template_name in template_names:
            typer.echo(template_name)

    return template_names


def templates_info_command(template_name: str) -> dict[str, Any]:
    """Show metadata and parameter schema for one template.

    Args:
        template_name: Template identifier (bare name or relative path).

    Returns:
        Dictionary with template metadata and parameter schema.

    Raises:
        typer.Exit: If the template is not found.
    """
    engine = get_template_engine()

    try:
        info = engine.get_template_info(template_name)
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"name: {info['name']}")
    typer.echo(f"description: {info['description']}")
    typer.echo(f"version: {info['version']}")
    typer.echo("parameters:")
    if not info["parameters"]:
        typer.echo("  - (none)")
    else:
        for param in info["parameters"]:
            required = "required" if param["required"] else "optional"
            default = (
                f", default={param['default']}"
                if param.get("default") is not None
                else ""
            )
            typer.echo(f"  - {param['name']} ({param['type']}, {required}{default})")
            if param.get("description"):
                typer.echo(f"    {param['description']}")

    return info


templates_app = typer.Typer(help="Discover built-in and local chart templates")


@templates_app.command("list")
def templates_list(
    details: bool = typer.Option(
        False,
        "--details",
        "-d",
        help="Show template descriptions in addition to names",
    )
) -> None:
    """List all available chart templates."""
    templates_list_command(show_details=details)


@templates_app.command("info")
def templates_info(
    template_name: str = typer.Argument(..., help="Template name")
) -> None:
    """Show template metadata and parameter contract."""
    templates_info_command(template_name)
