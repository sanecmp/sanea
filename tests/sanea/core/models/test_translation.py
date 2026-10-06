"""Tests for sanea domain translations."""

from django.utils.translation import override

from sanea.core.models.account import Account
from sanea.core.models.choices import ComputerStatus
from sanea.core.models.computer import Computer


def test_domain_model_text_has_russian_translation() -> None:

    with override("ru"):
        assert f"{Account._meta.verbose_name}" == "Учётная запись"
        assert f"{Account._meta.get_field("collect").verbose_name}" == "Собирать события"
        assert (
            f"{Computer._meta.get_field("timezone").help_text}"
            == "Часовой пояс IANA для расчёта недельных расписаний."
        )
        assert f"{ComputerStatus.PENDING.label}" == "Ожидает подтверждения"
