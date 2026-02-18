import types

import pytest

from slideflow.core.registry import (
    ClassRegistry,
    FunctionRegistry,
    ProviderRegistry,
    create_class_registry,
    create_function_registry,
    create_provider_registry,
)
from slideflow.presentations.positioning import (
    apply_alignment,
    compute_chart_dimensions,
    convert_dimensions,
    safe_eval_expression,
)
from slideflow.utilities.exceptions import ChartGenerationError, ProviderError


def test_safe_eval_expression_accepts_arithmetic_and_rejects_unsafe_nodes():
    assert safe_eval_expression("10") == 10
    assert safe_eval_expression("10.5") == 10.5
    assert safe_eval_expression("(10 + 5) * 2") == 30
    assert safe_eval_expression("20 / 4") == 5.0

    with pytest.raises(ChartGenerationError, match="Expression cannot be empty"):
        safe_eval_expression("")
    with pytest.raises(ChartGenerationError, match="Invalid expression syntax"):
        safe_eval_expression("1 +")
    with pytest.raises(ChartGenerationError, match="Division by zero"):
        safe_eval_expression("1 / 0")
    with pytest.raises(ChartGenerationError, match="Unsupported AST node type"):
        safe_eval_expression("__import__('os')")
    with pytest.raises(ChartGenerationError, match="Result too large"):
        safe_eval_expression("9999999999 * 2")


def test_convert_dimensions_supports_pt_emu_relative_and_errors():
    assert convert_dimensions("50 + 25", "100", "400", "300", "pt") == (75, 100, 400, 300)
    assert convert_dimensions(635000, 1270000, 5080000, 3810000, "emu") == (50, 100, 400, 300)
    assert convert_dimensions("5 * 10", "4 * 10", "20 * 10", "15 * 10", "expression") == (50, 40, 200, 150)

    slides_app = {
        "pageSize": {
            "width": {"magnitude": 9144000, "unit": "EMU"},   # 720 pt
            "height": {"magnitude": 6858000, "unit": "EMU"},  # 540 pt
        }
    }
    assert convert_dimensions(0.1, 0.2, 0.5, 0.4, "relative", slides_app) == (72, 108, 360, 216)

    with pytest.raises(ChartGenerationError, match="slides_app must be provided"):
        convert_dimensions(0.1, 0.2, 0.5, 0.4, "relative", None)
    with pytest.raises(ChartGenerationError, match="Unsupported dimensions_format"):
        convert_dimensions(1, 2, 3, 4, "pixels")


def test_alignment_and_dimension_computation_validation_paths():
    assert apply_alignment(10, 20, 300, 100, "center-top", 720, 540) == (220, 20)
    assert apply_alignment(50, 30, 200, 150, "right-bottom", 720, 540) == (470, 360)
    assert apply_alignment(5, 7, 100, 100, "left-center", 720, 540) == (5, 227)

    with pytest.raises(ChartGenerationError, match="Invalid alignment format"):
        apply_alignment(0, 0, 100, 100, "center", 720, 540)
    with pytest.raises(ChartGenerationError, match="Invalid horizontal alignment"):
        apply_alignment(0, 0, 100, 100, "middle-top", 720, 540)
    with pytest.raises(ChartGenerationError, match="Invalid vertical alignment"):
        apply_alignment(0, 0, 100, 100, "left-middle", 720, 540)

    assert compute_chart_dimensions(
        x="50 + 10",
        y="20",
        width=300,
        height=200,
        dimensions_format="pt",
        alignment_format="center-top",
        page_width_pt=720,
        page_height_pt=540,
    ) == (270, 20, 300, 200)

    with pytest.raises(ChartGenerationError, match="must be positive"):
        compute_chart_dimensions(0, 0, 0, 100)
    with pytest.raises(ChartGenerationError, match="too large"):
        compute_chart_dimensions(0, 0, 2000, 100)
    with pytest.raises(ChartGenerationError, match="too far from slide"):
        compute_chart_dimensions(3000, 0, 100, 100, page_width_pt=720, page_height_pt=540)


def test_function_registry_supports_registration_call_module_loading_and_errors():
    registry = create_function_registry("unit_funcs")
    registry.register_function("add", lambda x, y: x + y)
    assert registry.call("add", 2, 3) == 5
    assert registry.get_optional("missing", default="x") == "x"
    assert registry.has("add") is True
    assert "add" in registry
    assert len(registry) == 1
    assert registry.size() == 1
    assert "unit_funcs" in repr(registry)

    with pytest.raises(TypeError, match="must be callable"):
        registry.register_function("bad", 123)
    with pytest.raises(ValueError, match="already registered"):
        registry.register_function("add", lambda x, y: x - y)

    mod = types.ModuleType("temp_mod")

    def public_fn():
        return "ok"

    def _private_fn():
        return "hidden"

    mod.public_fn = public_fn
    mod._private_fn = _private_fn
    registry.register_module_functions(mod, prefix="m_")
    assert registry.call("m_public_fn") == "ok"
    with pytest.raises(KeyError):
        registry.get("m__private_fn")

    # Trigger call error path.
    registry.register_function("explode", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        registry.call("explode")

    removed = registry.remove("add")
    assert callable(removed)
    with pytest.raises(KeyError):
        registry.remove("add")

    registry.clear()
    assert registry.list_available() == []
    assert registry.items() == {}


def test_class_and_provider_registry_behavior_and_factory_helpers():
    class Base:
        def __init__(self, value=0):
            self.value = value

    class Impl(Base):
        pass

    class NotBase:
        pass

    class_registry = create_class_registry("classes", Base)
    class_registry.register_class("impl", Impl)
    assert isinstance(class_registry.get_class("impl"), type)
    assert class_registry.create_instance("impl", value=7).value == 7

    with pytest.raises(TypeError, match="must be a class"):
        class_registry.register_class("not-class", 123)
    with pytest.raises(TypeError, match="must inherit"):
        class_registry.register_class("notbase", NotBase)

    provider_registry = create_provider_registry("providers", Base)
    provider_registry.register_class("impl", Impl)
    instance = provider_registry.create_provider("impl", value=3)
    assert isinstance(instance, Impl)
    assert instance.value == 3

    with pytest.raises(ProviderError, match="Unknown provider"):
        provider_registry.get_provider_class("missing")
    with pytest.raises(ProviderError, match="Failed to create provider"):
        provider_registry.create_provider("missing")

    class Exploding(Impl):
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("ctor failed")

    provider_registry.register_class("exploding", Exploding)
    with pytest.raises(ProviderError, match="Failed to create provider"):
        provider_registry.create_provider("exploding")

    # Direct constructors should remain available and typed.
    assert isinstance(FunctionRegistry("f"), FunctionRegistry)
    assert isinstance(ClassRegistry("c"), ClassRegistry)
    assert isinstance(ProviderRegistry("p"), ProviderRegistry)
