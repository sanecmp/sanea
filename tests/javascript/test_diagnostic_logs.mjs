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

const createPage = (snapshots = [createSnapshot("1"), createSnapshot("2")], path = "/issues/?period=day") => {
    const elements = new Map();
    const entries = new Map();
    const body = { ...createEvents(), matches: () => false };
    const shown = [];
    const requests = [];
    const document = {
        ...createEvents(), body, hidden: false, activeElement: body,
        getElementById: (id) => elements.get(id),
        querySelectorAll: () => elements.has("diagnostic-logs") ? [...entries.values()].map((entry) => entry.log) : [],
        querySelector: (selector) => entries.get(selector.match(/data-log-latest="([^"]+)"/)?.[1])?.button,
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
                id: `log-latest-${computer}`, dataset: { logLatest: computer }, hidden: true,
                closest: (selector) => selector === "[data-log-latest]" ? button : null,
                matches: (selector) => selector === "[data-log-latest]",
                focus: () => { document.activeElement = button; },
            };
            entries.set(computer, { panel, tab, log, timestamp, button });
            for (const element of [tab, log, timestamp, button]) {
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
    return { document, window, body, elements, entries, shown, requests, render, swap, select, scroll };
};

test("the selected log starts at its tail and opening another machine initializes its own scroll", () => {
    const page = createPage(undefined, "/issues/?period=day&computer=2&log=2");

    page.document.emit("DOMContentLoaded");

    assert.equal(page.entries.get("2").log.scrollTop, 500);
    assert.equal(page.entries.get("1").log.scrollTop, 0);

    page.select("1");

    assert.equal(page.entries.get("1").log.scrollTop, 500);
    assert.equal(page.elements.get("diagnostic-computer").value, "1");
    const url = new URL(page.window.location.href);
    assert.equal(url.searchParams.get("log"), "1");
    assert.equal(url.searchParams.get("period"), "day");
    assert.equal(url.searchParams.get("computer"), "2");
    assert.deepEqual(page.window.history.state, { htmx: true });
});

test("background updates follow the tail and retain horizontal scrolling", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 500, 40);
    const latest = createSnapshot("1", createLog("updated", 35), "received 13:01");

    page.swap([latest, createSnapshot("2")]);
    const { log, timestamp, button } = page.entries.get("1");

    assert.equal(log.textContent, latest.text);
    assert.equal(timestamp.textContent, latest.received);
    assert.equal(log.scrollTop, 600);
    assert.equal(log.scrollLeft, 40);
    assert.equal(button.hidden, true);
});

for (const [name, content] of [
    ["appended", `${createLog("1")}\nSynthetic new line`],
    ["rotated", createLog("rotated", 20)],
]) {
    test(`${name} logs preserve the snapshot being read until New lines is clicked`, () => {
        const original = createSnapshot("1");
        const page = createPage([original]);
        page.document.emit("DOMContentLoaded");
        page.scroll("1", 120, 35);

        page.swap([createSnapshot("1", content, "received 13:01")]);
        const first = page.entries.get("1");

        assert.equal(first.log.textContent, original.text);
        assert.equal(first.timestamp.textContent, original.received);
        assert.equal(first.log.scrollTop, 120);
        assert.equal(first.log.scrollLeft, 35);
        assert.equal(first.button.hidden, false);

        const latest = createSnapshot("1", `${content}\nSynthetic newest line`, "received 13:02");
        page.swap([latest]);
        const refreshed = page.entries.get("1");

        assert.equal(refreshed.log.textContent, original.text);
        assert.equal(refreshed.log.scrollTop, 120);
        assert.equal(refreshed.button.hidden, false);

        page.body.emit("click", { target: { closest: () => refreshed.button } });

        assert.equal(refreshed.log.textContent, latest.text);
        assert.equal(refreshed.timestamp.textContent, latest.received);
        assert.equal(refreshed.log.scrollTop, refreshed.log.scrollHeight - refreshed.log.clientHeight);
        assert.equal(refreshed.log.scrollLeft, 35);
        assert.equal(refreshed.button.hidden, true);
    });
}

test("returning to the bottom shows pending lines and resumes following later updates", () => {
    const page = createPage([createSnapshot("1")]);
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 100);
    page.swap([createSnapshot("1", createLog("pending", 35))]);

    page.scroll("1", 500);
    assert.equal(page.entries.get("1").log.textContent, createLog("pending", 35));
    assert.equal(page.entries.get("1").log.scrollTop, 600);
    assert.equal(page.entries.get("1").button.hidden, true);

    page.swap([createSnapshot("1", createLog("following", 40))]);

    assert.equal(page.entries.get("1").log.textContent, createLog("following", 40));
    assert.equal(page.entries.get("1").log.scrollTop, 700);
});

test("refresh retains the selected machine and independent reading positions on other tabs", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120, 35);
    page.select("2");
    page.scroll("2", 240, 70);

    page.swap([createSnapshot("1", createLog("latest 1")), createSnapshot("2", createLog("latest 2"))]);

    assert.equal(page.entries.get("2").tab.classList.contains("active"), true);
    assert.equal(page.elements.get("diagnostic-computer").value, "2");
    assert.equal(page.entries.get("2").log.scrollTop, 240);
    assert.equal(page.entries.get("2").log.scrollLeft, 70);
    assert.equal(page.entries.get("2").log.textContent, createLog("2"));

    page.select("1");

    assert.equal(page.entries.get("1").log.scrollTop, 120);
    assert.equal(page.entries.get("1").log.scrollLeft, 35);
    assert.equal(page.entries.get("1").log.textContent, createLog("1"));
    assert.equal(page.entries.get("1").button.hidden, false);
    page.body.emit("click", { target: page.entries.get("1").button });
    page.select("2");

    assert.equal(page.entries.get("2").log.textContent, createLog("2"));
    assert.equal(page.entries.get("2").log.scrollTop, 240);
    assert.equal(page.entries.get("2").button.hidden, false);
});

test("machines can arrive, disappear, and reappear with fresh state after an empty result", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.select("2");
    page.scroll("2", 120);

    page.swap([createSnapshot("1"), createSnapshot("2"), createSnapshot("3", createLog("new", 20))]);

    assert.equal(page.entries.get("2").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("3").log.scrollTop, 0);
    page.select("3");
    assert.equal(page.entries.get("3").log.scrollTop, 300);

    page.swap([createSnapshot("1")]);

    assert.equal(page.entries.get("1").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("1").log.scrollTop, 500);
    assert.equal(page.elements.get("diagnostic-computer").value, "1");

    page.swap([]);
    assert.equal(page.entries.size, 0);
    page.swap([createSnapshot("2", createLog("reappeared", 20))]);

    assert.equal(page.entries.get("2").log.textContent, createLog("reappeared", 20));
    assert.equal(page.entries.get("2").log.scrollTop, 300);
    assert.equal(page.entries.get("2").button.hidden, true);
});

test("manual refresh and whole-page filter swaps both retain the selected log and its reading snapshot", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.select("2");
    page.scroll("2", 120);

    page.swap([createSnapshot("1"), createSnapshot("2", createLog("manual"))]);
    page.swap([createSnapshot("1"), createSnapshot("2", createLog("filtered"))], {
        target: "issues-content", path: "http://localhost/issues/?period=week",
    });

    assert.equal(page.entries.get("2").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("2").log.textContent, createLog("2"));
    assert.equal(page.entries.get("2").log.scrollTop, 120);
    assert.equal(page.entries.get("2").button.hidden, false);
    assert.equal(new URL(page.window.location.href).searchParams.get("period"), "week");
});

test("fallback waits for settled HTMX classes when the selected machine disappears", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.select("2");
    const target = { id: "diagnostic-logs" };
    page.body.emit("htmx:beforeSwap", { detail: { target, shouldSwap: true } });
    page.render([createSnapshot("1", createLog("surviving", 35))]);
    const surviving = page.entries.get("1");
    surviving.tab.classList.toggle("active", false);
    surviving.panel.classList.toggle("active", false);

    page.body.emit("htmx:afterSwap", { detail: { target } });

    assert.equal(surviving.log.scrollTop, 0);
    assert.equal(surviving.panel.classList.contains("active"), false);
    surviving.tab.classList.toggle("active", true);
    surviving.panel.classList.toggle("active", true);
    page.body.emit("htmx:afterSettle", { detail: { target } });

    assert.equal(surviving.tab.classList.contains("active"), true);
    assert.equal(surviving.log.scrollTop, 600);
    assert.equal(page.elements.get("diagnostic-computer").value, "1");
});

test("pending New lines retains keyboard focus across polling and moves focus into the shown log", () => {
    const page = createPage([createSnapshot("1")]);
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120);
    page.swap([createSnapshot("1", createLog("pending", 35))]);
    const previous = page.entries.get("1").button;
    previous.focus();

    page.swap([createSnapshot("1", createLog("latest", 40))]);
    const refreshed = page.entries.get("1");

    assert.notEqual(refreshed.button, previous);
    assert.equal(refreshed.button.hidden, false);
    assert.equal(page.document.activeElement, refreshed.button);
    assert.equal(refreshed.log.textContent, createLog("1"));
    assert.equal(refreshed.log.scrollTop, 120);

    page.body.emit("click", { target: refreshed.button });

    assert.equal(page.document.activeElement, refreshed.log);
    assert.equal(refreshed.button.hidden, true);
    assert.equal(refreshed.log.textContent, createLog("latest", 40));
    assert.equal(refreshed.log.scrollTop, 700);
});

test("HTMX history restoration discards paused snapshots and opens the machine from the restored URL", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120);
    page.select("2");
    const restored = createSnapshot("1", createLog("history", 20));
    page.render([restored, createSnapshot("2")], { active: "2" });
    page.window.location.href = "http://localhost/issues/?period=day&log=1";

    page.body.emit("htmx:historyRestore");

    assert.equal(page.entries.get("1").tab.classList.contains("active"), true);
    assert.equal(page.entries.get("1").log.textContent, restored.text);
    assert.equal(page.entries.get("1").log.scrollTop, 300);
    assert.equal(page.entries.get("1").button.hidden, true);
});

test("visibility refresh runs only with a visible log section and available HTMX", () => {
    const page = createPage([]);
    const root = page.elements.get("diagnostic-logs");

    page.document.hidden = true;
    page.document.emit("visibilitychange");
    assert.equal(page.requests.length, 0);
    page.document.hidden = false;
    page.document.emit("visibilitychange");
    assert.deepEqual(page.requests, [[root, "diagnostic-refresh"]]);
    page.elements.delete(root.id);
    page.document.emit("visibilitychange");
    page.elements.set(root.id, root);
    delete page.window.htmx;
    page.document.emit("visibilitychange");

    assert.equal(page.requests.length, 1);
});

test("unrelated or cancelled swaps, unrelated tabs, and missing libraries do not disturb the log", () => {
    const page = createPage([createSnapshot("1")]);
    page.document.emit("DOMContentLoaded");
    page.scroll("1", 120);
    delete page.window.bootstrap;
    delete page.window.htmx;

    page.body.emit("htmx:beforeSwap", { detail: { target: { id: "diagnostic-logs" }, shouldSwap: false } });
    page.body.emit("htmx:beforeSwap", { detail: { target: { id: "other" }, shouldSwap: true } });
    page.body.emit("htmx:afterSwap", { detail: { target: { id: "other" } } });
    page.body.emit("htmx:afterSettle", { detail: { target: { id: "other" } } });
    page.body.emit("hide.bs.tab", { target: { dataset: {} } });
    page.body.emit("shown.bs.tab", { target: { dataset: {} } });
    page.body.emit("click", { target: { closest: () => null } });
    page.document.emit("scroll", { target: {} });
    page.document.emit("visibilitychange");
    page.swap([createSnapshot("1", createLog("updated"))]);

    assert.equal(page.entries.get("1").log.textContent, createLog("1"));
    assert.equal(page.entries.get("1").log.scrollTop, 120);
    assert.equal(page.entries.get("1").button.hidden, false);
    assert.equal(page.requests.length, 0);
});
