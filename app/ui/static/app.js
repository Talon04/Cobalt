let currentChatId = null;
let isPullRunning = false;

function appendSystemMessage(message, isError = false) {
    const chat = document.getElementById("chat");
    if (!chat) return;
    const row = document.createElement("p");
    if (isError) {
        row.style.color = "red";
    }
    const strong = document.createElement("strong");
    strong.textContent = "Cobalt:";
    row.appendChild(strong);
    row.appendChild(document.createTextNode(` ${message}`));
    chat.appendChild(row);
}

function setAppModel(model) {
    const title = document.getElementById("app-title");
    if (title && model) {
        title.textContent = `Cobalt - ${model}`;
    }
}

async function loadModelOptions() {
    const select = document.getElementById("model-select");
    if (!select) return;

    const resp = await fetch("/chat/models");
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

async function selectModel(model, updateTitle = true) {
    if (!model) return;
    await fetch("/chat/models/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
    });
    if (updateTitle) {
        setAppModel(model);
    }
}

async function loadChats(selectChatId = null) {
    const resp = await fetch("/chat/chats");
    const chats = await resp.json();
    const select = document.getElementById("chat-select");
    if (!select) return;

    select.innerHTML = "";

    if (chats.length === 0) {
        const created = await createNewChat(false);
        if (created) {
            await loadChats(created.id);
        }
        return;
    }

    chats.forEach((chat) => {
        const option = document.createElement("option");
        option.value = chat.id;
        option.textContent = chat.title;
        if (selectChatId && chat.id === selectChatId) {
            option.selected = true;
        }
        select.appendChild(option);
    });

    const selectedId = selectChatId || chats[0].id;
    currentChatId = selectedId;
    select.value = String(selectedId);
    await loadChatMessages(selectedId);
}

async function loadChatMessages(chatId) {
    const chat = document.getElementById("chat");
    chat.innerHTML = "";
    setPullStatus("", false);
    setSendingEnabled(true);

    const resp = await fetch(`/chat/chats/${chatId}/messages`);
    const messages = await resp.json();

    messages.forEach((message) => {
        if (message.role === "user") {
            chat.innerHTML += `<p><strong>You:</strong> ${message.content}</p>`;
        } else {
            chat.innerHTML += `<p><strong>Cobalt - ${message.model || "Unknown Model"}: </strong> ${message.content}</p>`;
        }
    });
}

async function switchChat(chatId) {
    if (!chatId) return;
    currentChatId = Number(chatId);
    isPullRunning = false;
    setPullStatus("", false);
    await loadChatMessages(currentChatId);
}

async function createNewChat(selectAfterCreate = true) {
    const resp = await fetch("/chat/chats", { method: "POST" });
    const chat = await resp.json();
    if (selectAfterCreate) {
        await loadChats(chat.id);
    }
    return chat;
}

function setSendingEnabled(enabled) {
    const sendButton = document.getElementById("send-button");
    const input = document.getElementById("input");
    const newChatButton = document.getElementById("new-chat-button");
    const modelSelect = document.getElementById("model-select");
    const pullSelected = document.getElementById("pull-selected-model-button");
    const pullCustom = document.getElementById("pull-custom-model-button");
    const customInput = document.getElementById("custom-model-input");

    if (sendButton) {
        sendButton.disabled = !enabled;
    }
    if (input) {
        input.disabled = !enabled;
    }
    if (newChatButton) {
        newChatButton.disabled = !enabled;
    }
    if (modelSelect) {
        modelSelect.disabled = !enabled;
    }
    if (pullSelected) {
        pullSelected.disabled = !enabled;
    }
    if (pullCustom) {
        pullCustom.disabled = !enabled;
    }
    if (customInput) {
        customInput.disabled = !enabled;
    }
}

function setPullStatus(message, visible = true) {
    const status = document.getElementById("pull-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("hidden", !visible);
}

async function sendMessage() {
    const input = document.getElementById("input");
    const chat = document.getElementById("chat");

    const msg = input.value;
    if (!msg) return;
    if (!currentChatId) {
        await loadChats();
        return;
    }

    chat.innerHTML += `<p><strong>You:</strong> ${msg}</p>`;
    input.value = "";
    setSendingEnabled(false);

    try {
        const resp = await fetch("/chat/send-stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_id: currentChatId, role: "user", content: msg, model: null }),
        });

        if (!resp.ok) {
            const err = await resp.text();

            chat.innerHTML += `<p style="color:red">Network error: ${err}</p>`;
            console.error("Send message failed:", err);
            setSendingEnabled(true);

            return;
        }

        const assistantElem = document.createElement("p");
        assistantElem.innerHTML = `<strong>Cobalt: </strong> <span class="streaming"></span>`;
        chat.appendChild(assistantElem);
        const streamSpan = assistantElem.querySelector(".streaming");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        let streamEnded = false;
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const parts = buffer.split("\n\n");
            buffer = parts.pop();
            for (const part of parts) {
                const lines = part.split("\n");
                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const payload = JSON.parse(line.replace(/^data: /, ""));

                            if (payload.type === "connected") {
                                console.log("Stream connected, job_id:", payload.job_id);
                                continue;
                            }

                            if (payload.type === "meta" && payload.model) {
                                setAppModel(payload.model);
                                continue;
                            }

                            if (payload.type === "keepalive") {
                                continue;
                            }

                            if (payload.type === "stream_done" || payload.type === "done") {
                                streamEnded = true;
                                break;
                            }

                            if (payload.error) {
                                const err = payload.error;
                                chat.innerHTML += `<p style="color:red"><strong>Error:</strong> ${err}</p>`;
                                setSendingEnabled(true);
                                streamEnded = true;
                                break;
                            }

                            if (payload.content) {
                                streamSpan.textContent += payload.content;
                            }
                        } catch {
                            // ignore malformed chunks
                        }
                    }
                }
                if (streamEnded) break;
            }
            if (streamEnded) break;
        }

        await loadChats(currentChatId);
        setSendingEnabled(true);
    } catch (e) {
        chat.innerHTML += `<p style="color:red">Error: ${e}</p>`;
        setSendingEnabled(true);
    }
}

async function startModelPull(modelName) {
    if (!modelName) return;

    isPullRunning = true;
    setSendingEnabled(false);
    setPullStatus(`Pulling ${modelName}... please wait.`);
    appendSystemMessage(`Starting model pull for ${modelName}...`);

    try {
        const resp = await fetch("/chat/pull-model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: modelName }),
        });
        const data = await resp.json();

        if (data.ok && data.started) {
            appendSystemMessage(`Pull started for ${data.model}. Waiting for completion...`);
            await waitForPullToFinish();
        } else if (data.ok) {
            appendSystemMessage(`Pull already running for ${data.model}.`);
            await waitForPullToFinish();
        } else {
            appendSystemMessage(`Pull failed: ${data.error || data.status || "unknown error"}`, true);
            setSendingEnabled(true);
            setPullStatus("", false);
        }
    } catch (e) {
        appendSystemMessage(`Error pulling model: ${e}`, true);
        setSendingEnabled(true);
        setPullStatus("", false);
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
        try {
            const resp = await fetch("/chat/pull-model/status");
            const data = await resp.json();

            if (!data.running) {
                if (data.done) {
                    appendSystemMessage(`Model ${data.model} is ready.`);
                    setPullStatus(`Model ${data.model} is ready.`);
                    await selectModel(data.model, false);
                    await loadModelOptions();
                } else if (data.error) {
                    appendSystemMessage(`Pull failed: ${data.error}`, true);
                    setPullStatus(`Pull failed: ${data.error}`);
                }
                setSendingEnabled(true);
                isPullRunning = false;
                return;
            }

            setPullStatus(`Pulling ${data.model}... still working.`);
            await new Promise((resolve) => setTimeout(resolve, 3000));
        } catch (e) {
            appendSystemMessage(`Error checking pull status: ${e}`, true);
            setSendingEnabled(true);
            setPullStatus("", false);
            isPullRunning = false;
            return;
        }
    }
}

window.addEventListener("DOMContentLoaded", async () => {
    await loadModelOptions();
    await loadChats();
});
