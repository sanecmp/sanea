import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/diagnostic-logs.js", import.meta.url), "utf8");
const createLog = (name, count = 30) => Array.from(
    { length: count }, (_, index) => `Synthetic ${name} line ${index + 1}`,
).join("\n");
const createSnapshot = (computer, text = createLog(computer), received = "received 13:00") => ({ computer, text, received });
const createClassList = (active) => {
    const classes = new Set(active ? ["active"] : []);
    return {
        contains: (name) => classes.has(name),
        toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
    };
};

const createPage = (snapshots = [createSnapshot("1"), createSnapshot("2")], path = "/computers/?issues-period=7-days") => {
    const elements = new Map();
    const entries = new Map();
    const body = { ...createEvents(), matches: () => false };
    const shown = [];
    const requests = [];
    const copies = [];
    const document = {
        ...createEvents(), body, hidden: false, activeElement: body,
        getElementById: (id) => elements.get(id),
        querySelectorAll: () => elements.has("diagnostic-logs") ? [...entries.values()].map((entry) => entry.log) : [],
    };
    const window = {
        location: { href: `http://localhost${path}` },
        history: {
            state: { htmx: true },
            replaceState(state, title, url) {
                this.state = state;
                window.location.href = `${url}`;
            },
        },
        bootstrap: {
            Tab: {
                getOrCreateInstance(tab) {
                    return {
                        show() {
                            shown.push(tab.dataset.logComputer);
                            if (tab.classList.contains("active")) {
                                return;
                            }
                            const previous = [...entries.values()].find((entry) => entry.tab.classList.contains("active"));
                            if (previous) {
                                body.emit("hide.bs.tab", { target: previous.tab });
                                previous.tab.classList.toggle("active", false);
                                previous.panel.classList.toggle("active", false);
                            }
                            tab.classList.toggle("active", true);
                            entries.get(tab.dataset.logComputer).panel.classList.toggle("active", true);
                            body.emit("shown.bs.tab", { target: tab });
                        },
                    };
                },
            },
        },
        htmx: { trigger: (...args) => requests.push(args) },
        navigator: { clipboard: { writeText: async (value) => { copies.push(value); } } },
    };
    const render = (updated, { active = updated[0]?.computer, path = window.location.href } = {}) => {
        elements.clear();
        entries.clear();
        document.activeElement = body;
        const root = {
            id: "diagnostic-logs",
            querySelectorAll: () => [...entries.values()].map((entry) => entry.log),
            querySelector: () => [...entries.values()].find((entry) => entry.tab.classList.contains("active"))?.tab,
        };
        elements.set(root.id, root);
        elements.set("diagnostic-computer", { value: active || "" });
        for (const { computer, text, received } of updated) {
            const panel = { classList: createClassList(computer === active) };
            const href = new URL(path);
            href.searchParams.set("log", computer);
            href.hash = "diagnostic-logs";
            const tab = {
                id: `log-tab-${computer}`, dataset: { logComputer: computer }, href: href.href,
                classList: createClassList(computer === active),
            };
            let top = 0;
            const log = {
                id: `log-text-${computer}`, dataset: { logComputer: computer }, textContent: text, scrollLeft: 0,
                closest: (selector) => selector === ".tab-pane" ? panel : null,
                matches: (selector) => selector === "pre[data-log-computer]",
                focus: () => { document.activeElement = log; },
                get clientHeight() { return panel.classList.contains("active") ? 100 : 0; },
                get scrollHeight() { return panel.classList.contains("active") ? this.textContent.split("\n").length * 20 : 0; },
                get scrollTop() { return top; },
                set scrollTop(value) { top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); },
            };
            const timestamp = { id: `log-received-${computer}`, textContent: received };
            const button = {
                id: `log-copy-${computer}`, disabled: false,
                dataset: { logCopy: computer, copySuccess: "Copied", copyError: "Could not copy" },
                closest: (selector) => selector === "[data-log-copy]" ? button : null,
            };
            const status = { id: `log-copy-status-${computer}`, textContent: "" };
            entries.set(computer, { panel, tab, log, timestamp, button, status });
            for (const element of [tab, log, timestamp, button, status]) {
                elements.set(element.id, element);
            }
        }
    };
    const swap = (updated, options = {}) => {
        const target = { id: options.target || "diagnostic-logs" };
        body.emit("htmx:beforeSwap", { detail: { target, shouldSwap: true } });
        render(updated, options);
        body.emit("htmx:afterSwap", { detail: { target } });
        body.emit("htmx:afterSettle", { detail: { target } });
    };
    const select = (computer) => window.bootstrap.Tab.getOrCreateInstance(entries.get(computer).tab).show();
    const scroll = (computer, top, left = 0) => {
        const log = entries.get(computer).log;
        log.scrollTop = top;
        log.scrollLeft = left;
        document.emit("scroll", { target: log });
    };
    render(snapshots, { active: new URL(window.location.href).searchParams.get("log") || snapshots[0]?.computer });
    runInNewContext(script, { document, window, URL });
    return { document, window, body, elements, entries, shown, requests, copies, render, swap, select, scroll };
};

test("the selected log starts at its tail and tabs keep independent reading positions", () => {
    const page = createPage(undefined, "/computers/?issues-period=7-days&issues-computer=2&log=2");

    page.document.emit("DOMContentLoaded");

    assert.equal(page.entries.get("2").log.scrollTop, 500);
    assert.equal(page.entries.get("1").log.scrollTop, 0);
    page.scroll("2", 120, 35);
    page.select("1");
    assert.equal(page.entries.get("1").log.scrollTop, 500);
    page.select("2");
    assert.equal(page.entries.get("2").log.scrollTop, 120);
    assert.equal(page.entries.get("2").log.scrollLeft, 35);
    assert.equal(page.elements.get("diagnostic-computer").value, "2");
    const url = new URL(page.window.location.href);
    assert.equal(url.searchParams.get("log"), "2");
    assert.equal(url.searchParams.get("issues-period"), "7-days");
    assert.equal(url.searchParams.get("issues-computer"), "2");
    assert.deepEqual(page.window.history.state, { htmx: true });
});

test("manual refresh shows new text immediately, preserving the tab and reading positions", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120, 35);
    page.select("2");
    page.scroll("2", 240, 70);
    const updated = [createSnapshot("1", createLog("latest 1")), createSnapshot("2", createLog("latest 2"))];

    page.swap(updated);

    assert.equal(page.entries.get("2").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("2").log.textContent, updated[1].text);
    assert.equal(page.entries.get("2").log.scrollTop, 240);
    assert.equal(page.entries.get("2").log.scrollLeft, 70);
    page.select("1");
    assert.equal(page.entries.get("1").log.textContent, updated[0].text);
    assert.equal(page.entries.get("1").log.scrollTop, 120);
    assert.equal(page.entries.get("1").log.scrollLeft, 35);
});

test("manual refresh follows the tail when already at the end", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 500, 40);
    const latest = createSnapshot("1", createLog("updated", 35), "received 13:01");

    page.swap([latest, createSnapshot("2")]);
    const { log, timestamp } = page.entries.get("1");

    assert.equal(log.textContent, latest.text);
    assert.equal(timestamp.textContent, latest.received);
    assert.equal(log.scrollTop, 600);
    assert.equal(log.scrollLeft, 40);
});

test("filter changes discard missing computers and initialize returning logs from scratch", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.select("2");
    page.scroll("2", 120);

    page.swap([createSnapshot("1")], { target: "issues-content" });

    assert.equal(page.entries.get("1").tab.classList.contains("active"), true);
    assert.equal(page.elements.get("diagnostic-computer").value, "1");
    assert.equal(page.entries.get("1").log.scrollTop, 500);
    page.swap([]);
    page.swap([createSnapshot("2", createLog("returning", 20))]);
    assert.equal(page.entries.get("2").log.textContent, createLog("returning", 20));
    assert.equal(page.entries.get("2").log.scrollTop, 300);
});

test("HTMX history restoration opens the machine from the restored URL", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120);
    page.select("2");
    const restored = createSnapshot("1", createLog("history", 20));
    page.render([restored, createSnapshot("2")], { active: "2" });
    page.window.location.href = "http://localhost/computers/?issues-period=7-days&log=1";

    page.body.emit("htmx:historyRestore");

    assert.equal(page.entries.get("1").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("1").log.textContent, restored.text);
    assert.equal(page.entries.get("1").log.scrollTop, 300);
});

test("copy writes the exact displayed text without changing the log or its position", async () => {
    const text = "# Synthetic log\n<script>not markup</script>\n  indented line\n";
    const page = createPage([createSnapshot("1", text)]);
    page.document.emit("DOMContentLoaded");
    const { log, button, status } = page.entries.get("1");

    page.body.emit("click", { target: button });
    await new Promise(setImmediate);

    assert.deepEqual(page.copies, [text]);
    assert.equal(log.textContent, text);
    assert.equal(status.textContent, "Copied");
    assert.equal(button.disabled, false);
    assert.equal(page.requests.length, 0);
});

for (const available of [false, true]) {
    test(`copy failure provides feedback and permits another try (clipboard available: ${available})`, async () => {
        const page = createPage([createSnapshot("1")]);
        page.window.navigator.clipboard = available ? { writeText: async () => { throw new Error("Denied"); } } : undefined;
        const { button, status } = page.entries.get("1");

        page.body.emit("click", { target: button });
        await new Promise(setImmediate);

        assert.equal(button.disabled, false);
        assert.equal(status.textContent, "Could not copy");
        assert.equal(page.entries.get("1").log.textContent, createLog("1"));
        page.window.navigator.clipboard = { writeText: async () => {} };
        page.body.emit("click", { target: button });
        await new Promise(setImmediate);
        assert.equal(status.textContent, "Copied");
    });
}

test("visibility, scroll, tabs and unrelated swaps never request a log refresh", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.document.hidden = true;
    page.document.emit("visibilitychange");
    page.document.hidden = false;
    page.document.emit("visibilitychange");
    page.scroll("1", 120);
    page.select("2");
    page.body.emit("htmx:afterSettle", { detail: { target: { id: "computer-table" } } });
    page.body.emit("click", { target: { closest: () => null } });

    assert.equal(page.requests.length, 0);
    assert.equal(page.entries.get("1").log.textContent, createLog("1"));
    assert.equal(page.entries.get("2").log.textContent, createLog("2"));
});
