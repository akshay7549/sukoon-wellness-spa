document.addEventListener("DOMContentLoaded", () => {
    const service = document.getElementById("id_service");
    const duration = document.getElementById("id_duration");
    if (!service || !duration) return;
    let requestNumber = 0;
    const hint = document.createElement("p");
    hint.className = "help";
    duration.insertAdjacentElement("afterend", hint);
    async function loadOptions() {
        const sequence = ++requestNumber;
        duration.disabled = true;
        hint.textContent = "Loading available sessions…";
        try {
            const response = await fetch("/api/service-options/?service=" + encodeURIComponent(service.value), {credentials: "same-origin"});
            if (!response.ok) throw new Error("Sessions could not be loaded.");
            const data = await response.json();
            if (sequence !== requestNumber) return;
            duration.replaceChildren(new Option("Select duration", ""));
            for (const item of data.options) {
                const label = item.duration + " minutes — ₹" + Number(item.price).toLocaleString("en-IN", {minimumFractionDigits: 2});
                const option = new Option(label, item.duration);
                option.dataset.price = item.price;
                duration.appendChild(option);
            }
            hint.textContent = data.options.length ? "Choose a session." : "This treatment has no active sessions.";
        } catch (error) {
            if (sequence === requestNumber) {
                duration.replaceChildren(new Option("Select treatment first", ""));
                hint.textContent = "Select a treatment, or check its active duration and price options.";
            }
        } finally {
            if (sequence === requestNumber) duration.disabled = false;
        }
    }
    if (window.django && django.jQuery) django.jQuery(service).on("change", loadOptions);
    else service.addEventListener("change", loadOptions);
    duration.addEventListener("change", () => {
        const price = duration.selectedOptions[0]?.dataset.price;
        hint.textContent = price ? "Session price: ₹" + Number(price).toLocaleString("en-IN", {minimumFractionDigits: 2}) : "";
    });
});
