import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/account-limits.js", import.meta.url), "utf8");

const createClassList = () => {
    const classes = new Set();
    return {
        add: (name) => classes.add(name),
        contains: (name) => classes.has(name),
        toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
    };
};

const createRow = (prefix, index, { name = "", extra = false, deleted = false, persisted = false } = {}) => {
    const row = {
        dataset: { formPrefix: `${prefix}-${index}` },
        classList: createClassList(), hidden: false, extra, focused: false,
    };
    row.name = { name: `${prefix}-${index}-name`, value: name, focus: () => { row.focused = true; } };
    row.deletion = { name: `${prefix}-${index}-DELETE`, checked: deleted, closest: () => row };
    row.discardButton = persisted ? null : {
        hidden: true,
        closest: (selector) => selector === "[data-discard-form]" ? row.discardButton : row,
    };
    row.rule = {
        value: extra ? "" : "0", dataset: {}, options: [{ value: "", textContent: "Choose preset" }],
        updates: [],
        replaceChildren(...options) { this.options = options; },
        dispatchEvent(event) {
            this.updates.push({ type: event.type, bubbles: event.bubbles, value: this.value,
                labels: this.options.map((option) => option.textContent) });
        },
    };
    row.querySelector = (selector) => ({
        'input[name$="-DELETE"]': row.deletion,
        'input[name$="-name"]': row.name,
        "[data-discard-form]": row.discardButton,
        'input:not([type="hidden"]):not([type="checkbox"]), select': row.name,
    })[selector];
    return row;
};

const createPage = ({ bootstrap = true, initial = 1, bound = false, errors = {}, deletedSession = false, blocksSessions = false } = {}) => {
    const formsets = Object.fromEntries(["ranges", "sessions", "apps"].map((prefix) => {
        const rows = initial ? [createRow(prefix, 0, { name: "Everyday", deleted: prefix === "sessions" && deletedSession, persisted: true })] : [];
        rows.push(createRow(prefix, initial, { extra: !bound }));
        const total = { value: `${rows.length}` };
        const initialForms = { value: `${initial}` };
        const formset = {
            dataset: { formset: prefix }, rows, total, initialForms,
            querySelector(selector) {
                return {
                    [`input[name="${prefix}-TOTAL_FORMS"]`]: total,
                    [`input[name="${prefix}-INITIAL_FORMS"]`]: initialForms,
                    "[data-form-rows]": { append: (row) => rows.push(row) },
                    "[data-extra-row][hidden]:not(.is-removed)": rows.find((row) => row.extra && row.hidden && !row.classList.contains("is-removed")),
                    "[data-empty-form]": {
                        innerHTML: `<fieldset data-form-prefix="${prefix}-__prefix__"><input id="id_${prefix}-__prefix__-name" list="id_${prefix}-__prefix__-suggestions"><datalist id="id_${prefix}-__prefix__-suggestions"></datalist></fieldset>`,
                    },
                }[selector];
            },
            querySelectorAll: () => rows.filter((row) => row.extra),
        };
        formset.button = {
            hidden: true,
            closest: (selector) => ({ "[data-add-form]": formset.button, "[data-formset]": formset })[selector],
        };
        return [prefix, formset];
    }));
    const markers = Object.fromEntries(Object.entries(errors).map(([prefix, enabled]) => [
        prefix, enabled ? [{ closest: () => formsets[prefix].rows[0] }] : [],
    ]));
    const panels = ["schedule", "sessions", "apps"].map((name) => ({
        id: `account-limits-${name}`,
        querySelectorAll: () => markers[name === "schedule" ? "ranges" : name] || [],
    }));
    const details = { open: false, querySelectorAll: () => markers.apps || [] };
    const form = {
        ...createEvents(), dataset: { newPresetLabel: "New preset", discardNotice: "Unsaved changes will be discarded." },
        querySelectorAll(selector) {
            return {
                '[data-formset="sessions"] [data-form-row]': formsets.sessions.rows,
                'select[name$="-rule"]': [...formsets.ranges.rows, ...formsets.apps.rows].map((row) => row.rule),
                "[data-form-row]": Object.values(formsets).flatMap((formset) => formset.rows),
                "[data-formset]": Object.values(formsets),
                "[data-add-form]": Object.values(formsets).map((formset) => formset.button),
                "[data-limits-panel]": panels,
                "details": [details],
            }[selector];
        },
    };
    const tabs = { hidden: true };
    const panelContainer = { classList: createClassList() };
    const elements = new Map([
        ["account-limits-form", form], ["account-limits-tabs", tabs], ["account-limits-panels", panelContainer],
        ...panels.map((panel) => [`${panel.id}-tab`, { id: `${panel.id}-tab` }]),
    ]);
    const shown = [];
    const confirmation = { accepted: true, messages: [] };
    const removal = {
        ...createEvents(), dataset: { confirmation: "Remove preset and its intervals and applications?" },
        confirmed: { value: "" }, emptySchedule: { value: "" },
        hasAttribute: () => blocksSessions,
        querySelector(selector) {
            return { 'input[name="confirmed"]': this.confirmed, 'input[name="confirm_empty_schedule"]': this.emptySchedule }[selector];
        },
    };
    const document = {
        ...createEvents(), getElementById: (id) => elements.get(id),
        querySelectorAll: () => [removal],
        createElement(name) {
            if (name === "option") {
                return {};
            }
            return {
                set innerHTML(markup) {
                    const [prefix, index] = markup.match(/data-form-prefix="(\w+)-(\d+)"/).slice(1);
                    const row = createRow(prefix, Number(index), { extra: true });
                    row.markup = markup;
                    this.content = { firstElementChild: row };
                },
            };
        },
    };
    const window = {
        confirm: (message) => { confirmation.messages.push(message); return confirmation.accepted; },
        ...(bootstrap ? { bootstrap: { Tab: { getOrCreateInstance: (button) => ({ show: () => shown.push(button.id) }) } } } : {}),
    };
    class CustomEvent {
        constructor(type, options) { this.type = type; this.bubbles = options.bubbles; }
    }
    runInNewContext(script, { document, window, CustomEvent });
    return { document, form, formsets, tabs, panelContainer, details, shown, removal, confirmation };
};

test("initialization opens Schedule and hides only pristine extra rows beside existing rules", () => {
    const page = createPage();

    page.document.emit("DOMContentLoaded");

    assert.deepEqual(page.shown, ["account-limits-schedule-tab"]);
    assert.equal(page.tabs.hidden, false);
    assert.equal(page.panelContainer.classList.contains("tab-content"), true);
    assert.equal(page.formsets.sessions.rows[1].hidden, true);
    assert.equal(page.formsets.sessions.total.value, "2");
    assert.equal(page.formsets.sessions.rows[0].discardButton, null);
    assert.equal(page.formsets.sessions.rows[1].discardButton.hidden, false);
    assert.deepEqual(page.formsets.ranges.rows[0].rule.options.map((option) => option.value), ["", "0"]);
});

test("Add reveals the existing extra row before cloning, and new presets can be selected immediately", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");

    page.form.emit("click", { target: page.formsets.sessions.button });
    assert.equal(page.formsets.sessions.rows[1].hidden, false);
    assert.equal(page.formsets.sessions.total.value, "2");
    page.form.emit("click", { target: page.formsets.sessions.button });
    const added = page.formsets.sessions.rows[2];
    const selection = page.formsets.ranges.rows[0].rule;
    selection.value = "2";
    added.name.value = "After school <script>";
    page.form.emit("input", { target: added.name });

    assert.equal(page.formsets.sessions.total.value, "3");
    assert.equal(added.dataset.formPrefix, "sessions-2");
    assert.equal(added.markup.includes("__prefix__"), false);
    assert.equal(added.markup.includes('list="id_sessions-2-suggestions"'), true);
    assert.equal(added.focused, true);
    assert.equal(added.discardButton.hidden, false);
    assert.equal(selection.value, "2");
    assert.deepEqual(selection.options.map((option) => option.textContent), ["Choose preset", "Everyday", "New preset", "After school <script>"]);
    assert.deepEqual(selection.updates.at(-1), {
        type: "sanea:choices-updated", bubbles: true, value: "2",
        labels: ["Choose preset", "Everyday", "New preset", "After school <script>"],
    });
});

test("discarding an unsaved row hides it immediately without changing stored rows or TOTAL_FORMS", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.form.emit("click", { target: page.formsets.sessions.button });
    const row = page.formsets.sessions.rows[1];
    page.formsets.apps.rows[0].rule.value = "1";

    page.form.emit("click", { target: row.discardButton });

    assert.equal(row.deletion.checked, true);
    assert.equal(row.classList.contains("is-removed"), true);
    assert.equal(row.hidden, true);
    assert.equal(page.formsets.sessions.rows.length, 2);
    assert.equal(page.formsets.sessions.total.value, "2");
    assert.equal(page.formsets.apps.rows[0].rule.value, "");
    assert.deepEqual(page.formsets.apps.rows[0].rule.options.map((option) => option.value), ["", "0"]);
    assert.equal(page.formsets.apps.rows[0].rule.updates.at(-1).value, "");
    assert.equal(page.formsets.sessions.rows[0].deletion.checked, false);
    assert.equal(page.formsets.sessions.total.value, "2");
    assert.deepEqual(page.confirmation.messages, []);

    page.form.emit("click", { target: page.formsets.sessions.button });

    assert.equal(row.hidden, true);
    assert.equal(page.formsets.sessions.rows[2].hidden, false);
    assert.equal(page.formsets.sessions.total.value, "3");
});

test("stored rule removal is a separately confirmed submit, warns about drafts, and never submits their values", () => {
    const page = createPage({ blocksSessions: true });
    page.document.emit("DOMContentLoaded");
    page.confirmation.accepted = false;
    let prevented = false;

    page.removal.emit("submit", { preventDefault: () => { prevented = true; } });

    assert.equal(prevented, true);
    assert.equal(page.removal.confirmed.value, "");
    assert.equal(page.removal.emptySchedule.value, "");
    assert.equal(page.formsets.sessions.rows[0].deletion.checked, false);

    page.confirmation.accepted = true;
    page.form.emit("input", { target: page.formsets.sessions.rows[0].name });
    page.removal.emit("submit", { preventDefault: () => { throw new Error("Confirmed deletion was cancelled"); } });

    assert.equal(page.removal.confirmed.value, "on");
    assert.equal(page.removal.emptySchedule.value, "on");
    assert.match(page.confirmation.messages.at(-1), /Unsaved changes will be discarded/);
    assert.equal(page.formsets.sessions.rows[0].deletion.checked, false);
    assert.equal(page.formsets.sessions.total.value, "2");

    page.confirmation.accepted = false;
    page.removal.emit("submit", { preventDefault: () => {} });

    assert.equal(page.removal.confirmed.value, "");
    assert.equal(page.removal.emptySchedule.value, "");
});

test("empty accounts keep their blank forms visible and application errors open the matching tab and details", () => {
    const page = createPage({ initial: 0, errors: { apps: true } });

    page.document.emit("DOMContentLoaded");

    assert.equal(page.formsets.sessions.rows[0].hidden, false);
    assert.equal(page.formsets.apps.rows[0].hidden, false);
    assert.deepEqual(page.shown, ["account-limits-apps-tab"]);
    assert.equal(page.details.open, true);
    assert.deepEqual(page.formsets.ranges.rows[0].rule.options.map((option) => option.textContent), ["Choose preset", "New preset"]);
});

test("submitted extra rows remain visible and errors from removed rows do not hide relevant application errors", () => {
    const page = createPage({ bound: true, deletedSession: true, errors: { sessions: true, apps: true } });

    page.document.emit("DOMContentLoaded");

    assert.equal(page.formsets.sessions.rows[1].hidden, false);
    assert.equal(page.formsets.sessions.rows[0].classList.contains("is-removed"), true);
    assert.deepEqual(page.shown, ["account-limits-apps-tab"]);
    assert.equal(page.details.open, true);
});

test("without Bootstrap the sections remain visible, while formsets and recognition details still work", () => {
    const page = createPage({ bootstrap: false, errors: { apps: true } });

    page.document.emit("DOMContentLoaded");
    page.form.emit("click", { target: page.formsets.apps.button });

    assert.equal(page.tabs.hidden, true);
    assert.equal(page.panelContainer.classList.contains("tab-content"), false);
    assert.equal(page.formsets.apps.rows[1].hidden, false);
    assert.equal(page.details.open, true);
    assert.deepEqual(page.shown, []);
});
