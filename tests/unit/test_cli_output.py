import json

from dazzle.cli._output import format_output


def test_format_output_json():
    result = {"status": "ok", "count": 3}
    text = format_output(result, as_json=True)
    assert json.loads(text) == result


def test_format_output_text():
    result = {"status": "ok", "items": ["a", "b"]}
    text = format_output(result, as_json=False)
    assert "status: ok" in text
    assert "items:" in text


def test_format_output_nested_dict():
    result = {"meta": {"version": "1.0"}}
    text = format_output(result, as_json=False)
    assert "meta:" in text
    assert "version" in text


def test_format_output_empty():
    text = format_output({}, as_json=False)
    assert text == ""
