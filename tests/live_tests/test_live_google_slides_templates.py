import os
import uuid
from math import ceil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import pytest
import yaml  # type: ignore[import-untyped]

from slideflow.builtins.template_engine import TemplateEngine
from slideflow.presentations.builder import PresentationBuilder
from slideflow.presentations.providers.google_slides import (
    GoogleSlidesProvider,
    GoogleSlidesProviderConfig,
)

pytestmark = pytest.mark.live_google

CHARTS_PER_SLIDE = 4
CHART_SLOT_LAYOUTS: List[Tuple[int, int, int, int]] = [
    (30, 140, 300, 180),
    (380, 140, 300, 180),
    (30, 335, 300, 180),
    (380, 335, 300, 180),
]


def _require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        pytest.skip(f"{var_name} is not set; skipping live Google Slides tests.")
    return value


def _parse_optional_email_list(var_name: str) -> List[str]:
    raw = os.getenv(var_name, "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="session")
def live_provider() -> GoogleSlidesProvider:
    if os.getenv("SLIDEFLOW_RUN_LIVE") != "1":
        pytest.skip("SLIDEFLOW_RUN_LIVE != 1; skipping live Google Slides tests.")

    credentials = _require_env("GOOGLE_SLIDEFLOW_CREDENTIALS")
    presentation_folder_id = _require_env("SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID")
    drive_folder_id = os.getenv(
        "SLIDEFLOW_LIVE_DRIVE_FOLDER_ID", presentation_folder_id
    )
    requests_per_second = float(os.getenv("SLIDEFLOW_LIVE_RPS", "1.0"))

    config = GoogleSlidesProviderConfig(
        credentials=credentials,
        presentation_folder_id=presentation_folder_id,
        drive_folder_id=drive_folder_id,
        strict_cleanup=True,
        requests_per_second=requests_per_second,
    )
    return GoogleSlidesProvider(config)


def _extract_slide_text(slide_payload: Dict[str, Any]) -> str:
    text_chunks: List[str] = []
    for element in slide_payload.get("pageElements", []):
        shape = element.get("shape")
        if not shape:
            continue
        text = shape.get("text", {})
        for text_element in text.get("textElements", []):
            text_run = text_element.get("textRun")
            if text_run and text_run.get("content"):
                text_chunks.append(text_run["content"])
    return "".join(text_chunks)


def _count_images(slide_payload: Dict[str, Any]) -> int:
    return sum(
        1 for element in slide_payload.get("pageElements", []) if "image" in element
    )


def _trash_files(provider: GoogleSlidesProvider, file_ids: Iterable[str]) -> None:
    for file_id in file_ids:
        if not file_id:
            continue
        try:
            provider._execute_request(
                provider.drive_service.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                )
            )
        except Exception:
            # Cleanup best-effort: assertions should focus on rendering behavior.
            pass


def _create_working_template(provider: GoogleSlidesProvider, title_prefix: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    title = f"{title_prefix} template {suffix}"
    base_template_id = os.getenv("SLIDEFLOW_LIVE_TEMPLATE_ID")

    if base_template_id:
        return provider._copy_template(base_template_id, title)

    return provider.create_presentation(title)


def _get_slide_ids(provider: GoogleSlidesProvider, presentation_id: str) -> List[str]:
    payload = provider._execute_request(
        provider.slides_service.presentations().get(
            presentationId=presentation_id,
            fields="slides(objectId)",
        )
    )
    return [slide["objectId"] for slide in payload.get("slides", [])]


def _ensure_slide_count(
    provider: GoogleSlidesProvider,
    presentation_id: str,
    required_count: int,
    suffix: str,
) -> List[str]:
    slide_ids = _get_slide_ids(provider, presentation_id)
    requests: List[Dict[str, Any]] = []

    while len(slide_ids) < required_count:
        new_slide_id = f"sflive{suffix}{len(slide_ids)}"
        requests.append(
            {
                "createSlide": {
                    "objectId": new_slide_id,
                    "insertionIndex": len(slide_ids),
                    "slideLayoutReference": {"predefinedLayout": "BLANK"},
                }
            }
        )
        slide_ids.append(new_slide_id)

    if requests:
        provider._batch_update(presentation_id, requests)

    return slide_ids[:required_count]


def _add_placeholder_boxes(
    provider: GoogleSlidesProvider,
    presentation_id: str,
    slide_id: str,
    placeholders: Sequence[str],
) -> None:
    requests: List[Dict[str, Any]] = []

    for index, placeholder in enumerate(placeholders):
        textbox_id = f"sflivetxt{uuid.uuid4().hex[:10]}"
        y = 20 + (index * 28)
        requests.append(
            {
                "createShape": {
                    "objectId": textbox_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "height": {"magnitude": 24, "unit": "PT"},
                            "width": {"magnitude": 640, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": 20,
                            "translateY": y,
                            "unit": "PT",
                        },
                    },
                }
            }
        )
        requests.append({"insertText": {"objectId": textbox_id, "text": placeholder}})

    provider._batch_update(presentation_id, requests)


def _write_live_registry(registry_path: Path) -> None:
    registry_path.write_text(
        "import plotly.graph_objects as go\n"
        "import plotly.io as pio\n"
        "\n"
        "def decorate_presentation_name(name: str) -> str:\n"
        '    return f"{name} :: live"\n'
        "\n"
        'def summarize_revenue(df, prefix: str = "Total Revenue") -> str:\n'
        "    total = float(df['revenue'].sum())\n"
        '    return f"{prefix}: {int(total)}"\n'
        "\n"
        'def deterministic_ai_provider(prompt: str, label: str = "LIVE_AI", **kwargs) -> str:\n'
        '    return f"{label}: generated summary"\n'
        "\n"
        "def _safe_to_image(fig):\n"
        "    opts = {'format': 'png', 'width': 640, 'height': 360, 'scale': 1}\n"
        "    try:\n"
        "        import kaleido\n"
        "        kaleido.start_sync_server(n=1, timeout=90, headless=True, silence_warnings=True)\n"
        "        return kaleido.calc_fig_sync(fig.to_plotly_json(), opts=opts)\n"
        "    except Exception:\n"
        "        return pio.to_image(fig, **opts)\n"
        "\n"
        "def custom_revenue_chart(df, chart_config, chart_instance):\n"
        "    fig = go.Figure(\n"
        "        data=[\n"
        "            go.Bar(\n"
        "                x=df['month'].tolist(),\n"
        "                y=df['revenue'].tolist(),\n"
        "                marker_color=chart_config.get('color', '#1f77b4'),\n"
        "            )\n"
        "        ]\n"
        "    )\n"
        "    fig.update_layout(title=chart_config.get('title', 'Custom Revenue'))\n"
        "    return _safe_to_image(fig)\n"
        "\n"
        "function_registry = {\n"
        "    'decorate_presentation_name': decorate_presentation_name,\n"
        "    'summarize_revenue': summarize_revenue,\n"
        "    'deterministic_ai_provider': deterministic_ai_provider,\n"
        "    'custom_revenue_chart': custom_revenue_chart,\n"
        "}\n",
        encoding="utf-8",
    )


def _template_param_value(template_name: str, param_name: str) -> Any:
    if param_name == "title":
        return f"{template_name} live"
    if param_name == "x_column":
        return "matrix_x" if template_name.endswith("heatmap_matrix") else "month"
    if param_name == "y_column":
        return "matrix_y" if template_name.endswith("heatmap_matrix") else "revenue"
    if param_name == "z_column":
        return "matrix_z"
    if param_name in {"y1_column", "bar_column"}:
        return "revenue"
    if param_name in {"y2_column", "line_column"}:
        return "target"
    if param_name == "label_column":
        return "segment"
    if param_name == "stage_column":
        return "stage"
    if param_name == "group_column":
        return "segment"
    if param_name == "value_column":
        if template_name.startswith("kpi_cards/"):
            return "current_value"
        if template_name.startswith("composition/"):
            return "share"
        return "revenue"
    if param_name == "reference_column":
        return "previous_value"
    if param_name == "column_1":
        return "name"
    if param_name == "column_2":
        return "value"
    if param_name == "y_title":
        return "Revenue"
    if param_name in {"value_row_index", "reference_row_index"}:
        return 0
    return "month"


def _build_template_charts(data_path: Path) -> List[Dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    builtins_path = repo_root / "slideflow" / "templates"
    if not builtins_path.is_dir():
        raise AssertionError(
            f"Built-in template directory not found at expected path: {builtins_path}"
        )

    engine = TemplateEngine([builtins_path])
    template_names = engine.list_templates()
    if not template_names:
        raise AssertionError(f"No built-in templates discovered from: {builtins_path}")

    charts: List[Dict[str, Any]] = []
    for template_name in template_names:
        template_info = engine.get_template_info(template_name)
        template_config = {
            param["name"]: _template_param_value(template_name, param["name"])
            for param in template_info["parameters"]
        }
        charts.append(
            {
                "type": "template",
                "config": {
                    "template_name": template_name,
                    "data_source": {
                        "type": "csv",
                        "name": f"template_data_{template_name.replace('/', '_')}",
                        "file_path": str(data_path),
                    },
                    "template_config": template_config,
                },
            }
        )

    return charts


def _build_plotly_and_custom_charts(data_path: Path) -> List[Dict[str, Any]]:
    data_source = {
        "type": "csv",
        "name": "matrix_csv",
        "file_path": str(data_path),
    }

    return [
        {
            "type": "plotly_go",
            "config": {
                "title": "Plotly Bar",
                "data_source": data_source,
                "traces": [{"type": "bar", "x": "$month", "y": "$revenue"}],
            },
        },
        {
            "type": "plotly_go",
            "config": {
                "title": "Plotly Scatter",
                "data_source": data_source,
                "traces": [
                    {
                        "type": "scatter",
                        "x": "$month",
                        "y": "$target",
                        "mode": "lines+markers",
                        "name": "Target",
                    }
                ],
            },
        },
        {
            "type": "plotly_go",
            "config": {
                "title": "Plotly Pie",
                "data_source": data_source,
                "traces": [
                    {
                        "type": "pie",
                        "labels": "$segment",
                        "values": "$share",
                    }
                ],
            },
        },
        {
            "type": "plotly_go",
            "config": {
                "title": "Plotly Indicator",
                "data_source": data_source,
                "traces": [
                    {
                        "type": "indicator",
                        "mode": "number+delta",
                        "value": "$current_value[0]",
                        "delta": {"reference": "$previous_value[0]"},
                    }
                ],
            },
        },
        {
            "type": "custom",
            "config": {
                "title": "Custom Revenue",
                "chart_fn": "custom_revenue_chart",
                "data_source": data_source,
                "chart_config": {
                    "x_series": "$month",
                    "y_series": "$revenue",
                    "color": "#0099cc",
                },
            },
        },
    ]


def _layout_charts(charts: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    pages: List[List[Dict[str, Any]]] = [
        [] for _ in range(ceil(len(charts) / CHARTS_PER_SLIDE))
    ]

    for index, chart in enumerate(charts):
        page = index // CHARTS_PER_SLIDE
        slot = index % CHARTS_PER_SLIDE
        x, y, width, height = CHART_SLOT_LAYOUTS[slot]

        chart_copy = dict(chart)
        config_copy = dict(chart_copy["config"])
        config_copy.update({"x": x, "y": y, "width": width, "height": height})
        chart_copy["config"] = config_copy

        pages[page].append(chart_copy)

    return pages


@pytest.mark.live_google
def test_live_feature_matrix_covers_templates_plotly_and_dynamic_replacements(
    live_provider: GoogleSlidesProvider, tmp_path: Path
):
    created_file_ids: List[str] = []
    share_with = _parse_optional_email_list("SLIDEFLOW_LIVE_SHARE_EMAIL")
    keep_artifacts = _is_truthy(
        os.getenv("SLIDEFLOW_LIVE_KEEP_ARTIFACTS", "1" if share_with else "0")
    )
    share_role = os.getenv("SLIDEFLOW_LIVE_SHARE_ROLE", "reader")

    template_id = _create_working_template(live_provider, title_prefix="slideflow-live")
    created_file_ids.append(template_id)

    data_path = tmp_path / "matrix_data.csv"
    data_path.write_text(
        "month,revenue,target,cost,segment,stage,share,matrix_x,matrix_y,matrix_z,current_value,previous_value,name,value\n"
        "Jan,100,90,70,Enterprise,Lead,55,Q1,North,10,1250,1100,Alpha,100\n"
        "Feb,120,110,80,Mid-Market,Qualified,30,Q1,South,18,1250,1100,Beta,85\n"
        "Mar,140,130,95,SMB,Proposal,15,Q2,North,24,1250,1100,Gamma,60\n",
        encoding="utf-8",
    )

    registry_path = tmp_path / "registry.py"
    _write_live_registry(registry_path)

    direct_charts = _build_plotly_and_custom_charts(data_path)
    template_charts = _build_template_charts(data_path)
    all_charts = direct_charts + template_charts
    charts_by_slide = _layout_charts(all_charts)

    slide_suffix = uuid.uuid4().hex[:6]
    slide_ids = _ensure_slide_count(
        live_provider,
        template_id,
        required_count=max(1, len(charts_by_slide)),
        suffix=slide_suffix,
    )

    _add_placeholder_boxes(
        live_provider,
        template_id,
        slide_ids[0],
        placeholders=[
            "{{TITLE_PLACEHOLDER}}",
            "{{DYNAMIC_PLACEHOLDER}}",
            "{{AI_PLACEHOLDER}}",
            "{{TABLE_1,1}}",
            "{{TABLE_1,2}}",
        ],
    )

    slides_payload: List[Dict[str, Any]] = []
    for index, chart_group in enumerate(charts_by_slide):
        slide_payload: Dict[str, Any] = {
            "id": slide_ids[index],
            "charts": chart_group,
            "replacements": [],
        }
        if index == 0:
            slide_payload["replacements"] = [
                {
                    "type": "text",
                    "config": {
                        "placeholder": "{{TITLE_PLACEHOLDER}}",
                        "replacement": "Feature Matrix Title",
                    },
                },
                {
                    "type": "text",
                    "config": {
                        "placeholder": "{{DYNAMIC_PLACEHOLDER}}",
                        "data_source": {
                            "type": "csv",
                            "name": "dynamic_csv",
                            "file_path": str(data_path),
                        },
                        "value_fn": "summarize_revenue",
                        "value_fn_args": {"prefix": "Total Revenue"},
                    },
                },
                {
                    "type": "ai_text",
                    "config": {
                        "placeholder": "{{AI_PLACEHOLDER}}",
                        "prompt": "Summarize this test run.",
                        "provider": "deterministic_ai_provider",
                        "provider_args": {"label": "LIVE_AI"},
                        "data_source": {
                            "type": "csv",
                            "name": "ai_csv",
                            "file_path": str(data_path),
                        },
                    },
                },
                {
                    "type": "table",
                    "config": {
                        "prefix": "TABLE_",
                        "replacements": {
                            "{{TABLE_1,1}}": "Metric",
                            "{{TABLE_1,2}}": "Value",
                        },
                    },
                },
            ]
        slides_payload.append(slide_payload)

    provider_config: Dict[str, Any] = {
        "credentials": os.environ["GOOGLE_SLIDEFLOW_CREDENTIALS"],
        "template_id": template_id,
        "presentation_folder_id": os.environ["SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID"],
        "drive_folder_id": os.getenv(
            "SLIDEFLOW_LIVE_DRIVE_FOLDER_ID",
            os.environ["SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID"],
        ),
        "strict_cleanup": True,
    }
    if share_with:
        provider_config["share_with"] = share_with
        provider_config["share_role"] = share_role

    config_payload = {
        "registry": [registry_path.name],
        "provider": {
            "type": "google_slides",
            "config": provider_config,
        },
        "presentation": {
            "name": f"slideflow feature matrix {uuid.uuid4().hex[:6]}",
            "name_fn": "decorate_presentation_name",
            "slides": slides_payload,
        },
    }

    config_path = tmp_path / "feature_matrix.yml"
    config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8"
    )

    rendered_presentation_id = ""
    try:
        presentation = PresentationBuilder.from_yaml(
            yaml_path=config_path, registry_paths=[registry_path]
        )
        result = presentation.render()
        rendered_presentation_id = result.presentation_id
        created_file_ids.append(rendered_presentation_id)
        if share_with:
            print(
                "Shared rendered presentation with "
                f"{', '.join(share_with)} ({share_role}): {result.presentation_url}"
            )
        elif keep_artifacts:
            print(
                f"Retained rendered presentation for inspection: {result.presentation_url}"
            )

        assert result.charts_generated == len(all_charts)
        assert result.replacements_made >= 5

        rendered_payload = live_provider._execute_request(
            live_provider.slides_service.presentations().get(
                presentationId=rendered_presentation_id,
                fields=(
                    "title,slides(objectId,pageElements("
                    "objectId,image,shape(text(textElements(textRun(content))))"
                    "))"
                ),
            )
        )

        assert rendered_payload.get("title", "").endswith(":: live")

        slides_by_id = {
            slide["objectId"]: slide for slide in rendered_payload.get("slides", [])
        }

        for index, chart_group in enumerate(charts_by_slide):
            slide_id = slide_ids[index]
            assert slide_id in slides_by_id
            assert _count_images(slides_by_id[slide_id]) >= len(chart_group)

        first_slide_text = _extract_slide_text(slides_by_id[slide_ids[0]])
        assert "{{TITLE_PLACEHOLDER}}" not in first_slide_text
        assert "{{DYNAMIC_PLACEHOLDER}}" not in first_slide_text
        assert "{{AI_PLACEHOLDER}}" not in first_slide_text
        assert "{{TABLE_1,1}}" not in first_slide_text
        assert "{{TABLE_1,2}}" not in first_slide_text

        assert "Feature Matrix Title" in first_slide_text
        assert "Total Revenue: 360" in first_slide_text
        assert "LIVE_AI: generated summary" in first_slide_text
        assert "Metric" in first_slide_text
        assert "Value" in first_slide_text
    finally:
        if keep_artifacts:
            print(
                "Retaining live test artifacts (set SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0 for auto-cleanup)."
            )
        else:
            _trash_files(live_provider, created_file_ids)
