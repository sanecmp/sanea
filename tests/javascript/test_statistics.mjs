import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/statistics.js", import.meta.url), "utf8");

test("recent activity keeps the selected kind in subsequent filter submissions, including after a swap", () => {
    let field = {value: "application"};
    const body = createEvents();
    const document = {...createEvents(), body, getElementById: (identifier) => identifier === "recent-activity-kind" ? field : null};
    runInNewContext(script, {document, window: {}});

    body.emit("shown.bs.tab", {target: {dataset: {activityKind: "session"}}});
    assert.equal(field.value, "session");

    field = {value: "session"};
    body.emit("shown.bs.tab", {target: {dataset: {activityKind: "application"}}});
    assert.equal(field.value, "application");

    body.emit("shown.bs.tab", {target: {dataset: {}}});
    body.emit("shown.bs.tab", {target: {dataset: {activityKind: "unknown"}}});
    assert.equal(field.value, "application");

    field = null;
    assert.doesNotThrow(() => body.emit("shown.bs.tab", {target: {dataset: {activityKind: "session"}}}));
});
