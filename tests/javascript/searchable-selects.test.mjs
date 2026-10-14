import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/searchable-selects.js", import.meta.url), "utf8");

const createSelect = (count, value = "4") => {
    const options = Array.from({ length: count }, (unused, index) => ({
        value: `${index}`, text: `Choice ${index}`, selected: `${index}` === value, defaultSelected: `${index}` === value,
    }));
    return {
        options, value, isConnected: true,
        labels: [{ htmlFor: "timezone" }],
        get childNodes() { return this.options; },
        get selectedOptions() { return this.options.filter((option) => option.selected); },
        replaceChildren(...options) { this.options = options; },
        matches: (selector) => selector === "select",
        querySelectorAll: () => [],
    };
};

const createPage = (selects = [], { library = true } = {}) => {
    const instances = [];
    const document = {
        ...createEvents(),
        body: { dataset: { selectSearch: "Поиск", selectEmpty: "Нет совпадений <script>" } },
        querySelectorAll: () => selects,
        createElement: () => ({}),
    };
    class TomSelect {
        constructor(select, settings) {
            this.select = select;
            this.settings = settings;
            this.control_input = { setAttribute: (name, value) => { this.control_input[name] = value; } };
            this.operations = [];
            this.initialOptions = select.options;
            this.handlers = new Map();
            select.labels[0].htmlFor = "timezone-ts-control";
            select.tomselect = this;
            instances.push(this);
            settings.onInitialize.call(this);
        }
        clearOptions(filter) { this.operations.push(["clear", filter({}, this.select.value)]); }
        sync() { this.operations.push(["sync", this.select.value, this.select.options.length]); }
        on(name, callback) { this.handlers.set(name, callback); }
        destroy() {
            this.operations.push(["destroy"]);
            this.handlers.get("destroy")?.();
            this.select.options = this.initialOptions;
            delete this.select.tomselect;
        }
    }
    runInNewContext(script, { document, window: library ? { TomSelect } : {}, queueMicrotask });
    return { document, instances };
};

test("only long lists gain translated search without changing the native selection", () => {
    const short = createSelect(9);
    const long = createSelect(10);
    const page = createPage([short, long]);

    page.document.emit("DOMContentLoaded");

    assert.equal(short.tomselect, undefined);
    assert.equal(page.instances.length, 1);
    assert.equal(long.value, "4");
    const instance = long.tomselect;
    assert.equal(instance.settings.plugins.join(), "dropdown_input");
    assert.equal(instance.settings.dropdownParent, "body");
    assert.equal(instance.settings.create, false);
    assert.equal(instance.settings.allowEmptyOption, true);
    assert.equal(instance.settings.maxOptions, null);
    assert.equal(instance.control_input.placeholder, "Поиск");
    assert.equal(instance.control_input["aria-label"], "Поиск");
    const empty = instance.settings.render.no_results();
    assert.equal(empty.className, "no-results");
    assert.equal(empty.textContent, "Нет совпадений <script>");
    assert.equal(empty.innerHTML, undefined);
});

test("HTMX initializes new selects and repeated loads do not duplicate controls", () => {
    const existing = createSelect(12);
    const added = createSelect(15);
    const page = createPage([existing]);
    page.document.emit("DOMContentLoaded");
    const fragment = { matches: () => false, querySelectorAll: () => [existing, added] };

    page.document.emit("htmx:load", { detail: { elt: fragment } });
    page.document.emit("htmx:load", { detail: { elt: added } });

    assert.equal(page.instances.length, 2);
    assert.equal(page.instances[1].select, added);
});

test("HTMX cleanup destroys removed controls, including floating dropdowns", () => {
    const select = createSelect(12);
    const page = createPage([select]);
    page.document.emit("DOMContentLoaded");

    page.document.emit("htmx:beforeCleanupElement", { detail: { elt: select } });
    page.document.emit("htmx:beforeCleanupElement", { detail: { elt: select } });

    assert.deepEqual(page.instances[0].operations, [["destroy"]]);
    assert.equal(select.tomselect, undefined);
});

test("updated choices drop cached entries and reread the current native selection silently", () => {
    const select = createSelect(12);
    const page = createPage([select]);
    page.document.emit("DOMContentLoaded");
    select.options = [{ value: "", text: "Choose preset" }, { value: "new", text: "Renamed preset" }];
    select.value = "new";

    page.document.emit("sanea:choices-updated", { target: select });

    assert.deepEqual(select.tomselect.operations, [["clear", false], ["sync", "new", 2]]);
    assert.equal(select.value, "new");
    assert.equal(page.instances.length, 1);
});

test("a dynamically growing list gains search once it reaches the threshold", () => {
    const select = createSelect(9);
    const page = createPage([select]);
    page.document.emit("DOMContentLoaded");

    select.options.push({ value: "new", text: "New preset" });
    page.document.emit("sanea:choices-updated", { target: select });

    assert.equal(page.instances.length, 1);
});

test("history stores native markup, then rebuilds live choices and selection only on surviving controls", async () => {
    const select = createSelect(12);
    const replaced = createSelect(12);
    const page = createPage([select, replaced]);
    page.document.emit("DOMContentLoaded");
    const options = Array.from({ length: 15 }, (unused, index) => ({
        value: `${index}`, text: `Renamed ${index}`, selected: index === 8, defaultSelected: index === 4,
    }));
    select.options = options;
    select.value = "8";

    page.document.emit("htmx:beforeHistorySave", { detail: { historyElt: page.document } });

    assert.equal(select.tomselect, undefined);
    assert.equal(select.labels[0].htmlFor, "timezone");
    assert.equal(select.options[8].text, "Renamed 8");
    assert.deepEqual(select.selectedOptions.map((option) => option.value), ["8"]);
    assert.deepEqual(select.options.filter((option) => option.defaultSelected).map((option) => option.value), ["4"]);
    replaced.isConnected = false;
    const unsettled = createSelect(20);
    page.document.querySelectorAll = () => [select, unsettled];
    await Promise.resolve();

    assert.equal(page.instances.length, 3);
    assert.equal(select.tomselect.select, select);
    assert.equal(select.value, "8");
    assert.equal(replaced.tomselect, undefined);
    assert.equal(unsettled.tomselect, undefined);
    assert.deepEqual(page.instances[0].operations, [["destroy"]]);
});

test("native forms remain usable if the search library is unavailable", () => {
    const select = createSelect(600);
    const page = createPage([select], { library: false });

    page.document.emit("DOMContentLoaded");
    page.document.emit("sanea:choices-updated", { target: select });

    assert.equal(page.instances.length, 0);
    assert.equal(select.value, "4");
    assert.equal(select.options.length, 600);
});
