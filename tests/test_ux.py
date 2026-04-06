from __future__ import annotations

from prompt_polisher.ux import (
    build_bounded_splash_body,
    splash_inner_width,
    splash_main_body,
    splash_prompt_line_count,
)


def test_splash_inner_width_clamped() -> None:
    assert splash_inner_width(80) == 72
    assert splash_inner_width(200) == 120
    assert splash_inner_width(50) == 42
    assert splash_inner_width(10) == 40


def test_splash_prompt_line_count() -> None:
    assert splash_prompt_line_count("") == 0
    assert splash_prompt_line_count("a") == 1
    assert splash_prompt_line_count("a\nb") == 2


def test_build_bounded_no_truncation() -> None:
    body, truncated = build_bounded_splash_body("hello", console_width=80)
    assert body == "hello"
    assert truncated is False


def test_build_bounded_truncates_long_line() -> None:
    inner = splash_inner_width(50)
    long_line = "x" * (inner + 10)
    body, truncated = build_bounded_splash_body(long_line, console_width=50)
    assert truncated is True
    assert len(body) <= inner
    assert body.endswith("...")


def test_build_bounded_more_than_four_lines() -> None:
    raw = "\n".join(f"line{i}" for i in range(6))
    body, truncated = build_bounded_splash_body(raw, console_width=80)
    assert truncated is True
    assert body.count("\n") == 3
    assert "line0" in body
    assert "line3" in body
    assert "line5" not in body


def test_splash_main_body_verbose_returns_full() -> None:
    raw = "a\n" * 10
    body, truncated = splash_main_body(raw, verbose=True, console_width=80)
    assert body == raw
    assert truncated is False


def test_splash_main_body_non_verbose_uses_bounded() -> None:
    raw = "\n".join(f"line{i}" for i in range(6))
    body, truncated = splash_main_body(raw, verbose=False, console_width=80)
    assert truncated is True
    assert "line5" not in body
