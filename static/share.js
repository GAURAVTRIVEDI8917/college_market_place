document.addEventListener("DOMContentLoaded", function () {
    async function copyProductLink(url) {
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

    const shareButtons = document.querySelectorAll(
        "#shareProduct, .product-card-share"
    );

    shareButtons.forEach(function (shareButton) {
        let shareStatus = shareButton.nextElementSibling;
        if (shareButton.id === "shareProduct") {
            shareStatus = document.getElementById("shareStatus");
        }

        shareButton.addEventListener("click", async function () {
            const url = shareButton.dataset.shareUrl;
            const title = shareButton.dataset.shareTitle;

            try {
                if (navigator.share) {
                    await navigator.share({
                        title: title + " | CampusMart",
                        text: "Check out this CampusMart listing.",
                        url: url
                    });
                    if (shareStatus) {
                        shareStatus.textContent = "Share options opened.";
                    }
                    return;
                }

                await copyProductLink(url);
                if (shareStatus) {
                    shareStatus.textContent = "Product link copied. You can now share it.";
                }
            } catch (error) {
                if (error.name === "AbortError") {
                    return;
                }
                if (shareStatus) {
                    shareStatus.textContent = "Could not share automatically. Copy this page's link from the address bar.";
                }
            }
        });
    });
});
