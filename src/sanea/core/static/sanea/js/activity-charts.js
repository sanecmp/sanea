"use strict";

(() => {
    const charts = new Map();

    const renderChart = (canvas, dataNode) => {
        const payload = JSON.parse(dataNode.textContent);
        const units = payload.units;
        const horizontal = payload.indexAxis === "y";
        const formatDuration = (value) => {
            const hours = Math.floor(value / 3600);
            const minutes = Math.floor((value % 3600) / 60);
            if (hours) {
                return `${hours} ${units.hour} ${minutes} ${units.minute}`;
            }
            return `${minutes} ${units.minute}`;
        };
        const durationAxis = {
            beginAtZero: true,
            stacked: !horizontal,
            ticks: {
                maxTicksLimit: 8,
                callback: (value) => formatDuration(value),
            },
        };
        const labelAxis = {
            stacked: !horizontal,
            grid: {display: false},
            ticks: horizontal ? {autoSkip: false} : {maxRotation: 0, maxTicksLimit: 8},
        };
        return new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: payload.labels,
                datasets: payload.datasets,
            },
            options: {
                indexAxis: horizontal ? "y" : "x",
                animation: false,
                maintainAspectRatio: false,
                responsive: true,
                interaction: {
                    intersect: false,
                    mode: horizontal ? "nearest" : "index",
                    axis: horizontal ? "y" : "x",
                },
                plugins: {
                    legend: {
                        position: "bottom",
                        display: !horizontal,
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => `${context.dataset.label}: ${formatDuration(context.raw)}`,
                        },
                    },
                },
                scales: {
                    x: horizontal ? durationAxis : labelAxis,
                    y: horizontal ? labelAxis : durationAxis,
                },
            },
        });
    };

    const renderCharts = () => {
        for (const chart of charts.values()) {
            chart.destroy();
        }
        charts.clear();
        if (!window.Chart) {
            return;
        }
        for (const canvas of document.querySelectorAll("canvas[data-activity-chart]")) {
            const dataNode = document.getElementById(canvas.dataset.activityChart);
            if (dataNode) {
                charts.set(canvas.id, renderChart(canvas, dataNode));
            }
        }
    };

    document.addEventListener("DOMContentLoaded", renderCharts);
    // HTMX restores canvas attributes during settling, which clears earlier drawings.
    document.body.addEventListener("htmx:afterSettle", renderCharts);
    document.body.addEventListener("htmx:historyRestore", renderCharts);
})();
