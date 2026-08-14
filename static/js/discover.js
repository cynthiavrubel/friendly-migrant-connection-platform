document.querySelectorAll("[data-filter-search]").forEach((search) => {
    const options = document.querySelector(`#${CSS.escape(search.dataset.filterSearch)}`);
    const empty = document.querySelector(`[data-filter-empty="${search.dataset.filterSearch}"]`);
    if (!options) return;

    search.addEventListener("input", () => {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        options.querySelectorAll("[data-filter-option]").forEach((option) => {
            const matches = option.dataset.filterName.includes(query);
            option.hidden = !matches;
            visible += Number(matches);
        });
        if (empty) empty.hidden = visible !== 0;
    });
});

const discoveryFilters = document.querySelector("[data-discovery-filters]");
const mobileFilters = window.matchMedia("(max-width: 767px)");

function syncFilterDisclosure(event) {
    if (!discoveryFilters) return;
    if (!event.matches) {
        discoveryFilters.open = true;
    } else if (discoveryFilters.dataset.active !== "true") {
        discoveryFilters.open = false;
    }
}

function updateFilterSummary() {
    const state = discoveryFilters?.querySelector(".filter-summary-state");
    if (state) state.textContent = discoveryFilters.open ? "Hide filters" : "Show filters";
}

discoveryFilters?.addEventListener("toggle", updateFilterSummary);
mobileFilters.addEventListener("change", syncFilterDisclosure);
syncFilterDisclosure(mobileFilters);
updateFilterSummary();
