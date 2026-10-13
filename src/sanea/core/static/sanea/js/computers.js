(() => {
    "use strict";

    const hashTabs = {
        "#computer-list": "computers",
        "#command-history": "commands",
        "#registration-window": "registration",
        "#sanex-updates": "updates",
    };

    const showTab = (name) => {
        const tab = document.getElementById(`${name}-tab`);
        if (tab && window.bootstrap) {
            window.bootstrap.Tab.getOrCreateInstance(tab).show();
        }
    };

    const restoreTab = () => {
        const url = new URL(window.location.href);
        const requested = url.searchParams.get("tab") || hashTabs[url.hash];
        const hasCommands = ["command_computer", "command_type", "command_status", "command_page"]
            .some((field) => url.searchParams.get(field));
        const fallback = hasCommands ? "commands" : "computers";
        showTab(document.getElementById(`${requested}-tab`) ? requested : fallback);
    };

    document.addEventListener("DOMContentLoaded", restoreTab);
    window.addEventListener("popstate", restoreTab);
    window.addEventListener("hashchange", restoreTab);
    document.body.addEventListener("htmx:historyRestore", restoreTab);

    document.body.addEventListener("shown.bs.tab", (event) => {
        const name = event.target.dataset.computerTab;
        if (!name) {
            return;
        }
        const url = new URL(window.location.href);
        url.searchParams.set("tab", name);
        url.hash = "";
        window.history.replaceState(window.history.state, "", url);
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
        if (event.detail.target.id === "command-history") {
            showTab("commands");
        }
    });

    document.body.addEventListener("htmx:oobBeforeSwap", (event) => {
        const { target, fragment } = event.detail;
        if (target.id !== "command-history-results") {
            return;
        }
        target.querySelectorAll("details[open]").forEach((command) => {
            const refreshed = fragment.querySelector(`#${command.id}`);
            if (refreshed) {
                refreshed.open = true;
            }
        });
    });

    document.addEventListener("visibilitychange", () => {
        const refresh = document.getElementById("computer-live-refresh");
        if (!document.hidden && refresh && window.htmx) {
            window.htmx.trigger(refresh, "computer-refresh");
        }
    });
})();
