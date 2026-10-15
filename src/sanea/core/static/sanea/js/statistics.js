"use strict";

(() => {
    document.body.addEventListener("shown.bs.tab", (event) => {
        const kind = event.target.dataset?.activityKind;
        const field = document.getElementById("recent-activity-kind");
        if (field && (kind === "application" || kind === "session")) {
            field.value = kind;
        }
    });
})();
