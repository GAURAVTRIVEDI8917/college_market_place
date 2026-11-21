document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("websiteShareDynamicStyles")) {
        const styles = document.createElement("style");
        styles.id = "websiteShareDynamicStyles";
        styles.textContent = `
            .global-website-share-button {
                position: fixed; right: 20px; bottom: 20px; z-index: 1000;
                padding: 12px 16px; border: 0; border-radius: 999px;
                background: #174ea6; color: white; cursor: pointer;
                box-shadow: 0 4px 14px rgba(23,78,166,.3);
                font: inherit; font-weight: bold;
            }
            .global-share-status {
                position: fixed; right: 20px; bottom: 68px; z-index: 1000;
                max-width: 260px; padding: 6px 10px; border-radius: 6px;
                background: white; color: #174ea6;
                box-shadow: 0 2px 10px rgba(0,0,0,.12); font-size: 12px;
            }
        `;
        document.head.appendChild(styles);
    }

    let shareButton = document.getElementById("shareWebsite");
    let shareStatus = document.getElementById("websiteShareStatus");

    if (!shareButton) {
        shareButton = document.createElement("button");
        shareButton.id = "shareWebsite";
        shareButton.type = "button";
        shareButton.className = "global-website-share-button";
        shareButton.textContent = "Share Website";
        shareButton.dataset.shareTitle = "CampusMart";
        shareButton.dataset.shareUrl = window.location.origin + "/";

        shareStatus = document.createElement("span");
        shareStatus.id = "websiteShareStatus";
        shareStatus.className = "global-share-status";
        shareStatus.setAttribute("role", "status");
        shareStatus.setAttribute("aria-live", "polite");

        document.body.appendChild(shareButton);
        document.body.appendChild(shareStatus);
    }

    async function copyWebsiteLink(url) {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(url);
            return;
        }

        const temporaryInput = document.createElement("textarea");
        temporaryInput.value = url;
        temporaryInput.setAttribute("readonly", "");
        temporaryInput.style.position = "fixed";
        temporaryInput.style.opacity = "0";
        document.body.appendChild(temporaryInput);
        temporaryInput.select();
        const copied = document.execCommand("copy");
        temporaryInput.remove();

        if (!copied) {
            throw new Error("Copy command was not available.");
        }
    }

    shareButton.addEventListener("click", async function () {
        const url = shareButton.dataset.shareUrl;
        const title = shareButton.dataset.shareTitle;

        try {
            if (navigator.share) {
                await navigator.share({
                    title: title,
                    text: "Buy and sell second-hand items with CampusMart.",
                    url: url
                });
                shareStatus.textContent = "Share options opened.";
                return;
            }

            await copyWebsiteLink(url);
            shareStatus.textContent = "Website link copied.";
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            shareStatus.textContent = "Could not copy the link. Copy it from the address bar.";
        }
    });
});
