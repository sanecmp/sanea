(() => {
    "use strict";

    const positions = new Map();
    let activeComputer = null;
    let isRestoringTabs = false;
    const getLog = (computer) => document.getElementById(`log-text-${computer}`);

    const rememberLog = (log) => {
        if (!log.closest(".tab-pane").classList.contains("active")) {
            return;
        }
        positions.set(log.dataset.logComputer, {
            top: log.scrollTop,
            left: log.scrollLeft,
            following: log.scrollHeight - log.clientHeight - log.scrollTop <= 16,
        });
    };

    const positionLog = (computer) => {
        const log = getLog(computer);
        if (!log) {
            return;
        }
        const saved = positions.get(computer);
        log.scrollTop = !saved || saved.following ? log.scrollHeight : saved.top;
        log.scrollLeft = saved?.left || 0;
    };

    const restoreLogs = () => {
        const root = document.getElementById("diagnostic-logs");
        if (!root) {
            return;
        }
        const present = new Set([...root.querySelectorAll("pre[data-log-computer]")].map((log) => log.dataset.logComputer));
        for (const computer of positions.keys()) {
            if (!present.has(computer)) {
                positions.delete(computer);
            }
        }
        const selected = document.getElementById(`log-tab-${activeComputer}`);
        if (selected && window.bootstrap) {
            isRestoringTabs = true;
            try {
                window.bootstrap.Tab.getOrCreateInstance(selected).show();
            } finally {
                isRestoringTabs = false;
            }
        }
        activeComputer = root.querySelector(".nav-link.active")?.dataset.logComputer || null;
        positionLog(activeComputer);
        const selection = document.getElementById("diagnostic-computer");
        if (selection) {
            selection.value = activeComputer || "";
        }
    };

    document.addEventListener("DOMContentLoaded", restoreLogs);
    document.body.addEventListener("htmx:beforeSwap", (event) => {
        if (["diagnostic-logs", "issues-content"].includes(event.detail.target.id) && event.detail.shouldSwap) {
            document.querySelectorAll("pre[data-log-computer]").forEach(rememberLog);
        }
    });
    document.body.addEventListener("htmx:afterSettle", (event) => {
        if (["diagnostic-logs", "issues-content"].includes(event.detail.target.id)) {
            restoreLogs();
        }
    });
    document.body.addEventListener("htmx:historyRestore", () => {
        positions.clear();
        activeComputer = new URL(window.location.href).searchParams.get("log");
        restoreLogs();
    });
    document.body.addEventListener("hide.bs.tab", (event) => {
        if (!isRestoringTabs && event.target.dataset.logComputer) {
            rememberLog(getLog(event.target.dataset.logComputer));
        }
    });
    document.body.addEventListener("shown.bs.tab", (event) => {
        const computer = event.target.dataset.logComputer;
        if (!computer) {
            return;
        }
        activeComputer = computer;
        document.getElementById("diagnostic-computer").value = computer;
        window.history.replaceState(window.history.state, "", event.target.href);
        positionLog(computer);
    });
    document.addEventListener("scroll", (event) => {
        if (event.target.matches?.("pre[data-log-computer]")) {
            rememberLog(event.target);
        }
    }, true);
    document.body.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-log-copy]");
        if (!button || button.disabled) {
            return;
        }
        const status = document.getElementById(`log-copy-status-${button.dataset.logCopy}`);
        button.disabled = true;
        try {
            await window.navigator.clipboard.writeText(getLog(button.dataset.logCopy).textContent);
            status.textContent = button.dataset.copySuccess;
        } catch {
            status.textContent = button.dataset.copyError;
        } finally {
            button.disabled = false;
        }
    });
})();
