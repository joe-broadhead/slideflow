import typer

from slideflow.commands.build import main as build_main
from slideflow.commands.preview import main as preview_main
from slideflow.commands.validate import main as validate_main
from slideflow.commands.build_bulk import app as build_bulk_app
from slideflow.commands.extract_sources import app as extract_sources_app

app = typer.Typer()

app.command('build')(build_main)
app.command('preview')(preview_main)
app.command('validate')(validate_main)

app.add_typer(build_bulk_app, name = 'build-bulk')
app.add_typer(extract_sources_app, name = 'extract-sources')

def main():
    app()

if __name__ == '__main__':
    main()
