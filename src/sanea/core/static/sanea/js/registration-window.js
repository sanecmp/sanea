(() => {
    "use strict";

    const initializeCountdowns = (root) => {
        root.querySelectorAll("[data-registration-countdown]").forEach((timer) => {
            if (timer.dataset.countdownInitialized === "true") {
                return;
            }
            timer.dataset.countdownInitialized = "true";

            const initial = Number(timer.dataset.registrationCountdown);
            const duration = Number(timer.dataset.registrationDuration);
            const started = performance.now();
            const progress = timer.parentElement.querySelector(".progress-bar");
            const progressContainer = progress.parentElement;

            const update = () => {
                if (!timer.isConnected) {
                    return;
                }
                const remaining = Math.max(0, initial - (performance.now() - started));
                const totalSeconds = Math.ceil(remaining / 1000);
                const minutes = Math.floor(totalSeconds / 60);
                const seconds = totalSeconds % 60;
                const percentage = Math.ceil((remaining / duration) * 100);

                timer.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
                progress.style.width = `${percentage}%`;
                progressContainer.setAttribute("aria-valuenow", `${percentage}`);

                if (remaining > 0) {
                    window.setTimeout(update, 100);
                    return;
                }
                document.getElementById("registration-refresh")?.click();
            };

            update();
        });
    };

    document.addEventListener("DOMContentLoaded", () => initializeCountdowns(document));
    document.body.addEventListener("htmx:afterSwap", (event) => {
        initializeCountdowns(event.target);
    });
})();
