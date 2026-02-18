from slideflow.cli.commands._registry import resolve_registry_paths


def test_resolve_registry_paths_uses_config_relative_paths(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_file = config_dir / "config.yml"
    config_file.write_text("provider: {type: google_slides, config: {}}\n")

    resolved = resolve_registry_paths(
        config_file=config_file,
        cli_registry_paths=None,
        config_registry="registry.py",
    )

    assert resolved == [(config_dir / "registry.py").resolve()]


def test_resolve_registry_paths_prefers_config_dir_default_registry(
    tmp_path, monkeypatch
):
    config_dir = tmp_path / "configs"
    other_dir = tmp_path / "other"
    config_dir.mkdir()
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    config_registry_file = config_dir / "registry.py"
    cwd_registry_file = other_dir / "registry.py"
    config_registry_file.write_text("function_registry = {}\n")
    cwd_registry_file.write_text("function_registry = {}\n")

    resolved = resolve_registry_paths(
        config_file=config_dir / "config.yml",
        cli_registry_paths=None,
        config_registry=None,
    )

    assert resolved == [config_registry_file, cwd_registry_file]


def test_resolve_registry_paths_prefers_cli_over_config(tmp_path):
    config_file = tmp_path / "config.yml"
    cli_registry = tmp_path / "cli_registry.py"

    resolved = resolve_registry_paths(
        config_file=config_file,
        cli_registry_paths=[cli_registry],
        config_registry="config_registry.py",
    )

    assert resolved == [cli_registry]
