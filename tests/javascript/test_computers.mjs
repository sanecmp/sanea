import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/computers.js", import.meta.url), "utf8");

const createRegion = (id, content, scroller = null, commands = []) => ({
    id, content,
    get innerHTML() { return this.content + commands.map((command) => `${command.id}:${command.open}`).join(";"); },
    get outerHTML() { return `${this.id}:${this.innerHTML}`; },
    querySelector(selector) {
        return selector === ".table-responsive" ? scroller : commands.find((command) => selector === `#${command.id}`);
    },
    querySelectorAll: () => commands.filter((command) => command.open),
});

const createPage = (refreshId = "computer-live-refresh") => {
    const body = createEvents();
    const refresh = { id: refreshId };
    const elements = new Map([[refreshId, refresh]]);
    const document = {
        ...createEvents(), body, hidden: false,
        getElementById: (id) => elements.get(id),
    };
    const requests = [];
    const window = { htmx: { trigger: (...args) => requests.push(args) } };
    const responses = new Map();
    class DOMParser {
        parseFromString(response) {
            return { getElementById: (id) => responses.get(response)?.id === id ? responses.get(response) : null };
        }
    }
    runInNewContext(script, { document, window, DOMParser });
    return { document, window, body, elements, requests, refresh, responses };
};

const buildSwap = (page, target, response = "result") => ({
    target, requestConfig: { elt: page.refresh }, shouldSwap: true, serverResponse: response,
});

test("unchanged background markup is not swapped, leaving horizontal scroll and table focus untouched", () => {
    const page = createPage();
    const scroller = { scrollLeft: 240, scrollTop: 12 };
    const target = createRegion("computer-table", "same rows", scroller);
    page.responses.set("result", createRegion(target.id, "same rows"));
    const detail = buildSwap(page, target);

    page.body.emit("htmx:beforeSwap", { detail });

    assert.equal(detail.shouldSwap, false);
    assert.equal(scroller.scrollLeft, 240);
    assert.equal(scroller.scrollTop, 12);
});

test("changed rows are swapped and horizontal scroll is restored on the replacement table", () => {
    const page = createPage();
    const target = createRegion("computer-table", "old rows", { scrollLeft: 240, scrollTop: 12 });
    const refreshedScroller = { scrollLeft: 0, scrollTop: 0 };
    const replacement = createRegion(target.id, "new rows", refreshedScroller);
    page.responses.set("result", replacement);
    const detail = buildSwap(page, target);

    page.body.emit("htmx:beforeSwap", { detail });
    page.elements.set(target.id, replacement);
    page.body.emit("htmx:afterSwap", { detail: { target } });

    assert.equal(detail.shouldSwap, true);
    assert.equal(detail.serverResponse, replacement.outerHTML);
    assert.equal(refreshedScroller.scrollLeft, 240);
    assert.equal(refreshedScroller.scrollTop, 12);
});

test("out-of-band saves and explicit filter replacements also retain table scroll", () => {
    const page = createPage();
    const target = createRegion("computer-table", "old", { scrollLeft: 180, scrollTop: 0 });
    const scroller = { scrollLeft: 0, scrollTop: 0 };
    page.body.emit("htmx:oobBeforeSwap", { detail: { target } });
    page.elements.set(target.id, createRegion(target.id, "saved", scroller));
    page.body.emit("htmx:oobAfterSwap", { detail: { target } });
    assert.equal(scroller.scrollLeft, 180);

    const filterTarget = createRegion("computer-list", "old filter", { scrollLeft: 90, scrollTop: 0 });
    const detail = { target: filterTarget, requestConfig: { elt: { id: "computer-filter" } }, shouldSwap: true };
    page.body.emit("htmx:beforeSwap", { detail });
    page.elements.set(filterTarget.id, createRegion(filterTarget.id, "new filter", scroller));
    page.body.emit("htmx:afterSwap", { detail });
    assert.equal(scroller.scrollLeft, 90);
});

test("background requests and in-flight responses pause for both read-only and editable computer dialogs", () => {
    const page = createPage();
    page.elements.set("computer-editor", { querySelector: () => ({}) });
    let prevented = false;
    const event = { detail: { elt: page.refresh }, preventDefault: () => { prevented = true; } };
    const detail = buildSwap(page, createRegion("computer-table", "rows"));

    page.body.emit("htmx:beforeRequest", event);
    page.body.emit("htmx:beforeSwap", { detail });
    assert.equal(prevented, true);
    assert.equal(detail.shouldSwap, false);

    page.elements.delete("computer-editor");
    prevented = false;
    detail.shouldSwap = true;
    page.body.emit("htmx:beforeRequest", event);
    page.body.emit("htmx:beforeSwap", { detail });
    assert.equal(prevented, false);
    assert.equal(detail.shouldSwap, true);
});

test("explicit dialog and filter requests are never blocked by the background refresh guard", () => {
    const page = createPage();
    page.elements.set("computer-editor", { querySelector: () => ({}) });

    for (const id of ["computer-save", "computer-configure-12", "computer-details-open-12", "computer-filter", "command-filter"]) {
        const detail = { target: createRegion("computer-editor", "details"), requestConfig: { elt: { id } }, shouldSwap: true };
        page.body.emit("htmx:beforeRequest", {
            detail: { elt: { id } }, preventDefault: () => assert.fail(`Blocked explicit request ${id}`),
        });
        page.body.emit("htmx:beforeSwap", { detail });
        assert.equal(detail.shouldSwap, true);
    }
});

test("command polling retains expanded rows while applying new statuses, and skips truly unchanged results", () => {
    const page = createPage("command-live-refresh");
    const current = createRegion("command-history-results", "pending", null, [
        { id: "command-12", open: true }, { id: "command-removed", open: true },
    ]);
    const refreshedCommand = { id: "command-12", open: false };
    const replacement = createRegion(current.id, "done", null, [refreshedCommand]);
    page.responses.set("result", replacement);
    const detail = buildSwap(page, current);

    page.body.emit("htmx:beforeSwap", { detail });
    assert.equal(detail.shouldSwap, true);
    assert.equal(refreshedCommand.open, true);
    assert.match(detail.serverResponse, /done/);

    page.responses.set("result", createRegion(current.id, "done", null, [{ id: "command-12", open: false }]));
    const unchanged = buildSwap(page, replacement);
    page.body.emit("htmx:beforeSwap", { detail: unchanged });
    assert.equal(unchanged.shouldSwap, false);
});

test("cancelled swaps do not record stale scroll state", () => {
    const page = createPage();
    const target = createRegion("computer-table", "old", { scrollLeft: 50, scrollTop: 0 });
    const detail = { ...buildSwap(page, target), shouldSwap: false };
    page.body.emit("htmx:beforeSwap", { detail });
    const scroller = { scrollLeft: 130, scrollTop: 0 };
    page.elements.set(target.id, createRegion(target.id, "new", scroller));
    page.body.emit("htmx:afterSwap", { detail });
    assert.equal(scroller.scrollLeft, 130);
});

test("visibility refresh uses only the current page and is harmless without HTMX", () => {
    const page = createPage("command-live-refresh");
    page.document.hidden = true;
    page.document.emit("visibilitychange");
    assert.equal(page.requests.length, 0);
    page.document.hidden = false;
    page.document.emit("visibilitychange");
    assert.deepEqual(page.requests, [[page.refresh, "computer-refresh"]]);
    delete page.window.htmx;
    page.document.emit("visibilitychange");
    assert.equal(page.requests.length, 1);
});
