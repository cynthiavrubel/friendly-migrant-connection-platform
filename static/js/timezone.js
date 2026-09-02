(() => {
    "use strict";
    const field = document.querySelector("[data-browser-timezone='true']");
    if (!field || !window.Intl) return;
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!browserTimezone) return;
    const supported = [...document.querySelectorAll("#timezone-options option")]
        .some((option) => option.value === browserTimezone);
    if (supported) field.value = browserTimezone;
})();
