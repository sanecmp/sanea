"""People management views."""

from collections.abc import Callable

from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import PersonForm, TemplatePropagationForm
from ..models import Person
from .editor import ModelEditorView


class PeopleView(ModelEditorView[None, Person, PersonForm]):
    """List people, edit them, and explicitly distribute their templates."""

    page_title = _("People")
    section = "people"
    editor_id = "person-editor"
    editor_template = "sanea/people/_editor.html"
    reference_name = "person"
    selected_context_name = "person"
    form_context_name = "person_form"
    url_context_name = "people_url"
    saved_message = _("Person saved.")
    add_trigger = "person-add"
    edit_trigger = "person-edit-*"
    save_trigger = "person-save"
    cancel_trigger = "person-cancel"

    def dispatch(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Handle editing and non-JavaScript template distribution."""

        if request.method == "POST" and request.POST.get("propagate_template"):
            person = self.get_requested_person(request)

            if person is None:
                return HttpResponse(status=404)

            form = self.build_propagation_form(request, person)

            if form.is_submitted and form.is_valid():
                person.propagate_template(form.cleaned_data["accounts"])
                return redirect("core:people")

            return self.render_propagation_page(request, person, form)

        if request.GET.get("propagate"):
            person = self.get_requested_person(request)

            if person is None:
                return HttpResponse(status=404)

            form = self.build_propagation_form(request, person)
            return self.render_propagation_page(request, person, form)

        return super().dispatch(request, **kwargs)

    def get_extra_ajax_handlers(self) -> dict[str, Callable[..., HttpResponse]]:
        """Add template-distribution and its close handlers."""
        return {
            "person-propagate-*": self.render_propagation,
            "person-propagate-save": self.apply_propagation,
            "person-propagate-cancel": self.close_editor,
        }

    def render_propagation(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Render the template-distribution fragment."""
        person = self.get_requested_person(request)

        if person is None:
            return HttpResponse(status=404)

        form = self.build_propagation_form(request, person)
        return self.render_propagation_response(request, person, form)

    def apply_propagation(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        """Validate and distribute one person's template."""
        person = self.get_requested_person(request)

        if person is None:
            return HttpResponse(status=404)

        form = self.build_propagation_form(request, person)

        if not form.is_submitted or not form.is_valid():
            return self.render_propagation_response(request, person, form)

        count = person.propagate_template(form.cleaned_data["accounts"])
        message = f"{_("Accounts updated:")} {count}."
        return self.render_saved_response(request, None, message)

    def render_propagation_page(
        self,
        request: HttpRequest,
        person: Person,
        form: TemplatePropagationForm,
    ) -> HttpResponse:
        """Render template distribution in the complete editor page."""
        context = self.build_page_context(request, None, person, None)
        context.update({"editor_form": form, "propagation_form": form})
        return render(request, "sanea/editor_index.html", context)

    def render_propagation_response(
        self,
        request: HttpRequest,
        person: Person,
        form: TemplatePropagationForm,
    ) -> HttpResponse:
        """Render the template-distribution fragment with validation errors."""
        return render(
            request,
            "sanea/people/_propagate.html",
            {"person": person, "propagation_form": form},
        )

    def get_scope(self, **kwargs: object) -> None:
        """Return the empty top-level scope."""

    def build_form(
        self,
        request: HttpRequest,
        scope: None,
    ) -> tuple[Person | None, PersonForm]:
        """Build a person form for creation or editing."""
        person = self.get_requested_person(request)
        form = PersonForm(
            request=request,
            src="POST",
            prefix="person",
            instance=person,
            render_form_tag=False,
        )
        return person, form

    def build_propagation_form(
        self,
        request: HttpRequest,
        person: Person,
    ) -> TemplatePropagationForm:
        """Build a template-distribution form for one person."""
        return TemplatePropagationForm(
            request=request,
            src="POST",
            prefix="propagation",
            person=person,
            render_form_tag=False,
        )

    def save_form(
        self,
        form: PersonForm,
        selected: Person | None,
        scope: None,
    ) -> Person:
        """Persist one validated person form."""
        return form.save()

    def get_scope_context(self, scope: None) -> dict[str, object]:
        """Return the empty top-level context."""
        return {}

    def get_list_context(self, scope: None) -> dict[str, object]:
        """Return people with their template and account summary."""
        people: QuerySet[Person] = Person.objects.select_related(
            "limits_tpl__current_limits"
        ).annotate(account_count=Count("accounts"))
        return {"people": people}

    def get_success_url(
        self,
        selected: Person | None,
        scope: None,
    ) -> str:
        """Return the people index URL."""
        return reverse("core:people")

    def get_requested_person(self, request: HttpRequest) -> Person | None:
        """Resolve the optional person reference from either request method."""
        reference = request.POST.get("person", request.GET.get("person", ""))

        if not reference or reference == "new":
            return None

        return get_object_or_404(Person, pk=reference)


people = PeopleView().as_view()
