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

const languageSelector = document.querySelector("[data-language-selector]");
const languageSearch = languageSelector?.querySelector("#language-search");
const languageOptions = [...(languageSelector?.querySelectorAll("[data-language-option]") || [])];
const languageStatus = languageSelector?.querySelector("[data-language-status]");
const languageEmpty = languageSelector?.querySelector("[data-language-empty]");

function updateLanguageSelector() {
    if (!languageSelector) return;
    const query = languageSearch.value.trim().toLocaleLowerCase();
    let visibleCount = 0;
    let selectedCount = 0;

    languageOptions.forEach((option) => {
        const matches = option.dataset.languageName.includes(query);
        option.hidden = !matches;
        visibleCount += Number(matches);
        selectedCount += Number(option.querySelector("input").checked);
    });

    languageEmpty.hidden = visibleCount !== 0;
    const resultLabel = query ? `${visibleCount} result${visibleCount === 1 ? "" : "s"}` : `${visibleCount} languages`;
    languageStatus.textContent = `${selectedCount} selected · ${resultLabel}`;
}

languageSearch?.addEventListener("input", updateLanguageSelector);
languageSelector?.addEventListener("change", updateLanguageSelector);
updateLanguageSelector();

const photoInput = document.querySelector("#profile_photo");
const photoPreview = document.querySelector("[data-photo-preview]");
const cropEditor = document.querySelector("[data-crop-editor]");
const cropViewport = document.querySelector("[data-crop-viewport]");
const cropImage = document.querySelector("[data-crop-image]");
const zoomInput = document.querySelector("[data-crop-zoom]");
const resetCropButton = document.querySelector("[data-crop-reset]");
const cropXInput = document.querySelector("#photo_crop_x");
const cropYInput = document.querySelector("#photo_crop_y");
const cropZoomInput = document.querySelector("#photo_crop_zoom");
let previewObjectUrl;
let naturalWidth = 0;
let naturalHeight = 0;
let baseScale = 1;
let panX = 0;
let panY = 0;
let dragStart;

function restorePersistedPreview() {
    if (!photoPreview) return;
    const persistedSource = photoPreview.dataset.persistedSrc;
    photoPreview.replaceChildren();
    if (persistedSource) {
        const image = document.createElement("img");
        image.className = "profile-photo-preview";
        image.src = persistedSource;
        image.alt = "Current profile photo preview";
        photoPreview.append(image);
    } else {
        const initials = document.createElement("span");
        initials.className = "profile-photo-preview profile-photo-initials";
        initials.setAttribute("aria-hidden", "true");
        initials.textContent = photoPreview.dataset.initial;
        photoPreview.append(initials);
    }
}

function cropMetrics() {
    const viewportWidth = cropViewport.clientWidth;
    const viewportHeight = cropViewport.clientHeight;
    const zoom = Number(zoomInput.value);
    const scale = baseScale * zoom;
    const renderedWidth = naturalWidth * scale;
    const renderedHeight = naturalHeight * scale;
    const maxOffsetX = Math.max(0, (renderedWidth - viewportWidth) / 2);
    const maxOffsetY = Math.max(0, (renderedHeight - viewportHeight) / 2);
    panX = Math.min(maxOffsetX, Math.max(-maxOffsetX, panX));
    panY = Math.min(maxOffsetY, Math.max(-maxOffsetY, panY));
    return { viewportWidth, viewportHeight, zoom, scale, renderedWidth, renderedHeight };
}

function renderCrop() {
    if (!naturalWidth || !cropViewport) return;
    const { viewportWidth, viewportHeight, zoom, scale, renderedWidth, renderedHeight } = cropMetrics();
    cropImage.style.width = `${renderedWidth}px`;
    cropImage.style.height = `${renderedHeight}px`;
    cropImage.style.transform = `translate3d(calc(-50% + ${panX}px), calc(-50% + ${panY}px), 0)`;

    const imageLeft = (viewportWidth - renderedWidth) / 2 + panX;
    const imageTop = (viewportHeight - renderedHeight) / 2 + panY;
    const cropWidth = viewportWidth / scale;
    const cropHeight = viewportHeight / scale;
    cropXInput.value = String(Math.min(1, Math.max(0, (-imageLeft / scale + cropWidth / 2) / naturalWidth)));
    cropYInput.value = String(Math.min(1, Math.max(0, (-imageTop / scale + cropHeight / 2) / naturalHeight)));
    cropZoomInput.value = String(zoom);
}

function resetCrop() {
    if (!naturalWidth || !cropViewport) return;
    zoomInput.value = "1";
    panX = 0;
    panY = 0;
    baseScale = Math.max(cropViewport.clientWidth / naturalWidth, cropViewport.clientHeight / naturalHeight);
    renderCrop();
}

function deactivateCropEditor() {
    if (cropEditor) cropEditor.hidden = true;
    naturalWidth = 0;
    naturalHeight = 0;
    cropXInput.value = "0.5";
    cropYInput.value = "0.5";
    cropZoomInput.value = "1";
}

function updatePhotoPreview() {
    if (!photoInput || !photoPreview) return;
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = undefined;
    const [file] = photoInput.files;
    if (!file) {
        deactivateCropEditor();
        restorePersistedPreview();
        return;
    }
    previewObjectUrl = URL.createObjectURL(file);
    const image = document.createElement("img");
    image.className = "profile-photo-preview";
    image.src = previewObjectUrl;
    image.alt = "Selected profile photo preview";
    photoPreview.replaceChildren(image);
    cropImage.src = previewObjectUrl;
    cropImage.onload = () => {
        naturalWidth = cropImage.naturalWidth;
        naturalHeight = cropImage.naturalHeight;
        cropEditor.hidden = false;
        resetCrop();
    };
}

photoInput?.addEventListener("change", updatePhotoPreview);
zoomInput?.addEventListener("input", renderCrop);
resetCropButton?.addEventListener("click", resetCrop);

cropViewport?.addEventListener("pointerdown", (event) => {
    if (!naturalWidth) return;
    cropViewport.setPointerCapture(event.pointerId);
    dragStart = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX, panY };
});
cropViewport?.addEventListener("pointermove", (event) => {
    if (!dragStart || event.pointerId !== dragStart.pointerId) return;
    panX = dragStart.panX + event.clientX - dragStart.x;
    panY = dragStart.panY + event.clientY - dragStart.y;
    renderCrop();
});
cropViewport?.addEventListener("pointerup", (event) => {
    if (!dragStart || event.pointerId !== dragStart.pointerId) return;
    if (cropViewport.hasPointerCapture(event.pointerId)) cropViewport.releasePointerCapture(event.pointerId);
    dragStart = undefined;
});
cropViewport?.addEventListener("pointercancel", () => { dragStart = undefined; });
cropViewport?.addEventListener("keydown", (event) => {
    const movement = event.shiftKey ? 24 : 8;
    const directions = {
        ArrowLeft: [movement, 0], ArrowRight: [-movement, 0],
        ArrowUp: [0, movement], ArrowDown: [0, -movement],
    };
    if (!directions[event.key] || !naturalWidth) return;
    event.preventDefault();
    panX += directions[event.key][0];
    panY += directions[event.key][1];
    renderCrop();
});
window.addEventListener("resize", () => {
    if (naturalWidth) {
        baseScale = Math.max(cropViewport.clientWidth / naturalWidth, cropViewport.clientHeight / naturalHeight);
        renderCrop();
    }
});
window.addEventListener("pagehide", () => {
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
});
