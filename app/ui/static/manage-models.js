function appendMessage(message, isError = false) {
    const messages = document.getElementById("messages");
    if (!messages) return;
    const row = document.createElement("p");
    if (isError) {
        row.style.color = "red";
    }
    row.textContent = message;
    messages.appendChild(row);
}

function setPullStatus(message, visible = true) {
    const status = document.getElementById("pull-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("hidden", !visible);
}

function formatBytes(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "unknown";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = value;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }
    const precision = size >= 100 ? 0 : size >= 10 ? 1 : 2;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
}

function formatPullProgress(status) {
    const model = status?.model || "model";
    const percent = typeof status?.percent === "number"
        ? `${status.percent.toFixed(2)}%`
        : "--%";
    const downloaded = formatBytes(status?.downloaded_bytes);
    const total = formatBytes(status?.total_bytes);
    const speed = typeof status?.speed_bytes_per_sec === "number"
        ? `${formatBytes(status.speed_bytes_per_sec)}/s`
        : "unknown";
    return `Pulling ${model}: ${percent} | ${downloaded} / ${total} | ${speed}`;
}

function setButtonsEnabled(enabled) {
    const modelSelect = document.getElementById("model-select");
    const pullSelected = document.getElementById("pull-selected-model-button");
    const pullCustom = document.getElementById("pull-custom-model-button");
    const customInput = document.getElementById("custom-model-input");
    if (modelSelect) modelSelect.disabled = !enabled;
    if (pullSelected) pullSelected.disabled = !enabled;
    if (pullCustom) pullCustom.disabled = !enabled;
    if (customInput) customInput.disabled = !enabled;
}

async function readErrorMessage(resp, fallbackMessage) {
    try {
        const data = await resp.json();
        if (typeof data?.detail === "string" && data.detail.trim()) {
            return data.detail;
        }
    } catch {
        // ignore invalid error payload
    }
    return fallbackMessage;
}

function setAppModel(model) {
    const title = document.getElementById("app-title");
    if (title && model) {
        title.textContent = `Manage models - ${model}`;
    }
}

async function loadModelOptions() {
    const select = document.getElementById("model-select");
    if (!select) return;
    const resp = await fetch("/chat/models");
    if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, "Unable to load models"));
    }
    const data = await resp.json();
    const currentModel = data.current_model;
    const installed = new Set(data.installed_models || []);
    const standard = new Set(data.standard_models || []);
    select.innerHTML = "";
    (data.models || []).forEach((model) => {
        const option = document.createElement("option");
        option.value = model;
        if (installed.has(model)) {
            option.textContent = model;
        } else if (standard.has(model)) {
            option.textContent = `${model} (download)`;
        } else {
            option.textContent = `${model} (custom)`;
        }
        if (model === currentModel) {
            option.selected = true;
        }
        select.appendChild(option);
    });
    setAppModel(currentModel);
}

async function selectModel(model) {
    if (!model) return;
    const resp = await fetch("/chat/models/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
    });
    if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, "Unable to select model"));
    }
    setAppModel(model);
}

async function startModelPull(modelName) {
    if (!modelName) return;
    setButtonsEnabled(false);
    setPullStatus(`Pulling ${modelName}... please wait.`);
    appendMessage(`Starting model pull for ${modelName}...`);
    try {
        const resp = await fetch("/chat/pull-model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: modelName }),
        });
        const data = await resp.json();
        if (data.ok && data.started) {
            appendMessage(`Pull started for ${data.model}. Waiting for completion...`);
            await waitForPullToFinish();
            return;
        }
        if (data.ok) {
            appendMessage(`Pull already running for ${data.model}. Waiting for completion...`);
            await waitForPullToFinish();
            return;
        }
        appendMessage(`Pull failed: ${data.error || data.status || "unknown error"}`, true);
    } catch (e) {
        appendMessage(`Error pulling model: ${e}`, true);
    } finally {
        setButtonsEnabled(true);
    }
}

async function pullSelectedModel() {
    const select = document.getElementById("model-select");
    if (!select || !select.value) return;
    await startModelPull(select.value);
}

async function pullCustomModel() {
    const input = document.getElementById("custom-model-input");
    if (!input) return;
    const model = input.value.trim();
    if (!model) return;
    await startModelPull(model);
}

async function waitForPullToFinish() {
    while (true) {
        const resp = await fetch("/chat/pull-model/status");
        const data = await resp.json();
        if (!data.running) {
            if (data.done) {
                appendMessage(`Model ${data.model} is ready.`);
                setPullStatus(`Model ${data.model} is ready.`);
                await loadModelOptions();
                await selectModel(data.model);
            } else if (data.error) {
                appendMessage(`Pull failed: ${data.error}`, true);
                setPullStatus(`Pull failed: ${data.error}`);
            } else {
                setPullStatus("", false);
            }
            return;
        }
        setPullStatus(formatPullProgress(data));
        await new Promise((resolve) => setTimeout(resolve, 3000));
    }
}

window.addEventListener("DOMContentLoaded", async () => {
    try {
        await loadModelOptions();
    } catch (e) {
        appendMessage(`Failed to load models: ${e}`, true);
    }
});
