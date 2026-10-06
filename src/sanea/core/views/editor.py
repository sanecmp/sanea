"""Reusable class-based flow for progressively enhanced model editors."""

from abc import abstractmethod
from collections.abc import Callable
from typing import Generic, TypeVar

from django.forms import BaseForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.functional import Promise

from .base import ManagedView


ScopeT = TypeVar("ScopeT")
SelectedT = TypeVar("SelectedT")
FormT = TypeVar("FormT", bound=BaseForm)


class ModelEditorView(ManagedView, Generic[ScopeT, SelectedT, FormT]):
    """Share the HTML and siteajax lifecycle of list-and-editor pages."""

    page_title: str | Promise
    section: str
    editor_id: str
    editor_template: str
    reference_name: str
    selected_context_name: str
    form_context_name: str
    url_context_name: str
    saved_message: str | Promise
    add_trigger: str | None = None
    edit_trigger: str | None = None
    save_trigger: str | None = None
    cancel_trigger: str | None = None

    def get_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return common editor triggers and specialized handlers."""
        handlers = {
            trigger: handler
            for trigger, handler in (
                (self.add_trigger, self.render_editor),
                (self.edit_trigger, self.render_editor),
                (self.save_trigger, self.save_editor),
                (self.cancel_trigger, self.close_editor),
            )
            if trigger is not None
        }
        handlers.update(self.get_extra_ajax_handlers())
        return handlers

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Handle the non-JavaScript editor flow."""
        scope = self.get_scope(**kwargs)
        selected = None
        form = None

        if request.method == "POST":
            selected, form = self.build_form(request, scope)

            if form.is_submitted and form.is_valid():
                saved = self.save_form(form, selected, scope)
                return redirect(self.get_success_url(saved, scope))

        elif request.GET.get(self.reference_name):
            selected, form = self.build_form(request, scope)

        return self.render_page(request, scope, selected, form)

    def render_editor(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render only the requested editor fragment."""
        scope = self.get_scope(**kwargs)
        selected, form = self.build_form(request, scope)
        return self.render_editor_response(request, scope, selected, form)

    def save_editor(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Validate an AJAX submission and render its incremental result."""
        scope = self.get_scope(**kwargs)
        selected, form = self.build_form(request, scope)

        if not form.is_submitted or not form.is_valid():
            return self.render_editor_response(request, scope, selected, form)

        saved = self.save_form(form, selected, scope)
        redirect_url = self.get_ajax_redirect_url(saved, scope)

        if redirect_url is not None:
            return HttpResponse(status=204, headers={"HX-Redirect": redirect_url})

        return self.render_saved_response(request, scope, self.saved_message)

    def close_editor(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Close an AJAX editor without changing state."""
        return HttpResponse()

    def render_page(
        self,
        request: HttpRequest,
        scope: ScopeT,
        selected: SelectedT | None,
        form: FormT | None,
    ) -> HttpResponse:
        """Render the common editor page with view-specific context."""
        context = self.build_page_context(request, scope, selected, form)
        return render(request, "sanea/editor_index.html", context)

    def build_page_context(
        self,
        request: HttpRequest,
        scope: ScopeT,
        selected: SelectedT | None,
        form: FormT | None,
    ) -> dict[str, object]:
        """Build the common editor-page context for specialized renderers."""
        context = self.get_scope_context(scope)
        context.update(self.get_list_context(scope))
        context.update(
            {
                "page_title": self.page_title,
                "section": self.section,
                "editor_id": self.editor_id,
                "editor_form": form,
                self.selected_context_name: selected,
                self.form_context_name: form,
                self.url_context_name: self.get_success_url(selected, scope),
            }
        )
        context.update(self.get_page_context(request, scope, selected, form))
        return context

    def render_editor_response(
        self,
        request: HttpRequest,
        scope: ScopeT,
        selected: SelectedT | None,
        form: FormT,
    ) -> HttpResponse:
        """Render the shared context contract of one editor fragment."""
        context = self.get_scope_context(scope)
        context.update(
            {
                self.selected_context_name: selected,
                self.form_context_name: form,
            }
        )
        return render(request, self.editor_template, context)

    def render_saved_response(
        self,
        request: HttpRequest,
        scope: ScopeT,
        message: str | Promise,
    ) -> HttpResponse:
        """Render the shared saved marker and an out-of-band list update."""
        context = self.get_scope_context(scope)
        context.update(self.get_list_context(scope))
        context.update(
            {
                "section": self.section,
                "list_oob": True,
                "message": message,
            }
        )
        return render(request, "sanea/_saved.html", context)

    def get_extra_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Return additional trigger handlers for a specialized editor."""
        return {}

    def get_page_context(
        self,
        request: HttpRequest,
        scope: ScopeT,
        selected: SelectedT | None,
        form: FormT | None,
    ) -> dict[str, object]:
        """Return optional context used only by the complete page."""
        return {}

    def get_ajax_redirect_url(
        self,
        saved: SelectedT,
        scope: ScopeT,
    ) -> str | None:
        """Return a redirect when saving moved an object outside this scope."""
        return None

    @abstractmethod
    def get_scope(self, **kwargs: object) -> ScopeT:
        """Resolve immutable parent objects for one request."""

    @abstractmethod
    def build_form(
        self,
        request: HttpRequest,
        scope: ScopeT,
    ) -> tuple[SelectedT | None, FormT]:
        """Resolve the selected object and construct its form."""

    @abstractmethod
    def save_form(
        self,
        form: FormT,
        selected: SelectedT | None,
        scope: ScopeT,
    ) -> SelectedT:
        """Persist one validated form through the model API."""

    @abstractmethod
    def get_scope_context(self, scope: ScopeT) -> dict[str, object]:
        """Return parent objects shared by all templates."""

    @abstractmethod
    def get_list_context(self, scope: ScopeT) -> dict[str, object]:
        """Return the replaceable list fragment context."""

    @abstractmethod
    def get_success_url(
        self,
        selected: SelectedT | None,
        scope: ScopeT,
    ) -> str:
        """Return the canonical page URL after saving."""
