"use strict";

(() => {
    if (!window.bootstrap?.Modal) {
        return;
    }

    document.querySelectorAll("[data-editor-dialog]").forEach((dialog) => {
        const editor = dialog.querySelector("[data-dialog-editor]");
        if (!editor) {
            return;
        }

        dialog.classList.add("modal");
        const modal = window.bootstrap.Modal.getOrCreateInstance(dialog);
        let returnFocusId = dialog.dataset.dialogFallback;
        let requestSource = null;

        const focusEditor = () => {
            const field = editor.querySelector(".is-invalid, [aria-invalid='true']")
                || editor.querySelector("input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled])")
                || editor.querySelector("[data-dialog-focus]");
            field?.focus();
        };

        const synchronizeDialog = () => {
            if (editor.querySelector("[data-dialog-panel]")) {
                dialog.hidden = false;
                modal.show();
            } else {
                modal.hide();
            }
        };

        dialog.addEventListener("shown.bs.modal", focusEditor);
        dialog.addEventListener("hide.bs.modal", () => {
            if (requestSource) {
                window.htmx?.trigger(requestSource, "htmx:abort");
                requestSource = null;
            }
        });
        dialog.addEventListener("hidden.bs.modal", () => {
            editor.replaceChildren();
            dialog.hidden = true;
            const opener = document.getElementById(returnFocusId)
                || document.getElementById(dialog.dataset.dialogFallback);
            opener?.focus();
        });
        dialog.addEventListener("click", (event) => {
            if (event.target.closest("[data-dialog-close]")) {
                event.preventDefault();
                modal.hide();
            }
        });

        document.addEventListener("htmx:beforeRequest", (event) => {
            if (event.detail.target !== editor) {
                return;
            }
            requestSource = event.detail.elt;
            if (!dialog.contains(requestSource)) {
                returnFocusId = requestSource.id || dialog.dataset.dialogFallback;
            }
        });
        document.addEventListener("htmx:afterRequest", (event) => {
            if (event.detail.elt === requestSource) {
                requestSource = null;
            }
        });
        document.addEventListener("htmx:afterSwap", (event) => {
            if (event.detail.target === editor) {
                synchronizeDialog();
            }
        });
        document.addEventListener("htmx:afterSettle", (event) => {
            if (event.detail.target === editor && editor.querySelector("[data-dialog-panel]")) {
                focusEditor();
            }
        });
        document.addEventListener("DOMContentLoaded", synchronizeDialog);
    });
})();
