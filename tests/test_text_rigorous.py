from __future__ import annotations

from prompt_polisher.text import sanitize_user_input


def test_sanitize_task_context():
    # Basic tag
    assert sanitize_user_input("<task_context>") == "&lt;task_context&gt;"
    assert sanitize_user_input("</task_context>") == "&lt;/task_context&gt;"

    # Nested/Multiple
    input_text = "Before <task_context>Inside</task_context> After"
    expected = "Before &lt;task_context&gt;Inside&lt;/task_context&gt; After"
    assert sanitize_user_input(input_text) == expected


def test_sanitize_task_context_case_insensitive():
    assert sanitize_user_input("<TASK_CONTEXT>") == "&lt;task_context&gt;"
    assert sanitize_user_input("</Task_Context>") == "&lt;/task_context&gt;"


def test_sanitize_task_context_with_attributes():
    # Our current regex handles attributes via [^>]*
    assert sanitize_user_input("<task_context id='1'>") == "&lt;task_context&gt;"


def test_sanitize_no_effect_on_regular_text():
    assert sanitize_user_input("This is a <div> not escaped") == "This is a <div> not escaped"
    assert sanitize_user_input("Safe <input> tag") == "Safe <input> tag"


def test_sanitize_incomplete_tags():
    # The regex is <tag[^>]*>, so an unclosed tag might not trigger if there is
    # no closing bracket. But `<task_context ` followed by EOF or something is
    # safe because LLM won't parse it as XML boundary.
    assert sanitize_user_input("<task_context") == "<task_context"
