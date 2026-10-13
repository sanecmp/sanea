(() => {
    "use strict";

    const positions = new Map();
    let activeComputer = null;
    let isRestoringTabs = false;
    let focusedLatest = null;
    const isAtEnd = (log) => log.scrollHeight - log.clientHeight - log.scrollTop <= 16;
    const getReceived = (computer) => document.getElementById(`log-received-${computer}`);
    const getLog = (computer) => document.getElementById(`log-text-${computer}`);
    const getLatestButton = (computer) => document.querySelector(`[data-log-latest="${computer}"]`);

    const rememberLog = (log) => {
        const computer = log.dataset.logComputer;
        const previous = positions.get(computer) || { following: true, initialized: false };
        if (log.closest(".tab-pane").classList.contains("active")) {
            previous.top = log.scrollTop;
            previous.left = log.scrollLeft;
            previous.following = isAtEnd(log);
        }
        previous.text = log.textContent;
        previous.received = getReceived(computer).textContent;
        positions.set(computer, previous);
    };

    const positionLog = (computer) => {
        const log = getLog(computer);
        const saved = positions.get(computer);
        if (!log || !saved) {
            return;
        }
        log.scrollTop = !saved.initialized || saved.following ? log.scrollHeight : saved.top;
        log.scrollLeft = saved.left || 0;
        saved.initialized = true;
    };

    const showLatest = (computer) => {
        const saved = positions.get(computer);
        if (!saved?.pending) {
            return;
        }
        getLog(computer).textContent = saved.pending.text;
        getReceived(computer).textContent = saved.pending.received;
        saved.text = saved.pending.text;
        saved.received = saved.pending.received;
        saved.pending = null;
        saved.following = true;
        const button = getLatestButton(computer);
        const hadFocus = document.activeElement === button;
        button.hidden = true;
        positionLog(computer);
        if (hadFocus) {
            getLog(computer).focus({ preventScroll: true });
        }
    };

    const restoreLogs = () => {
        const root = document.getElementById("diagnostic-logs");
        if (!root) {
            return;
        }
        const present = new Set();
        root.querySelectorAll("pre[data-log-computer]").forEach((log) => {
            const computer = log.dataset.logComputer;
            present.add(computer);
            const saved = positions.get(computer) || { following: true, initialized: false };
            const latest = { text: log.textContent, received: getReceived(computer).textContent };
            // Keep the snapshot being read, even if sanex has rotated its bounded log tail.
            if (saved.initialized && !saved.following && saved.text !== latest.text) {
                saved.pending = latest;
                log.textContent = saved.text;
                getReceived(computer).textContent = saved.received;
            } else {
                saved.pending = null;
                saved.text = latest.text;
                saved.received = latest.received;
            }
            positions.set(computer, saved);
            getLatestButton(computer).hidden = !saved.pending;
        });
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
    };

    document.addEventListener("DOMContentLoaded", restoreLogs);
    document.body.addEventListener("htmx:beforeSwap", (event) => {
        if (!["diagnostic-logs", "issues-content"].includes(event.detail.target.id) || !event.detail.shouldSwap) {
            return;
        }
        document.querySelectorAll("pre[data-log-computer]").forEach(rememberLog);
        const focused = document.activeElement;
        focusedLatest = focused?.matches("[data-log-latest]") ? focused.id : null;
    });
    document.body.addEventListener("htmx:afterSettle", (event) => {
        if (["diagnostic-logs", "issues-content"].includes(event.detail.target.id)) {
            restoreLogs();
            const focused = document.getElementById(focusedLatest);
            if (focused && !focused.hidden && document.activeElement === document.body) {
                focused.focus({ preventScroll: true });
            }
            focusedLatest = null;
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
        const log = event.target;
        if (log.matches?.("pre[data-log-computer]")) {
            rememberLog(log);
            if (isAtEnd(log)) {
                showLatest(log.dataset.logComputer);
            }
        }
    }, true);
    document.body.addEventListener("click", (event) => {
        const button = event.target.closest("[data-log-latest]");
        if (button) {
            showLatest(button.dataset.logLatest);
        }
    });
    document.addEventListener("visibilitychange", () => {
        const root = document.getElementById("diagnostic-logs");
        if (!document.hidden && root && window.htmx) {
            window.htmx.trigger(root, "diagnostic-refresh");
        }
    });
})();
