import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

import { createEvents } from "./support/events.mjs";

const script = readFileSync(new URL("../../src/sanea/core/static/sanea/js/activity-charts.js", import.meta.url), "utf8");

const createPage = () => {
    const payload = {
        labels: ["2026-10-13"], datasets: [{label: "Demo", data: [3660]}],
        units: {hour: "h", minute: "min"},
    };
    const elements = new Map([
        ["activity-chart", {id: "activity-chart", dataset: {activityChart: "activity-chart-data"}}],
        ["activity-chart-data", {textContent: JSON.stringify(payload)}],
    ]);
    const document = {
        ...createEvents(), body: createEvents(), getElementById: (id) => elements.get(id),
        querySelectorAll: () => [...elements.values()].filter((element) => element.dataset?.activityChart),
    };
    const charts = [];
    class Chart {
        constructor(canvas, config) {
            this.canvas = canvas;
            this.config = config;
            this.destroyed = false;
            charts.push(this);
        }
        destroy() {
            this.destroyed = true;
        }
    }
    runInNewContext(script, {document, window: {Chart}});
    return {document, elements, charts};
};

test("statistics initializes the chart and formats durations from the report units", () => {
    const page = createPage();

    page.document.emit("DOMContentLoaded");
    const chart = page.charts[0];

    assert.equal(page.charts.length, 1);
    assert.equal(chart.canvas, page.elements.get("activity-chart"));
    assert.equal(chart.config.type, "bar");
    assert.equal(chart.config.data.datasets[0].data[0], 3660);
    assert.equal(chart.config.options.scales.y.ticks.callback(3660), "1 h 1 min");
    assert.equal(chart.config.options.plugins.tooltip.callbacks.title, undefined);
});

test("dashboard tooltips use the complete interval for the hovered bar without changing its duration", () => {
    const page = createPage();
    page.elements.set("activity-chart-data", {textContent: JSON.stringify({
        labels: [["25.10", "17:00"], ["25.10", "18:00"]],
        datasets: [{label: "Synthetic person", data: [1560, 2040]}],
        units: {hour: "ч", minute: "мин"},
        tooltipTitles: ["25.10.2026 17:00 — 25.10.2026 18:00", "25.10.2026 18:00 — 25.10.2026 19:00"],
    })});

    page.document.emit("DOMContentLoaded");
    const callbacks = page.charts[0].config.options.plugins.tooltip.callbacks;

    assert.equal(callbacks.title([{dataIndex: 0}]), "25.10.2026 17:00 — 25.10.2026 18:00");
    assert.equal(callbacks.title([{dataIndex: 1}]), "25.10.2026 18:00 — 25.10.2026 19:00");
    assert.equal(callbacks.label({dataset: {label: "Synthetic person"}, raw: 1560}), "Synthetic person: 26 мин");
    assert.equal(callbacks.label({dataset: {label: "Synthetic person"}, raw: 2040}), "Synthetic person: 34 мин");
});

test("filter changes recreate the chart only after HTMX has settled canvas attributes", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");
    const refreshedCanvas = {id: "activity-chart", dataset: {activityChart: "activity-chart-data"}};
    page.elements.set("activity-chart", refreshedCanvas);

    page.document.body.emit("htmx:afterSwap");
    assert.equal(page.charts.length, 1);
    assert.equal(page.charts[0].destroyed, false);
    page.document.body.emit("htmx:afterSettle");

    assert.equal(page.charts.length, 2);
    assert.equal(page.charts[0].destroyed, true);
    assert.equal(page.charts[1].canvas, refreshedCanvas);
});

test("history restoration redraws the chart and leaving statistics releases it", () => {
    const page = createPage();
    page.document.emit("DOMContentLoaded");

    page.document.body.emit("htmx:historyRestore");
    assert.equal(page.charts.length, 2);
    assert.equal(page.charts[0].destroyed, true);
    page.elements.delete("activity-chart");
    page.document.body.emit("htmx:afterSettle");

    assert.equal(page.charts[1].destroyed, true);
    assert.equal(page.charts.length, 2);
});

test("dashboard renders two independent charts with duration axes and redraws both after refresh", () => {
    const page = createPage();
    page.elements.set("applications-chart", {
        id: "applications-chart", dataset: {activityChart: "applications-data"},
    });
    page.elements.set("applications-data", {textContent: JSON.stringify({
        labels: ["Synthetic app"], datasets: [{label: "Time", data: [3660]}],
        units: {hour: "ч", minute: "мин"}, indexAxis: "y",
    })});

    page.document.emit("DOMContentLoaded");
    const applications = page.charts[1];

    assert.equal(page.charts.length, 2);
    assert.equal(applications.config.options.indexAxis, "y");
    assert.equal(applications.config.options.scales.x.ticks.callback(3660), "1 ч 1 мин");
    assert.equal(applications.config.options.scales.y.ticks.autoSkip, false);
    assert.equal(applications.config.options.plugins.legend.display, false);
    assert.equal(applications.config.options.scales.x.stacked, false);
    assert.equal(applications.config.options.plugins.tooltip.callbacks.title, undefined);
    assert.equal(page.charts[0].config.options.scales.y.stacked, true);
    assert.equal(applications.config.options.plugins.tooltip.callbacks.label({
        dataset: {label: "Время"}, raw: 3660,
    }), "Время: 1 ч 1 мин");

    page.document.body.emit("htmx:afterSettle");

    assert.equal(page.charts.length, 4);
    assert.equal(page.charts[0].destroyed, true);
    assert.equal(page.charts[1].destroyed, true);
});

test("a missing chart payload does not prevent the remaining charts from rendering", () => {
    const page = createPage();
    page.elements.set("missing-chart", {id: "missing-chart", dataset: {activityChart: "missing-data"}});

    page.document.emit("DOMContentLoaded");

    assert.equal(page.charts.length, 1);
});
