"""Tests for intentionally optional limits form fields."""

from sanea.core.forms import AppRuleForm, SessionRuleForm


def test_optional_quota_fields_are_not_marked_required() -> None:
    app_form = AppRuleForm()
    session_form = SessionRuleForm()

    assert app_form.fields["max_launches"].required is False
    assert app_form.fields["max_time"].required is False
    assert session_form.fields["max_sessions"].required is False
    assert session_form.fields["max_duration"].required is False
