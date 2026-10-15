"""Local account management views."""

from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import AccountForm
from ..models import Account
from .editor import ModelEditorView


class AccountsView(ModelEditorView[None, Account, AccountForm]):
    """List reported accounts and edit sanea-owned settings."""

    page_title = _("Accounts")
    section = "accounts"
    dialog_fallback = "accounts-heading"
    editor_id = "account-editor"
    editor_template = "sanea/accounts/_editor.html"
    reference_name = "account"
    selected_context_name = "account"
    form_context_name = "account_form"
    url_context_name = "accounts_url"
    saved_message = _("Account settings saved.")
    edit_trigger = "account-edit-*"
    save_trigger = "account-save"
    cancel_trigger = "account-cancel"

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[Account, AccountForm]:
        """Build a form for the requested reported account."""
        account = self.get_requested_account(request)
        form = AccountForm(
            request=request,
            src="POST",
            prefix="account",
            instance=account,
            render_form_tag=False,
        )
        return account, form

    def save_form(
        self,
        form: AccountForm,
        selected: Account | None,
        scope: None,
    ) -> Account:
        """Persist account settings through the model API."""
        return Account.save_form(form)

    def get_scope_context(self, scope: None) -> dict[str, object]:
        """Return the empty top-level context."""
        return {}

    def get_list_context(self, scope: None) -> dict[str, object]:
        """Return accounts with their editor dependencies."""
        return {"accounts": self.get_accounts()}

    def get_success_url(
        self,
        selected: Account | None,
        scope: None,
    ) -> str:
        """Return the accounts index URL."""
        return reverse("core:accounts")

    def get_requested_account(self, request: HttpRequest) -> Account:
        """Resolve the account reference from either request method."""
        reference = request.POST.get("account", request.GET.get("account", ""))
        return get_object_or_404(self.get_accounts(), pk=reference)

    def get_accounts(self) -> QuerySet[Account]:
        """Return accounts with all data required by their list and editor."""
        return Account.objects.select_related("computer", "person", "limits")


accounts = AccountsView().as_view()
