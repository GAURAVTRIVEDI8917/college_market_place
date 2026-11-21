document.addEventListener("DOMContentLoaded", function () {
    const searchInput = document.getElementById("searchInput");
    const searchForm = document.getElementById("searchForm");
    const categoryFilter = document.getElementById("categoryFilter");
    const clearSearch = document.getElementById("clearSearch");
    const sortProducts = document.getElementById("sortProducts");
    const productsGrid = document.querySelector(".product-grid");
    const products = Array.from(document.querySelectorAll(".product-card"));
    const noResults = document.getElementById("noResults");
    const resultsCount = document.getElementById("resultsCount");
    const filterChips = document.querySelectorAll("[data-category-filter]");

    if (
        !searchInput || !searchForm || !categoryFilter || !productsGrid ||
        !noResults || !resultsCount
    ) {
        return;
    }

    const serverFilters = new URLSearchParams(window.location.search);
    const hasServerFilters = Boolean(
        serverFilters.get("q") || serverFilters.get("category")
    );

    function sortVisibleProducts() {
        const sortBy = sortProducts ? sortProducts.value : "newest";
        const sortedProducts = products.slice().sort(function (first, second) {
            if (sortBy === "price-low") {
                return Number(first.dataset.price) - Number(second.dataset.price);
            }
            if (sortBy === "price-high") {
                return Number(second.dataset.price) - Number(first.dataset.price);
            }
            if (sortBy === "name") {
                return first.querySelector("h3").textContent.localeCompare(
                    second.querySelector("h3").textContent
                );
            }
            return Number(second.dataset.listingId) - Number(first.dataset.listingId);
        });

        sortedProducts.forEach(function (product) {
            productsGrid.appendChild(product);
        });
    }

    function updateProducts() {
        const searchText = searchInput.value.toLowerCase().trim();
        const selectedCategory = categoryFilter.value.toLowerCase();
        let visibleCount = 0;

        products.forEach(function (product) {
            const productText = product.dataset.search || product.innerText.toLowerCase();
            const productCategory = product.dataset.category || "";
            const matchesSearch = productText.includes(searchText);
            const matchesCategory = !selectedCategory || productCategory === selectedCategory;
            const isVisible = matchesSearch && matchesCategory;

            product.hidden = !isVisible;
            if (isVisible) {
                visibleCount++;
            }
        });

        noResults.hidden = visibleCount > 0;
        resultsCount.textContent = visibleCount === 1
            ? "Showing 1 item"
            : "Showing " + visibleCount + " items";

        filterChips.forEach(function (chip) {
            const isActive = chip.dataset.categoryFilter === selectedCategory;
            chip.classList.toggle("is-active", isActive);
            chip.setAttribute("aria-pressed", String(isActive));
        });

        sortVisibleProducts();
    }

    searchInput.addEventListener("input", updateProducts);
    categoryFilter.addEventListener("change", function () {
        if (hasServerFilters) {
            searchForm.submit();
            return;
        }
        updateProducts();
    });

    if (sortProducts) {
        sortProducts.addEventListener("change", updateProducts);
    }

    filterChips.forEach(function (chip) {
        chip.addEventListener("click", function () {
            const nextCategory = chip.dataset.categoryFilter || "";
            if (hasServerFilters && nextCategory !== categoryFilter.value.toLowerCase()) {
                const params = new URLSearchParams();
                if (searchInput.value.trim()) {
                    params.set("q", searchInput.value.trim());
                }
                if (nextCategory) {
                    const selectedOption = Array.from(categoryFilter.options).find(
                        function (option) {
                            return option.value.toLowerCase() === nextCategory;
                        }
                    );
                    params.set("category", selectedOption ? selectedOption.value : nextCategory);
                }
                window.location.assign("/?" + params.toString());
                return;
            }
            categoryFilter.value = nextCategory;
            updateProducts();
            document.getElementById("products").scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        });
    });

    if (clearSearch) {
        clearSearch.addEventListener("click", function () {
            if (hasServerFilters) {
                window.location.assign("/");
                return;
            }
            searchInput.value = "";
            categoryFilter.value = "";
            if (sortProducts) {
                sortProducts.value = "newest";
            }
            updateProducts();
            searchInput.focus();
        });
    }

    updateProducts();
});
