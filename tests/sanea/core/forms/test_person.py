"""Person editing contains only a correctly translated name."""

from django.utils.translation import override

from sanea.core.forms import LimitsTemplateForm, PersonForm


def test_person_name_has_its_own_translation() -> None:

    with override("ru"):
        person_form = PersonForm()
        template_form = LimitsTemplateForm()

        assert f"{person_form.fields["name"].label}" == "Имя"
        assert f"{template_form.fields["name"].label}" == "Название"
        assert person_form.fields["name"].help_text == ""
        assert tuple(person_form.fields) == ("name",)
