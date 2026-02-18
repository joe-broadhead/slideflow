from pathlib import Path
from types import SimpleNamespace
import threading

import pandas as pd
import pytest

import slideflow.cli.commands.build as build_command_module
import slideflow.presentations.base as base_module
import slideflow.presentations.builder as builder_module
import slideflow.presentations.providers.google_slides as google_provider_module
from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import PresentationConfig


def _stub_build_cli_output(monkeypatch):
    monkeypatch.setattr(
        build_command_module, "print_build_header", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_progress", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_success", lambda *a, **k: None
    )
    monkeypatch.setattr(build_command_module, "print_build_error", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module.time, "sleep", lambda *_: None)


def test_build_single_presentation_applies_rps_override_and_returns_result(monkeypatch):
    captured = {}
    limiter = object()

    class FakePresentation:
        def __init__(self):
            self.name = "Deck"
            self.provider = SimpleNamespace(
                config=SimpleNamespace(requests_per_second=1.0),
                rate_limiter=None,
            )

        def render(self):
            return SimpleNamespace(presentation_url="https://example.com/deck")

    fake_presentation = FakePresentation()

    def _from_yaml(yaml_path, registry_paths, params):
        captured["yaml_path"] = yaml_path
        captured["registry_paths"] = list(registry_paths)
        captured["params"] = dict(params)
        return fake_presentation

    monkeypatch.setattr(
        build_command_module.PresentationBuilder,
        "from_yaml",
        staticmethod(_from_yaml),
    )
    monkeypatch.setattr(
        google_provider_module,
        "_get_rate_limiter",
        lambda rps, force_update=False: limiter,
    )

    name, result, index, params = build_command_module.build_single_presentation(
        config_file=Path("config.yml"),
        registry_files=[Path("registry.py")],
        params={"region": "us"},
        index=1,
        total=2,
        print_lock=threading.Lock(),
        requests_per_second=4.5,
    )

    assert captured["yaml_path"] == Path("config.yml")
    assert captured["registry_paths"] == [Path("registry.py")]
    assert captured["params"] == {"region": "us"}
    assert fake_presentation.provider.config.requests_per_second == 4.5
    assert fake_presentation.provider.rate_limiter is limiter
    assert (name, index, params) == ("Deck", 1, {"region": "us"})
    assert result.presentation_url == "https://example.com/deck"


def test_build_single_presentation_propagates_render_error(monkeypatch):
    class FakePresentation:
        def __init__(self):
            self.name = "Broken Deck"
            self.provider = SimpleNamespace(
                config=SimpleNamespace(requests_per_second=1.0)
            )

        def render(self):
            raise RuntimeError("render failed")

    monkeypatch.setattr(
        build_command_module.PresentationBuilder,
        "from_yaml",
        staticmethod(lambda *a, **k: FakePresentation()),
    )

    with pytest.raises(RuntimeError, match="render failed"):
        build_command_module.build_single_presentation(
            config_file=Path("config.yml"),
            registry_files=[],
            params={},
            index=1,
            total=1,
            print_lock=threading.Lock(),
        )


def test_build_command_non_dry_run_processes_results_and_sorts(tmp_path, monkeypatch):
    _stub_build_cli_output(monkeypatch)
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n",
        encoding="utf-8",
    )
    params_path = tmp_path / "params.csv"
    params_path.write_text("region\nus\neu\n", encoding="utf-8")

    def _fake_build_single(
        config_file,
        registry_files,
        params,
        index,
        total,
        print_lock,
        requests_per_second=None,
    ):
        if params["region"] == "us":
            return (
                "Z Deck",
                SimpleNamespace(presentation_url="https://example.com/z"),
                index,
                params,
            )
        return (
            "A Deck",
            SimpleNamespace(presentation_url="https://example.com/a"),
            index,
            params,
        )

    monkeypatch.setattr(
        build_command_module, "build_single_presentation", _fake_build_single
    )

    result = build_command_module.build_command(
        config_file=config_file,
        registry_files=None,
        params_path=params_path,
        dry_run=False,
        threads=2,
    )

    assert [row["presentation_name"] for row in result] == ["A Deck", "Z Deck"]
    assert [row["url"] for row in result] == [
        "https://example.com/a",
        "https://example.com/z",
    ]
    assert sorted(row["region"] for row in result) == ["eu", "us"]


def test_build_command_non_dry_run_worker_failure_exits(tmp_path, monkeypatch):
    _stub_build_cli_output(monkeypatch)
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n",
        encoding="utf-8",
    )
    params_path = tmp_path / "params.csv"
    params_path.write_text("region\nus\neu\n", encoding="utf-8")

    def _failing_build_single(
        config_file,
        registry_files,
        params,
        index,
        total,
        print_lock,
        requests_per_second=None,
    ):
        if params["region"] == "eu":
            raise RuntimeError("worker failure")
        return (
            "Deck",
            SimpleNamespace(presentation_url="https://example.com/ok"),
            index,
            params,
        )

    monkeypatch.setattr(
        build_command_module, "build_single_presentation", _failing_build_single
    )

    with pytest.raises(build_command_module.typer.Exit) as exc_info:
        build_command_module.build_command(
            config_file=config_file,
            registry_files=None,
            params_path=params_path,
            dry_run=False,
            threads=2,
        )

    assert exc_info.value.code == 1


def test_presentation_builder_from_yaml_uses_loader_and_delegates(
    monkeypatch, tmp_path
):
    captured = {}

    class FakeLoader:
        def __init__(self, yaml_path, registry_paths, params):
            captured["yaml_path"] = yaml_path
            captured["registry_paths"] = list(registry_paths)
            captured["params"] = dict(params)
            self.config = {
                "provider": {"type": "google_slides", "config": {}},
                "presentation": {"name": "Demo", "slides": []},
            }

    monkeypatch.setattr(builder_module, "ConfigLoader", FakeLoader)

    sentinel = object()

    def _from_config(cls, config):
        captured["config"] = config
        return sentinel

    monkeypatch.setattr(
        builder_module.PresentationBuilder,
        "from_config",
        classmethod(_from_config),
    )

    result = builder_module.PresentationBuilder.from_yaml(
        yaml_path=tmp_path / "config.yaml",
        registry_paths=[Path("registry.py")],
        params={"region": "us"},
    )

    assert result is sentinel
    assert captured["yaml_path"] == tmp_path / "config.yaml"
    assert captured["registry_paths"] == [Path("registry.py")]
    assert captured["params"] == {"region": "us"}
    assert isinstance(captured["config"], PresentationConfig)


def test_presentation_builder_from_config_sets_templates_and_builds_slides(monkeypatch):
    config = PresentationConfig.model_validate(
        {
            "template_paths": ["./templates"],
            "provider": {"type": "google_slides", "config": {}},
            "presentation": {
                "name": "Demo",
                "slides": [{"id": "slide_1"}, {"id": "slide_2"}],
            },
        }
    )

    template_calls = []
    slide_ids = []
    fake_provider = object()
    fake_slides = [SimpleNamespace(id="s1"), SimpleNamespace(id="s2")]

    monkeypatch.setattr(
        builder_module, "set_template_paths", lambda paths: template_calls.append(paths)
    )
    monkeypatch.setattr(
        builder_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: fake_provider),
    )

    def _build_slide(cls, spec):
        slide_ids.append(spec.id)
        return fake_slides[len(slide_ids) - 1]

    monkeypatch.setattr(
        builder_module.PresentationBuilder,
        "_build_slide",
        classmethod(_build_slide),
    )
    monkeypatch.setattr(
        builder_module, "Presentation", lambda **kwargs: SimpleNamespace(**kwargs)
    )

    presentation = builder_module.PresentationBuilder.from_config(config)

    assert template_calls == [["./templates"]]
    assert slide_ids == ["slide_1", "slide_2"]
    assert presentation.provider is fake_provider
    assert presentation.name == "Demo"
    assert presentation.slides == fake_slides


def test_prefetch_data_sources_deduplicates_sources(monkeypatch):
    class FakeSource:
        def __init__(self, source_type, name):
            self.type = source_type
            self.name = name
            self.calls = 0

        def fetch_data(self):
            self.calls += 1
            return pd.DataFrame({"x": [1]})

    shared = FakeSource("csv", "shared")
    unique = FakeSource("csv", "unique")

    replacement = SimpleNamespace(data_source=[shared, unique])
    chart = SimpleNamespace(data_source=shared)
    slide = Slide.model_construct(
        id="slide_1", title="S1", replacements=[replacement], charts=[chart]
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=SimpleNamespace(),
    )

    captured_items = []

    def _execute(
        self, items, task_func, task_name, max_workers=10, collect_results=False
    ):
        captured_items.extend(items)
        for _, source in items:
            task_func(source)
        return []

    monkeypatch.setattr(Presentation, "_execute_concurrent_tasks", _execute)

    presentation._prefetch_data_sources()

    assert [(name, source.name) for name, source in captured_items] == [
        ("shared", "shared"),
        ("unique", "unique"),
    ]
    assert shared.calls == 1
    assert unique.calls == 1


def test_execute_concurrent_tasks_collects_results_and_reraises_errors():
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[],
        provider=SimpleNamespace(),
    )

    results = presentation._execute_concurrent_tasks(
        items=[("a", 1), ("b", 2)],
        task_func=lambda value: value * 2,
        task_name="double",
        collect_results=True,
    )
    assert dict(results) == {"a": 2, "b": 4}

    def _explode(_value):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        presentation._execute_concurrent_tasks(
            items=[("bad", 1)],
            task_func=_explode,
            task_name="explode",
        )


def test_render_shares_presentation_and_processes_table_replacements(monkeypatch):
    monkeypatch.setattr(base_module.time, "sleep", lambda *_: None)

    class FakeProvider:
        def __init__(self):
            self.config = SimpleNamespace(
                strict_cleanup=False,
                share_with=["team@example.com"],
                share_role="reader",
            )
            self.share_calls = []
            self.replace_calls = []

        def create_presentation(self, name):
            return "pres-1"

        def upload_chart_image(self, presentation_id, image_data, filename):
            return ("https://example.com/chart.png", "file-1")

        def insert_chart_to_slide(
            self, presentation_id, slide_id, image_url, x, y, width, height
        ):
            return None

        def replace_text_in_slide(
            self, presentation_id, slide_id, placeholder, replacement
        ):
            self.replace_calls.append((slide_id, placeholder, replacement))
            return 2

        def share_presentation(self, presentation_id, emails, role="writer"):
            self.share_calls.append((presentation_id, tuple(emails), role))

        def get_presentation_url(self, presentation_id):
            return f"https://example.com/{presentation_id}"

        def delete_chart_image(self, file_id):
            return None

    class TextReplacement:
        placeholder = "{{TITLE}}"
        type = "text"

        @staticmethod
        def get_replacement():
            return "Demo Title"

    class TableReplacement:
        prefix = "T_"
        type = "table"

        @staticmethod
        def get_replacement():
            return {"{{T_1}}": "A", "{{T_2}}": "B"}

    provider = FakeProvider()
    slide = Slide.model_construct(
        id="slide_1",
        title="S1",
        replacements=[TextReplacement(), TableReplacement()],
        charts=[],
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=provider,
    )

    result = presentation.render()

    assert result.presentation_id == "pres-1"
    assert result.replacements_made == 6
    assert provider.share_calls == [("pres-1", ("team@example.com",), "reader")]
    assert [call[1] for call in provider.replace_calls] == [
        "{{TITLE}}",
        "{{T_1}}",
        "{{T_2}}",
    ]


def test_render_inserts_error_placeholder_after_chart_retries(monkeypatch):
    monkeypatch.setattr(base_module.time, "sleep", lambda *_: None)

    class FailingChart:
        type = "plotly_go"
        title = "Failing"
        x = 10
        y = 20
        width = 100
        height = 50
        dimensions_format = "pt"
        alignment_format = None
        data_source = None

        @staticmethod
        def generate_chart_image(_df):
            raise RuntimeError("cannot render chart")

    class FakeProvider:
        def __init__(self):
            self.config = SimpleNamespace(
                strict_cleanup=False, share_with=[], share_role="writer"
            )
            self.insert_calls = []

        def create_presentation(self, name):
            return "pres-err"

        def upload_chart_image(self, presentation_id, image_data, filename):
            return ("https://example.com/chart.png", "file-1")

        def insert_chart_to_slide(
            self, presentation_id, slide_id, image_url, x, y, width, height
        ):
            self.insert_calls.append((slide_id, image_url, x, y, width, height))

        def replace_text_in_slide(
            self, presentation_id, slide_id, placeholder, replacement
        ):
            return 0

        def share_presentation(self, presentation_id, emails, role="writer"):
            return None

        def get_presentation_url(self, presentation_id):
            return f"https://example.com/{presentation_id}"

        def delete_chart_image(self, file_id):
            return None

    provider = FakeProvider()
    slide = Slide.model_construct(
        id="slide_1", title="S1", replacements=[], charts=[FailingChart()]
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=provider,
    )

    result = presentation.render()

    assert result.presentation_id == "pres-err"
    assert result.charts_generated == 0
    assert len(provider.insert_calls) == 1
    assert (
        provider.insert_calls[0][1]
        == "https://drive.google.com/uc?id=10geCrUpKZmQBesbhjtepZ9NexE-HRkn4"
    )
