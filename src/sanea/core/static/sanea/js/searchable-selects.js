(() => {
    const initializeSelect = (select) => {
        if (!window.TomSelect || select.tomselect || select.options.length < 10) {
            return;
        }
        const searchLabel = document.body.dataset.selectSearch;
        const labels = Array.from(select.labels, (label) => ({ label, target: label.htmlFor }));
        new window.TomSelect(select, {
            plugins: ["dropdown_input"],
            dropdownParent: "body",
            allowEmptyOption: true,
            create: false,
            maxOptions: null,
            onInitialize() {
                this.control_input.placeholder = searchLabel;
                this.control_input.setAttribute("aria-label", searchLabel);
                this.on("destroy", () => labels.forEach(({ label, target }) => { label.htmlFor = target; }));
            },
            render: {
                no_results() {
                    const message = document.createElement("div");
                    message.className = "no-results";
                    message.textContent = document.body.dataset.selectEmpty;
                    return message;
                },
            },
        });
    };

    const initialize = (root) => {
        if (root.matches?.("select")) {
            initializeSelect(root);
        }
        root.querySelectorAll("select").forEach(initializeSelect);
    };

    document.addEventListener("DOMContentLoaded", () => initialize(document));
    document.addEventListener("htmx:load", (event) => initialize(event.detail.elt));
    document.addEventListener("htmx:beforeCleanupElement", (event) => event.detail.elt.tomselect?.destroy());
    document.addEventListener("htmx:beforeHistorySave", (event) => {
        const selects = Array.from(event.detail.historyElt.querySelectorAll("select")).filter((select) => select.tomselect);
        selects.forEach((select) => {
            const options = Array.from(select.childNodes);
            const selected = Array.from(select.selectedOptions, (option) => option.value);
            select.tomselect.destroy();
            select.replaceChildren(...options);
            Array.from(select.options).forEach((option) => { option.selected = selected.includes(option.value); });
        });
        // HTMX snapshots synchronously. Rebuild surviving controls, not the unsettled response DOM.
        queueMicrotask(() => selects.filter((select) => select.isConnected).forEach(initializeSelect));
    });
    document.addEventListener("sanea:choices-updated", (event) => {
        const select = event.target;
        if (select.tomselect) {
            // sync() adds options without dropping removed or renamed cached entries.
            select.tomselect.clearOptions(() => false);
            select.tomselect.sync();
        } else {
            initializeSelect(select);
        }
    });
})();
