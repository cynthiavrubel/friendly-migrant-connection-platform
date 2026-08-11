const genderSelect = document.querySelector("#gender");
const descriptionField = document.querySelector("[data-gender-description]");

function updateGenderDescription() {
    if (!genderSelect || !descriptionField) return;
    const visible = genderSelect.value === "self_described";
    descriptionField.hidden = !visible;
    descriptionField.querySelector("input").required = visible;
}

genderSelect?.addEventListener("change", updateGenderDescription);
updateGenderDescription();
