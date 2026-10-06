"use strict";

(() => {
    let chart = null;

    const renderChart = () => {
        const canvas = document.getElementById("activity-chart");
        const dataNode = document.getElementById("activity-chart-data");
        if (!canvas || !dataNode || !window.Chart) {
            if (chart) {
                chart.destroy();
                chart = null;
            }
            return;
        }
        const payload = JSON.parse(dataNode.textContent);
        const units = payload.units;
        const formatDuration = (value) => {
            const hours = Math.floor(value / 3600);
            const minutes = Math.floor((value % 3600) / 60);
            if (hours) {
                return `${hours} ${units.hour} ${minutes} ${units.minute}`;
            }
            return `${minutes} ${units.minute}`;
        };
        if (chart) {
            chart.destroy();
        }
        chart = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: payload.labels,
                datasets: payload.datasets,
            },
            options: {
                maintainAspectRatio: false,
                responsive: true,
                interaction: {
                    intersect: false,
                    mode: "index",
                },
                plugins: {
                    legend: {
                        position: "bottom",
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => `${context.dataset.label}: ${formatDuration(context.raw)}`,
                        },
                    },
                },
                scales: {
                    x: {
                        stacked: true,
                        grid: {
                            display: false,
                        },
                    },
                    y: {
                        beginAtZero: true,
                        stacked: true,
                        ticks: {
                            callback: (value) => formatDuration(value),
                        },
                    },
                },
            },
        });
    };

    document.addEventListener("DOMContentLoaded", renderChart);
    document.body.addEventListener("htmx:afterSwap", renderChart);
})();
