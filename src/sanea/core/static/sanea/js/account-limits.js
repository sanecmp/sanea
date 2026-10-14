(() => {
    const initialize = () => {
        const form = document.getElementById("account-limits-form");
        if (!form) {
            return;
        }
        let hasDraftChanges = false;

        const synchronizeRules = () => {
            const sessions = Array.from(form.querySelectorAll('[data-formset="sessions"] [data-form-row]'));
            const choices = sessions.filter((row) => !row.hidden && !row.querySelector('input[name$="-DELETE"]').checked)
                .map((row) => ({
                    value: row.dataset.formPrefix.slice("sessions-".length),
                    label: row.querySelector('input[name$="-name"]').value.trim() || form.dataset.newPresetLabel,
                }));

            form.querySelectorAll('select[name$="-rule"]').forEach((select) => {
                const selected = select.value;
                const placeholder = select.options[0]?.textContent || "";
                const options = [{value: "", label: placeholder}, ...choices].map((choice) => {
                    const option = document.createElement("option");
                    option.value = choice.value;
                    option.textContent = choice.label;
                    return option;
                });
                select.replaceChildren(...options);
                select.value = choices.some((choice) => choice.value === selected) ? selected : "";
                select.dispatchEvent(new CustomEvent("sanea:choices-updated", { bubbles: true }));
            });
        };

        const initializeRow = (row) => {
            const discarded = row.querySelector('input[name$="-DELETE"]').checked;
            row.classList.toggle("is-removed", discarded);
            if (discarded) {
                row.hidden = true;
            }
            const button = row.querySelector("[data-discard-form]");
            if (button) {
                button.hidden = false;
            }
        };

        form.querySelectorAll("[data-form-row]").forEach(initializeRow);
        form.querySelectorAll("[data-formset]").forEach((formset) => {
            const prefix = formset.dataset.formset;
            const initial = Number(formset.querySelector(`input[name="${prefix}-INITIAL_FORMS"]`).value);
            if (initial > 0) {
                formset.querySelectorAll("[data-extra-row]").forEach((row) => { row.hidden = true; });
            }
        });
        form.querySelectorAll("[data-add-form]").forEach((button) => { button.hidden = false; });
        synchronizeRules();

        document.querySelectorAll("[data-rule-deletion]").forEach((removal) => {
            removal.addEventListener("submit", (event) => {
                const confirmed = removal.querySelector('input[name="confirmed"]');
                const emptySchedule = removal.querySelector('input[name="confirm_empty_schedule"]');
                confirmed.value = "";
                emptySchedule.value = "";
                const message = removal.dataset.confirmation
                    + (hasDraftChanges ? `\n\n${form.dataset.discardNotice}` : "");
                if (!window.confirm(message)) {
                    event.preventDefault();
                    return;
                }
                confirmed.value = "on";
                if (removal.hasAttribute("data-blocks-sessions")) {
                    emptySchedule.value = "on";
                }
            });
        });

        form.addEventListener("click", (event) => {
            const discard = event.target.closest("[data-discard-form]");
            if (discard) {
                const row = discard.closest("[data-form-row]");
                row.querySelector('input[name$="-DELETE"]').checked = true;
                initializeRow(row);
                hasDraftChanges = true;
                synchronizeRules();
                return;
            }

            const button = event.target.closest("[data-add-form]");
            if (!button) {
                return;
            }
            const formset = button.closest("[data-formset]");
            const prefix = formset.dataset.formset;
            let row = formset.querySelector("[data-extra-row][hidden]:not(.is-removed)");
            if (row) {
                row.hidden = false;
            } else {
                const total = formset.querySelector(`input[name="${prefix}-TOTAL_FORMS"]`);
                const template = document.createElement("template");
                template.innerHTML = formset.querySelector("[data-empty-form]").innerHTML
                    .replaceAll("__prefix__", total.value);
                row = template.content.firstElementChild;
                formset.querySelector("[data-form-rows]").append(row);
                total.value = `${Number(total.value) + 1}`;
            }
            initializeRow(row);
            hasDraftChanges = true;
            synchronizeRules();
            row.querySelector('input:not([type="hidden"]):not([type="checkbox"]), select')?.focus();
        });

        form.addEventListener("change", (event) => {
            hasDraftChanges = true;
        });
        form.addEventListener("input", (event) => {
            hasDraftChanges = true;
            if (event.target.name?.startsWith("sessions-") && event.target.name.endsWith("-name")) {
                synchronizeRules();
            }
        });

        const hasVisibleErrors = (container) => Array.from(container.querySelectorAll("[data-limits-error]"))
            .some((error) => !error.closest("[data-form-row]")?.classList.contains("is-removed"));
        form.querySelectorAll("details").forEach((details) => {
            if (hasVisibleErrors(details)) {
                details.open = true;
            }
        });
        if (window.bootstrap?.Tab) {
            const panels = Array.from(form.querySelectorAll("[data-limits-panel]"));
            const errorPanel = panels.find(hasVisibleErrors);
            document.getElementById("account-limits-tabs").hidden = false;
            document.getElementById("account-limits-panels").classList.add("tab-content");
            const panel = errorPanel || panels[0];
            window.bootstrap.Tab.getOrCreateInstance(document.getElementById(`${panel.id}-tab`)).show();
        }
    };

    document.addEventListener("DOMContentLoaded", initialize);
})();
