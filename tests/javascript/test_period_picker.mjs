import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/period-picker.js", import.meta.url), "utf8");
const createElement = () => ({
    ...createEvents(), dataset: {}, attributes: {}, children: [],
    setAttribute(name, value) { this.attributes[name] = value; },
    appendChild(child) { this.children.push(child); },
    querySelectorAll() { return this.children.flatMap((child) => child.dataset.periodPreset ? [child] : child.querySelectorAll()); },
});
const createPage = (prefix = "", language = "ru-RU") => {
    const period = Object.assign(createElement(), {value: "7-days", name: `${prefix}period`});
    const label = {htmlFor: `${prefix}day`};
    const field = Object.assign(createElement(), {
        id: `${prefix}day`, name: `${prefix}day`, value: "", isConnected: true, labels: [label],
        dataset: {periodField: `${prefix}period`, periodDefault: "7-days", periodPresets: JSON.stringify([
            {value: "today", label: "Сегодня"}, {value: "7-days", label: "Последние 7 дней"},
        ])},
        form: {elements: {namedItem: (name) => name === `${prefix}period` ? period : null}},
        matches: () => true,
        dispatchEvent(event) { this.emit(event.type, event); },
    });
    const document = {
        ...createEvents(), documentElement: {lang: language}, createElement,
        querySelectorAll: () => [field],
    };
    let options;
    let destroyed = 0;
    let closed = 0;
    const flatpickr = (input, settings) => {
        options = settings;
        const instance = {
            altInput: {}, calendarContainer: createElement(),
            clear(triggerChange) {
                assert.equal(triggerChange, false);
                input.value = "";
                this.altInput.value = "";
            },
            close() { closed += 1; },
            destroy() { destroyed += 1; settings.onDestroy(); },
        };
        input._flatpickr = instance;
        settings.onReady([], input.value, instance);
    };
    flatpickr.l10ns = {ru: {firstDayOfWeek: 1}};
    const microtasks = [];
    const location = {search: ""};
    runInNewContext(script, {document, window: {flatpickr, location}, Event, URLSearchParams,
        queueMicrotask: (callback) => microtasks.push(callback)});
    return {document, field, label, period, flatpickr, microtasks, location,
        get options() { return options; }, get destroyed() { return destroyed; }, get closed() { return closed; }};
};

for (const prefix of ["", "issues-"]) {
    test(`one period picker selects a day or a shortcut, with prefix '${prefix}'`, () => {
        const page = createPage(prefix);
        let changed = 0;
        page.field.addEventListener("change", () => { changed += 1; });

        page.document.emit("DOMContentLoaded");
        const instance = page.field._flatpickr;
        const buttons = instance.calendarContainer.querySelectorAll();
        assert.equal(instance.altInput.value, "Последние 7 дней");
        assert.equal(page.label.htmlFor, `${prefix}day-display`);
        assert.equal(page.options.altInput, true);
        assert.equal(page.options.locale, page.flatpickr.l10ns.ru);
        assert.equal(page.options.monthSelectorType, "static");
        assert.equal(buttons[1].attributes["aria-pressed"], "true");

        page.field.value = "2026-10-02";
        instance.altInput.value = "2026-10-02";
        page.options.onChange([], page.field.value, instance);
        assert.equal(page.period.value, "day");
        assert.equal(instance.altInput.value, "2026-10-02");
        assert.equal(buttons[1].attributes["aria-pressed"], "false");

        buttons[0].emit("click");
        assert.equal(page.period.value, "today");
        assert.equal(page.field.value, "");
        assert.equal(instance.altInput.value, "Сегодня");
        assert.equal(buttons[0].attributes["aria-pressed"], "true");
        assert.equal(changed, 1);
        assert.equal(page.closed, 1);
    });
}

test("period pickers survive swaps and history without duplicate instances or stale labels", () => {
    const page = createPage("issues-", "en");
    page.document.emit("DOMContentLoaded");
    assert.equal(page.options.locale, "default");
    const instance = page.field._flatpickr;
    page.document.emit("htmx:load", {detail: {elt: page.field}});
    assert.equal(page.field._flatpickr, instance);

    page.document.emit("htmx:beforeCleanupElement", {detail: {elt: page.field}});
    assert.equal(page.destroyed, 1);
    assert.equal(page.label.htmlFor, "issues-day");
    page.document.emit("htmx:load", {detail: {elt: page.field}});
    page.field.value = "2026-10-02";
    page.period.value = "day";

    page.document.emit("htmx:beforeHistorySave", {detail: {historyElt: page.document}});
    assert.equal(page.destroyed, 2);
    assert.equal(page.field.attributes.value, "2026-10-02");
    assert.equal(page.period.attributes.value, "day");
    assert.equal(page.field._flatpickr, undefined);
    assert.equal(page.label.htmlFor, "issues-day");
    page.microtasks.forEach((callback) => callback());
    assert.ok(page.field._flatpickr);
    assert.equal(page.label.htmlFor, "issues-day-display");
});

test("the native date input selects the day when Flatpickr is unavailable", () => {
    const period = {value: "today"};
    const document = {...createEvents(), querySelectorAll: () => []};
    const field = {
        value: "2026-10-01", matches: () => true, dataset: {periodField: "issues-period"},
        form: {elements: {namedItem: (name) => name === "issues-period" ? period : null}},
    };
    runInNewContext(script, {document, window: {}});

    document.emit("DOMContentLoaded");
    document.emit("change", {target: field});
    assert.equal(period.value, "day");

    period.value = "7-days";
    field.value = "";
    document.emit("change", {target: field});
    assert.equal(period.value, "7-days");
});

test("history restores the report's URL selection, not the form changed before the previous swap", () => {
    const page = createPage("issues-");
    page.document.emit("DOMContentLoaded");
    page.location.search = "?issues-period=day&issues-day=2026-10-23";

    page.document.emit("htmx:historyRestore");
    assert.equal(page.period.value, "day");
    assert.equal(page.field.value, "2026-10-23");

    page.location.search = "";
    page.document.emit("htmx:historyRestore");
    assert.equal(page.period.value, "7-days");
    assert.equal(page.field.value, "");
    assert.equal(page.field._flatpickr.altInput.value, "Последние 7 дней");
});
