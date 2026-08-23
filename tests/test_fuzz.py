from __future__ import annotations

import json
from typing import Any

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from runproof_engine import format_traceparent, parse_traceparent
from runproof_engine.utils import safe_value

json_scalars = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=80))
json_values = st.recursive(
    json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=8),
        st.dictionaries(st.text(max_size=30), children, max_size=8),
        st.tuples(children, children),
    ),
    max_leaves=40,
)


@settings(max_examples=100, deadline=None)
@given(json_values)
def test_safe_value_always_returns_bounded_json(value: Any) -> None:
    bounded = safe_value(value, max_items=20, max_text=80)
    encoded = json.dumps(bounded, ensure_ascii=False)
    assert len(encoded) < 100_000


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=200))
def test_traceparent_parser_never_raises_on_arbitrary_text(value: str) -> None:
    parsed = parse_traceparent(value)
    assert parsed is None or len(parsed) == 3


def test_traceparent_fuzz_seed_round_trip() -> None:
    header = format_traceparent("0123456789abcdef0123456789abcdef", "0123456789abcdef")
    assert parse_traceparent(header) == (
        "0123456789abcdef0123456789abcdef",
        "0123456789abcdef",
        1,
    )
