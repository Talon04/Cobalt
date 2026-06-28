async function loadSettings() {
    const status = document.getElementById("settings-status");
    const keepAliveInput = document.getElementById("keep-alive-input");
    try {
        const resp = await fetch("/chat/settings");
        if (!resp.ok) {
            throw new Error("Failed to load settings");
        }
        const data = await resp.json();
        keepAliveInput.value = data.keep_alive || "";
        status.textContent = "Loaded.";
    } catch (error) {
        status.textContent = `Error: ${error}`;
    }
}

async function saveSettings() {
    const status = document.getElementById("settings-status");
    const keepAliveInput = document.getElementById("keep-alive-input");
    status.textContent = "Saving...";
    try {
        const resp = await fetch("/chat/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keep_alive: keepAliveInput.value }),
        });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(text || "Failed to save settings");
        }
        const data = await resp.json();
        keepAliveInput.value = data.keep_alive || "";
        status.textContent = "Saved.";
    } catch (error) {
        status.textContent = `Error: ${error}`;
    }
}

window.addEventListener("DOMContentLoaded", loadSettings);
