"""Tests for utils/json_extract.py."""

import pytest

from utils.json_extract import JsonExtractionError, extract_json


def test_extract_clean_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_surrounding_text():
    text = 'Sure, here you go:\n```json\n{"a": 1, "b": "two"}\n```\nHope that helps!'
    assert extract_json(text) == {"a": 1, "b": "two"}


def test_extract_json_raises_on_no_json():
    with pytest.raises(JsonExtractionError):
        extract_json("no json here at all")
