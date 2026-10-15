"""People management views."""

from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..forms import PersonForm
from ..models import Person
from .editor import ModelEditorView


class PeopleView(ModelEditorView[None, Person, PersonForm]):
    """List people and edit their names."""

    page_title = _("People")
    section = "people"
    page_template = "sanea/people/index.html"
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
        ).annotate(account_count=Count("accounts")).prefetch_related("accounts__computer")
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
