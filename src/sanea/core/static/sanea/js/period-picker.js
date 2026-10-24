"use strict";

(() => {
    const dateSelector = "input[data-period-date]";
    const destroyDate = (field) => {
        field._flatpickr?.destroy();
        delete field._flatpickr;
    };
    const selectDay = (field) => {
        if (field.value) {
            const period = field.form?.elements.namedItem(field.dataset.periodField);
            if (period) {
                period.value = "day";
            }
        }
    };
    const initializeDate = (field) => {
        if (!window.flatpickr || field._flatpickr) {
            return;
        }
        selectDay(field);
        const language = document.documentElement.lang.split("-")[0];
        const period = field.form.elements.namedItem(field.dataset.periodField);
        const presets = JSON.parse(field.dataset.periodPresets);
        const labels = Array.from(field.labels || [], (label) => ({label, target: label.htmlFor}));
        const showPeriod = (instance) => {
            const preset = presets.find((item) => item.value === period.value);
            if (preset) {
                instance.altInput.value = preset.label;
            }
            instance.calendarContainer.querySelectorAll("[data-period-preset]").forEach((button) => {
                button.setAttribute("aria-pressed", `${button.dataset.periodPreset === period.value}`);
            });
        };
        window.flatpickr(field, {
            dateFormat: "Y-m-d",
            altInput: true,
            altFormat: "Y-m-d",
            disableMobile: true,
            // Keep the calendar's month controls out of generic searchable selects.
            monthSelectorType: "static",
            ariaDateFormat: "j F Y",
            locale: window.flatpickr.l10ns[language] || "default",
            onReady: (_dates, _value, instance) => {
                instance.altInput.id = `${field.id}-display`;
                labels.forEach(({label}) => { label.htmlFor = instance.altInput.id; });
                const shortcuts = document.createElement("div");
                shortcuts.className = "sanea-period-presets";
                presets.forEach((preset) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "btn btn-sm btn-light";
                    button.textContent = preset.label;
                    button.dataset.periodPreset = preset.value;
                    button.addEventListener("click", () => {
                        period.value = preset.value;
                        instance.clear(false);
                        instance.close();
                        showPeriod(instance);
                        field.dispatchEvent(new Event("change", {bubbles: true}));
                    });
                    shortcuts.appendChild(button);
                });
                instance.calendarContainer.appendChild(shortcuts);
                showPeriod(instance);
            },
            onChange: (_dates, _value, instance) => {
                selectDay(field);
                showPeriod(instance);
            },
            onDestroy: () => labels.forEach(({label, target}) => { label.htmlFor = target; }),
        });
    };
    const initialize = (root) => {
        if (root.matches?.(dateSelector)) {
            initializeDate(root);
        }
        root.querySelectorAll(dateSelector).forEach(initializeDate);
    };

    document.addEventListener("DOMContentLoaded", () => initialize(document));
    document.addEventListener("htmx:load", (event) => initialize(event.detail.elt));
    document.addEventListener("change", (event) => {
        if (event.target.matches?.(dateSelector)) {
            selectDay(event.target);
        }
    }, true);
    document.addEventListener("htmx:beforeCleanupElement", (event) => destroyDate(event.detail.elt));
    document.addEventListener("htmx:beforeHistorySave", (event) => {
        const fields = Array.from(event.detail.historyElt.querySelectorAll(dateSelector));
        fields.forEach((field) => {
            destroyDate(field);
            field.setAttribute("value", field.value);
            const period = field.form.elements.namedItem(field.dataset.periodField);
            period.setAttribute("value", period.value);
        });
        queueMicrotask(() => fields.filter((field) => field.isConnected).forEach(initializeDate));
    });
    document.addEventListener("htmx:historyRestore", () => {
        const query = new URLSearchParams(window.location.search);
        document.querySelectorAll(dateSelector).forEach((field) => {
            // The outgoing form may already contain the next request's selection.
            // The restored URL, not that cached input value, identifies this report.
            destroyDate(field);
            const period = field.form.elements.namedItem(field.dataset.periodField);
            field.value = query.get(field.name) || "";
            period.value = query.get(period.name) || field.dataset.periodDefault;
            initializeDate(field);
        });
    });
})();
