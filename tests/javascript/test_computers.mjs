import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/computers.js", import.meta.url), "utf8");

const createPage = (path = "/computers/") => {
    const body = createEvents();
    const elements = new Map(["computers", "commands", "registration", "updates"].map((name) => [
        `${name}-tab`, { id: `${name}-tab`, dataset: { computerTab: name } },
    ]));
    const refresh = { id: "computer-live-refresh" };
    elements.set(refresh.id, refresh);
    const document = {
        ...createEvents(), body, hidden: false,
        getElementById: (id) => elements.get(id),
    };
    const shown = [];
    const requests = [];
    let active = "computers";
    const window = {
        ...createEvents(),
        location: { href: `http://localhost${path}` },
        history: {
            state: { htmx: true },
            replaceState(state, title, url) {
                this.state = state;
                window.location.href = url.href;
            },
        },
        bootstrap: {
            Tab: {
                getOrCreateInstance(tab) {
                    return {
                        show() {
                            const name = tab.dataset.computerTab;
                            shown.push(name);
                            if (active !== name) {
                                active = name;
                                body.emit("shown.bs.tab", { target: tab });
                            }
                        },
                    };
                },
            },
        },
        htmx: { trigger: (...args) => requests.push(args) },
    };
    runInNewContext(script, { document, window, URL });
    return { document, window, body, elements, shown, requests, refresh };
};

test("direct command links open history, and tab changes retain filters and pagination", () => {
    const page = createPage("/computers/?access=allowed&command_status=failed&command_page=2#command-history");

    page.document.emit("DOMContentLoaded");
    page.body.emit("shown.bs.tab", { target: page.elements.get("updates-tab") });
    const url = new URL(page.window.location.href);

    assert.deepEqual(page.shown, ["commands"]);
    assert.equal(url.searchParams.get("tab"), "updates");
    assert.equal(url.searchParams.get("access"), "allowed");
    assert.equal(url.searchParams.get("command_status"), "failed");
    assert.equal(url.searchParams.get("command_page"), "2");
    assert.equal(url.hash, "");
    assert.deepEqual(page.window.history.state, { htmx: true });
});

test("URL and HTMX history restoration select the intended pane including the default", () => {
    const page = createPage("/computers/?tab=registration");

    page.document.emit("DOMContentLoaded");
    page.window.location.href = "http://localhost/computers/";
    page.window.emit("popstate");
    page.window.location.href = "http://localhost/computers/#sanex-updates";
    page.window.emit("hashchange");
    page.window.location.href = "http://localhost/computers/?tab=computers&command_status=failed";
    page.body.emit("htmx:historyRestore");

    assert.deepEqual(page.shown, ["registration", "computers", "updates", "computers"]);
});

test("history responses open the commands pane but background table refreshes do not", () => {
    const page = createPage();

    page.body.emit("htmx:afterSwap", { detail: { target: { id: "computer-table" } } });
    page.body.emit("htmx:afterSwap", { detail: { target: { id: "command-history" } } });

    assert.deepEqual(page.shown, ["commands"]);
});

test("background history refresh keeps surviving commands expanded without retaining stale content", () => {
    const page = createPage();
    const refreshed = { id: "command-12", open: false, status: "done" };
    const target = {
        id: "command-history-results",
        querySelectorAll: () => [{ id: "command-12" }, { id: "command-removed" }],
    };
    const fragment = { querySelector: (selector) => selector === "#command-12" ? refreshed : null };

    page.body.emit("htmx:oobBeforeSwap", { detail: { target, fragment } });

    assert.equal(refreshed.open, true);
    assert.equal(refreshed.status, "done");
});

test("visibility changes refresh only when the computers page becomes visible", () => {
    const page = createPage();

    page.document.hidden = true;
    page.document.emit("visibilitychange");
    assert.equal(page.requests.length, 0);
    page.document.hidden = false;
    page.document.emit("visibilitychange");
    assert.deepEqual(page.requests, [[page.refresh, "computer-refresh"]]);
    page.elements.delete(page.refresh.id);
    page.document.emit("visibilitychange");
    assert.equal(page.requests.length, 1);
});

test("missing JavaScript libraries and unrelated Bootstrap tabs are harmless", () => {
    const page = createPage("/computers/?tab=commands");
    delete page.window.bootstrap;
    delete page.window.htmx;

    page.document.emit("DOMContentLoaded");
    page.document.emit("visibilitychange");
    page.body.emit("shown.bs.tab", { target: { dataset: {} } });

    assert.equal(page.shown.length, 0);
    assert.equal(page.requests.length, 0);
    assert.equal(new URL(page.window.location.href).searchParams.get("tab"), "commands");
});
