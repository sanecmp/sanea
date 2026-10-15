"""Readable labels for local account selections."""

from django import forms

from ..models import Account


class AccountChoiceLabelMixin:
    """Identify an account by its familiar name and computer."""

    def label_from_instance(self, account: Account) -> str:
        """Avoid exposing internal identifiers in account selections."""
        return f"{account.get_display_name()} · {account.computer.get_display_name()}"


class AccountChoiceField(AccountChoiceLabelMixin, forms.ModelChoiceField):
    """Choose one local account."""


class AccountMultipleChoiceField(AccountChoiceLabelMixin, forms.ModelMultipleChoiceField):
    """Choose several local accounts."""
