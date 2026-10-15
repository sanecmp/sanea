(() => {
    "use strict";

    const scrollPositions = new Map();
    const refreshIds = new Set(["computer-live-refresh", "command-live-refresh"]);
    const isBackground = (source) => refreshIds.has(source?.id);
    const shouldPauseRefresh = (source) => source?.id === "computer-live-refresh"
        && Boolean(document.getElementById("computer-editor")?.querySelector("[data-dialog-panel]"));

    const rememberScroll = (target) => {
        const scroller = target?.querySelector(".table-responsive");
        if (scroller) {
            scrollPositions.set(target.id, { left: scroller.scrollLeft, top: scroller.scrollTop });
        }
    };

    const restoreScroll = (event) => {
        const targetId = event.detail.target?.id;
        const position = scrollPositions.get(targetId);
        if (!position) {
            return;
        }
        const scroller = document.getElementById(targetId)?.querySelector(".table-responsive");
        if (scroller) {
            scroller.scrollLeft = position.left;
            scroller.scrollTop = position.top;
        }
        scrollPositions.delete(targetId);
    };

    const preserveOpenCommands = (current, refreshed) => {
        if (current.id === "command-history-results") {
            current.querySelectorAll("details[open]").forEach((command) => {
                const replacement = refreshed.querySelector(`#${command.id}`);
                if (replacement) {
                    replacement.open = true;
                }
            });
        }
    };

    document.body.addEventListener("htmx:beforeRequest", (event) => {
        if (shouldPauseRefresh(event.detail.elt)) {
            event.preventDefault();
        }
    });

    document.body.addEventListener("htmx:beforeSwap", (event) => {
        const detail = event.detail;
        const source = detail.requestConfig?.elt;
        if (shouldPauseRefresh(source)) {
            detail.shouldSwap = false;
            return;
        }
        if (!detail.shouldSwap) {
            return;
        }

        if (isBackground(source) && detail.serverResponse) {
            const refreshed = new DOMParser().parseFromString(detail.serverResponse, "text/html")
                .getElementById(detail.target.id);
            if (refreshed) {
                preserveOpenCommands(detail.target, refreshed);
                // Compare parsed markup, ignoring request classes on the outer target.
                if (detail.target.innerHTML === refreshed.innerHTML) {
                    detail.shouldSwap = false;
                    return;
                }
                detail.serverResponse = refreshed.outerHTML;
            }
        }
        rememberScroll(detail.target);
    });

    document.body.addEventListener("htmx:oobBeforeSwap", (event) => {
        rememberScroll(event.detail.target);
    });
    document.body.addEventListener("htmx:afterSwap", restoreScroll);
    document.body.addEventListener("htmx:oobAfterSwap", restoreScroll);

    document.addEventListener("visibilitychange", () => {
        if (document.hidden || !window.htmx) {
            return;
        }
        refreshIds.forEach((identifier) => {
            const refresh = document.getElementById(identifier);
            if (refresh) {
                window.htmx.trigger(refresh, "computer-refresh");
            }
        });
    });
})();
