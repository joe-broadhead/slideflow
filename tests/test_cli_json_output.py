import json
import math

from slideflow.cli.json_output import write_output_json


def test_write_output_json_normalizes_non_finite_values(tmp_path):
    output_file = tmp_path / "result.json"
    payload = {
        "nan_value": math.nan,
        "pos_inf": math.inf,
        "neg_inf": -math.inf,
        "nested": {
            "items": [1, math.nan, {"x": math.inf}],
        },
    }

    write_output_json(output_file, payload)
    data = json.loads(output_file.read_text(encoding="utf-8"))

    assert data["nan_value"] is None
    assert data["pos_inf"] is None
    assert data["neg_inf"] is None
    assert data["nested"]["items"][1] is None
    assert data["nested"]["items"][2]["x"] is None


def test_write_output_json_noop_when_path_missing():
    write_output_json(None, {"value": 1})
