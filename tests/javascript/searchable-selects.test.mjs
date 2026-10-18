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
        options, value, isConnected: true, dataset: {},
        labels: [{ htmlFor: "timezone" }],
        get childNodes() { return this.options; },
        get selectedOptions() { return this.options.filter((option) => option.selected); },
        replaceChildren(...options) { this.options = options; },
        matches: (selector) => selector === "select",
        closest: () => null,
        querySelectorAll: () => [],
    };
};

const createInput = (value = "", suggestions = []) => ({
    value, isConnected: true, maxLength: 15,
    dataset: { selectSuggestions: JSON.stringify(suggestions), selectCreateLabel: "Использовать:" },
    labels: [{ htmlFor: "process" }],
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    matches: (selector) => selector === "input[data-select-suggestions]",
    closest: () => null,
    querySelectorAll: () => [],
});

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

test("opted-in lists always offer search without allowing arbitrary values", () => {
    const select = createSelect(3);
    select.dataset.selectSearch = "always";
    const page = createPage([select]);

    page.document.emit("DOMContentLoaded");

    assert.equal(page.instances.length, 1);
    assert.equal(select.tomselect.settings.create, false);
    assert.equal(select.tomselect.settings.plugins.join(), "dropdown_input");
    assert.equal(select.tomselect.control_input.placeholder, "Поиск");
});

test("new form rows initialize searchable lists only once", () => {
    const select = createSelect(3);
    select.dataset.selectSearch = "always";
    const page = createPage();
    const row = { querySelectorAll: () => [select] };

    page.document.emit("sanea:form-added", { target: row });
    page.document.emit("sanea:form-added", { target: row });

    assert.equal(page.instances.length, 1);
    assert.equal(select.tomselect.settings.create, false);
});

test("dialog searches stay inside the focus trap instead of moving to the body", () => {
    const select = createSelect(3);
    select.dataset.selectSearch = "always";
    select.closest = (selector) => selector === "[data-editor-dialog]" ? {} : null;
    const page = createPage([select]);

    page.document.emit("DOMContentLoaded");

    assert.equal(select.tomselect.settings.dropdownParent, null);
});

test("text suggestions keep exact names and commit manual input on blur", () => {
    const input = createInput("custom,process", ["SteamWebHelper", "gjs-console"]);
    const select = createSelect(10);
    const page = createPage([input, select]);

    page.document.emit("DOMContentLoaded");

    const settings = input.tomselect.settings;
    assert.equal(page.instances.length, 2);
    assert.equal(settings.create, true);
    assert.equal(settings.createOnBlur, true);
    assert.equal(settings.plugins.length, 0);
    assert.equal(settings.allowEmptyOption, false);
    assert.equal(settings.maxItems, 1);
    assert.equal(settings.splitOn.test("synthetic,tool"), false);
    assert.equal(JSON.stringify(settings.items), '["custom,process"]');
    assert.equal(JSON.stringify(settings.options), JSON.stringify([
        { value: "SteamWebHelper", text: "SteamWebHelper" },
        { value: "gjs-console", text: "gjs-console" },
        { value: "custom,process", text: "custom,process" },
    ]));
    assert.equal(input.tomselect.control_input.maxLength, 15);
    assert.equal(select.tomselect.settings.create, false);
    const option = settings.render.option_create({ input: 'qa&"<x>' });
    assert.equal(option.textContent, 'Использовать: qa&"<x>');
    assert.equal(option.innerHTML, undefined);
});

test("empty activity still allows typing a process name without inventing an empty selection", () => {
    const input = createInput();
    const page = createPage([input]);

    page.document.emit("DOMContentLoaded");

    assert.equal(input.tomselect.settings.options.length, 0);
    assert.equal(input.tomselect.settings.items.length, 0);
    assert.equal(input.tomselect.settings.create, true);
});

test("HTMX initializes individual text inputs once and cleanup restores their labels", () => {
    const input = createInput("gjs-console", ["gjs-console"]);
    const page = createPage();

    page.document.emit("htmx:load", { detail: { elt: input } });
    page.document.emit("htmx:load", { detail: { elt: input } });

    assert.equal(page.instances.length, 1);
    assert.equal(input.tomselect.settings.options.length, 1);

    page.document.emit("htmx:beforeCleanupElement", { detail: { elt: input } });

    assert.equal(input.tomselect, undefined);
    assert.equal(input.labels[0].htmlFor, "process");
});

test("history preserves a text input value and rebuilds its suggestions", async () => {
    const input = createInput("gjs-console", ["gjs-console"]);
    const page = createPage([input]);
    page.document.emit("DOMContentLoaded");
    input.value = "manual-name";

    page.document.emit("htmx:beforeHistorySave", { detail: { historyElt: page.document } });

    assert.equal(input.tomselect, undefined);
    assert.equal(input.value, "manual-name");
    assert.equal(input.attributes.value, "manual-name");
    assert.equal(input.labels[0].htmlFor, "process");
    await Promise.resolve();

    assert.equal(page.instances.length, 2);
    assert.equal(JSON.stringify(input.tomselect.settings.items), '["manual-name"]');
});

test("without the search library a process name stays a normal editable text value", () => {
    const input = createInput("custom,process", ["gjs-console"]);
    const page = createPage([input], { library: false });

    page.document.emit("DOMContentLoaded");

    assert.equal(input.tomselect, undefined);
    assert.equal(input.value, "custom,process");
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
