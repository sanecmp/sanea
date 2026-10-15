import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/editor-dialog.js", import.meta.url), "utf8");

const createField = () => ({ focused: 0, focus() { this.focused += 1; } });

const createPage = ({ initialForm = false, library = true } = {}) => {
    const editor = {
        form: initialForm ? {} : null,
        field: createField(), invalid: null,
        querySelector(selector) {
            return {
                "[data-dialog-panel]": this.form,
                ".is-invalid, [aria-invalid='true']": this.invalid,
                "input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled])": this.field,
                "[data-dialog-focus]": this.button,
            }[selector];
        },
        querySelectorAll() { return [this.form].filter(Boolean); },
        replaceChildren() { this.form = null; },
    };
    const classes = new Set();
    const dialog = {
        ...createEvents(), hidden: !initialForm, dataset: { dialogFallback: "person-add" },
        querySelector: () => editor,
        classList: { add: (name) => classes.add(name), contains: (name) => classes.has(name) },
        contains: (element) => !!element?.insideDialog,
    };
    const opener = { id: "person-edit-1", ...createField() };
    const add = { id: "person-add", ...createField() };
    const elements = new Map([["person-dialog", dialog], ["person-editor", editor], [opener.id, opener], [add.id, add]]);
    const document = {
        ...createEvents(), getElementById: (identifier) => elements.get(identifier), querySelectorAll: () => [dialog],
    };
    const modal = {
        open: false, shown: 0, hidden: 0,
        show() {
            if (!this.open) {
                this.open = true;
                this.shown += 1;
                dialog.emit("shown.bs.modal");
            }
        },
        hide() {
            if (this.open) {
                dialog.emit("hide.bs.modal");
                this.open = false;
                this.hidden += 1;
                dialog.emit("hidden.bs.modal");
            }
        },
    };
    const aborted = [];
    const window = {
        htmx: { trigger: (element, name) => aborted.push([element, name]) },
        ...(library ? { bootstrap: { Modal: { getOrCreateInstance: () => modal } } } : {}),
    };
    runInNewContext(script, { document, window });
    document.emit("DOMContentLoaded");
    return { document, dialog, editor, modal, opener, add, elements, aborted };
};

const swapEditor = (page) => {
    page.document.emit("htmx:afterSwap", { detail: { target: page.editor } });
    page.document.emit("htmx:afterSettle", { detail: { target: page.editor } });
};

test("initial people lists stay unobstructed, while ordinary editor links open a focused dialog", () => {
    const listing = createPage();
    assert.equal(listing.dialog.hidden, true);
    assert.equal(listing.modal.shown, 0);

    const editor = createPage({ initialForm: true });
    assert.equal(editor.dialog.classList.contains("modal"), true);
    assert.equal(editor.dialog.hidden, false);
    assert.equal(editor.modal.open, true);
    assert.equal(editor.editor.field.focused, 1);
});

test("AJAX errors keep the dialog open and focus the invalid control; saves close it and restore the new row's focus", () => {
    const page = createPage();
    page.document.emit("htmx:beforeRequest", { detail: { target: page.editor, elt: page.opener } });
    page.editor.form = { insideDialog: true };
    swapEditor(page);
    assert.equal(page.modal.shown, 1);
    assert.equal(page.modal.open, true);

    page.editor.invalid = createField();
    page.document.emit("htmx:beforeRequest", { detail: { target: page.editor, elt: page.editor.form } });
    swapEditor(page);
    assert.equal(page.modal.shown, 1);
    assert.equal(page.editor.invalid.focused, 1);

    const replacementOpener = createField();
    page.elements.set(page.opener.id, replacementOpener);
    page.editor.form = null;
    swapEditor(page);
    assert.equal(page.modal.open, false);
    assert.equal(page.dialog.hidden, true);
    assert.equal(replacementOpener.focused, 1);
});

test("cancel closes without submitting, aborts in-flight requests, and allows reopening", () => {
    const page = createPage({ initialForm: true });
    const form = page.editor.form;
    page.document.emit("htmx:beforeRequest", { detail: { target: page.editor, elt: form } });
    let prevented = false;

    page.dialog.emit("click", {
        target: { closest: () => ({}) }, preventDefault: () => { prevented = true; },
    });

    assert.equal(prevented, true);
    assert.equal(page.modal.hidden, 1);
    assert.equal(page.editor.form, null);
    assert.deepEqual(page.aborted, [[form, "htmx:abort"]]);
    assert.equal(page.add.focused, 1);

    page.editor.form = {};
    page.editor.field = createField();
    swapEditor(page);
    assert.equal(page.modal.shown, 2);
    assert.equal(page.dialog.hidden, false);
    assert.ok(page.editor.field.focused > 0);
});

test("Escape and backdrop dismissal share cleanup and cancel does not intercept ordinary clicks", () => {
    const page = createPage({ initialForm: true });
    page.dialog.emit("click", { target: { closest: () => null }, preventDefault: () => assert.fail("Ordinary click intercepted") });
    assert.equal(page.modal.open, true);

    page.modal.hide();
    assert.equal(page.editor.form, null);
    assert.equal(page.dialog.hidden, true);
});

test("unrelated swaps do not open dialogs and missing Bootstrap leaves ordinary forms usable", () => {
    const page = createPage();
    page.document.emit("htmx:afterSwap", { detail: { target: {} } });
    assert.equal(page.modal.open, false);

    const ordinary = createPage({ initialForm: true, library: false });
    assert.equal(ordinary.dialog.classList.contains("modal"), false);
    assert.equal(ordinary.dialog.hidden, false);
    assert.ok(ordinary.editor.form);
});

test("read-only details, editing and saved details share one dialog, while closing aborts a pending mode switch", () => {
    const page = createPage();
    const edit = { insideDialog: true, ...createField() };
    page.editor.form = {};
    page.editor.field = null;
    page.editor.button = edit;
    swapEditor(page);
    assert.equal(page.modal.open, true);
    assert.ok(edit.focused > 0);

    page.document.emit("htmx:beforeRequest", { detail: { target: page.editor, elt: edit } });
    page.modal.hide();
    assert.deepEqual(page.aborted, [[edit, "htmx:abort"]]);
    assert.equal(page.editor.form, null);

    page.editor.form = { insideDialog: true };
    page.editor.field = createField();
    swapEditor(page);
    const field = page.editor.field;
    assert.ok(field.focused > 0);
    page.editor.field = null;
    swapEditor(page);
    assert.equal(page.modal.open, true);
});

test("closing after a table update focuses the fallback when the original row has disappeared", () => {
    const page = createPage();
    page.document.emit("htmx:beforeRequest", { detail: { target: page.editor, elt: page.opener } });
    page.editor.form = {};
    swapEditor(page);
    page.elements.delete(page.opener.id);
    page.modal.hide();

    assert.equal(page.add.focused, 1);
});
