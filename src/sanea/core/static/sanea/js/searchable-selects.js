(() => {
    const selector = "select, input[data-select-suggestions]";

    const initializeControl = (control) => {
        const freeText = control.matches("input[data-select-suggestions]");
        if (!window.TomSelect || control.tomselect
            || (!freeText && control.dataset.selectSearch !== "always" && control.options.length < 10)) {
            return;
        }
        const searchLabel = document.body.dataset.selectSearch;
        const labels = Array.from(control.labels, (label) => ({ label, target: label.htmlFor }));
        const settings = {
            // Editable names use the control itself; a second search input would commit
            // a partial name on blur before a suggestion's click is handled.
            plugins: freeText ? [] : ["dropdown_input"],
            // Keep the search inside the dialog's focus trap.
            dropdownParent: control.closest("[data-editor-dialog]") ? null : "body",
            allowEmptyOption: true,
            create: false,
            maxOptions: null,
            onInitialize() {
                if (!freeText) {
                    this.control_input.placeholder = searchLabel;
                    this.control_input.setAttribute("aria-label", searchLabel);
                }
                if (control.maxLength > 0) {
                    this.control_input.maxLength = control.maxLength;
                }
                this.on("destroy", () => labels.forEach(({ label, target }) => { label.htmlFor = target; }));
            },
            render: {
                no_results() {
                    const message = document.createElement("div");
                    message.className = "no-results";
                    message.textContent = document.body.dataset.selectEmpty;
                    return message;
                },
                option_create(data) {
                    const option = document.createElement("div");
                    option.className = "create";
                    option.textContent = `${control.dataset.selectCreateLabel} ${data.input}`;
                    return option;
                },
            },
        };
        if (freeText) {
            const values = JSON.parse(control.dataset.selectSuggestions);
            if (control.value && !values.includes(control.value)) {
                values.push(control.value);
            }
            Object.assign(settings, {
                options: values.map((value) => ({ value, text: value })),
                items: control.value ? [control.value] : [],
                maxItems: 1,
                // A process name is one value, even when pasted with a comma.
                splitOn: /(?!)/,
                allowEmptyOption: false,
                create: true,
                // Clicking Save must retain a manually typed name, not just list selections.
                createOnBlur: true,
            });
        }
        new window.TomSelect(control, settings);
    };

    const initialize = (root) => {
        if (root.matches?.("select") || root.matches?.("input[data-select-suggestions]")) {
            initializeControl(root);
        }
        root.querySelectorAll(selector).forEach(initializeControl);
    };

    document.addEventListener("DOMContentLoaded", () => initialize(document));
    document.addEventListener("htmx:load", (event) => initialize(event.detail.elt));
    document.addEventListener("sanea:form-added", (event) => initialize(event.target));
    document.addEventListener("htmx:beforeCleanupElement", (event) => event.detail.elt.tomselect?.destroy());
    document.addEventListener("htmx:beforeHistorySave", (event) => {
        const controls = Array.from(event.detail.historyElt.querySelectorAll(selector)).filter((control) => control.tomselect);
        controls.forEach((control) => {
            if (control.matches("select")) {
                const options = Array.from(control.childNodes);
                const selected = Array.from(control.selectedOptions, (option) => option.value);
                control.tomselect.destroy();
                control.replaceChildren(...options);
                Array.from(control.options).forEach((option) => { option.selected = selected.includes(option.value); });
            } else {
                const value = control.value;
                control.tomselect.destroy();
                control.value = value;
                control.setAttribute("value", value);
            }
        });
        // HTMX snapshots synchronously. Rebuild surviving controls, not the unsettled response DOM.
        queueMicrotask(() => controls.filter((control) => control.isConnected).forEach(initializeControl));
    });
    document.addEventListener("sanea:choices-updated", (event) => {
        const select = event.target;
        if (select.tomselect) {
            // sync() adds options without dropping removed or renamed cached entries.
            select.tomselect.clearOptions(() => false);
            select.tomselect.sync();
        } else {
            initializeControl(select);
        }
    });
})();
