"use strict";

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.getElementById(button.dataset.passwordToggle);
        if (!input) return;

        const showPassword = input.type === "password";
        input.type = showPassword ? "text" : "password";
        button.setAttribute("aria-pressed", String(showPassword));

        const fieldName = input.id === "confirm_password" ? "confirm password" : "password";
        button.setAttribute("aria-label", `${showPassword ? "Hide" : "Show"} ${fieldName}`);
    });
});
