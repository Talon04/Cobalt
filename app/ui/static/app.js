let currentChatId = null;
const pendingMathRender = new WeakMap();

const SIMPLE_MATH_SYMBOLS = new Map([
    ["\\rightarrow", "→"],
    ["\\leftarrow", "←"],
    ["\\leftrightarrow", "↔"],
    ["\\uparrow", "↑"],
    ["\\downarrow", "↓"],
    ["\\pm", "±"],
    ["\\times", "×"],
    ["\\div", "÷"],
    ["\\leq", "≤"],
    ["\\geq", "≥"],
]);

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function getMarkdownRenderer() {
    const markedLib = window.marked;
    const purifier = window.DOMPurify;
    if (!markedLib || !purifier) {
        return null;
    }

    if (!getMarkdownRenderer.initialized) {
        markedLib.setOptions({
            gfm: true,
            breaks: true,
        });
        getMarkdownRenderer.initialized = true;
    }

    return (content) =>
        purifier.sanitize(markedLib.parse(content), {
            USE_PROFILES: { html: true },
        });
}

function formatMessageContent(content) {
    const normalized = String(content || "").replace(/\r\n/g, "\n").trim();
    if (!normalized) return "";

    const expanded = normalized.replace(/\$([^$\n]+)\$/g, (match, mathContent) => {
        const symbol = SIMPLE_MATH_SYMBOLS.get(mathContent.trim());
        return symbol || match;
    });

    const renderMarkdown = getMarkdownRenderer();
    if (!renderMarkdown) {
        return `<p>${escapeHtml(expanded).replace(/\n/g, "<br>")}</p>`;
    }

    return renderMarkdown(expanded);
}

function renderMathInElement(element) {
    if (!element || typeof window.renderMathInElement !== "function") return;
    try {
        window.renderMathInElement(element, {
            delimiters: [
                { left: "$$", right: "$$", display: true },
                { left: "$", right: "$", display: false },
                { left: "\\(", right: "\\)", display: false },
                { left: "\\[", right: "\\]", display: true },
            ],
            throwOnError: false,
            strict: "warn",
            trust: false,
        });
    } catch (error) {
        console.error("Math render failed:", error);
    }
}

function scheduleMathRender(element) {
    if (!element || typeof window.renderMathInElement !== "function") return;
    const existingTimer = pendingMathRender.get(element);
    if (existingTimer) {
        clearTimeout(existingTimer);
    }
    const timer = setTimeout(() => {
        pendingMathRender.delete(element);
        renderMathInElement(element);
    }, 80);
    pendingMathRender.set(element, timer);
}

function appendChatMessage(senderLabel, content, model = null, isError = false) {
    const chat = document.getElementById("chat");
    if (!chat) return null;
    const row = document.createElement("div");
    row.className = "chat-message";
    if (isError) {
        row.classList.add("error");
    }
    const strong = document.createElement("strong");
    strong.textContent = model ? `${senderLabel} - ${model}:` : `${senderLabel}:`;
    row.appendChild(strong);
    const messageSpan = document.createElement("span");
    messageSpan.className = "chat-message-content";
    messageSpan.innerHTML = formatMessageContent(content);
    scheduleMathRender(messageSpan);
    row.appendChild(messageSpan);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return messageSpan;
}

function appendSystemMessage(message, isError = false) {
    appendChatMessage("Cobalt", message, null, isError);
}

function ensureModelOption(model) {
    const select = document.getElementById("model-select");
    if (!select || !model) return;
    const exists = Array.from(select.options).some((option) => option.value === model);
    if (!exists) {
        const option = document.createElement("option");
        option.value = model;
        option.textContent = model;
        select.appendChild(option);
    }
    select.value = model;
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
        title.textContent = `Cobalt - ${model}`;
    }
}

async function loadModelOptions() {
    const select = document.getElementById("model-select");
    if (!select) return;

    try {
        const resp = await fetch("/chat/models");
        if (!resp.ok) {
            throw new Error(await readErrorMessage(resp, "Unable to load models"));
        }
        const data = await resp.json();
        const currentModel = data.current_model;
        const installed = new Set(data.installed_models || []);

        // Chat selector should only show ready-to-use models.
        const chatModels = [];
        (data.installed_models || []).forEach((model) => {
            if (model && !chatModels.includes(model)) {
                chatModels.push(model);
            }
        });
        if (currentModel && !chatModels.includes(currentModel)) {
            chatModels.push(currentModel);
        }

        select.innerHTML = "";
        chatModels.forEach((model) => {
            const option = document.createElement("option");
            option.value = model;
            option.textContent = installed.has(model) ? model : `${model} (current)`;

            if (model === currentModel) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        setAppModel(currentModel);
    } catch (e) {
        appendSystemMessage(`Failed to load models: ${e}`, true);
    }
}

async function selectModel(model, updateTitle = true) {
    if (!model) return;
    const select = document.getElementById("model-select");
    if (select) {
        const option = Array.from(select.options).find((item) => item.value === model);
        if (option && option.disabled) {
            appendSystemMessage(
                `Model "${model}" is currently being pulled and cannot be selected yet.`,
                true
            );
            return;
        }
    }
    try {
        const resp = await fetch("/chat/models/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model }),
        });
        if (!resp.ok) {
            throw new Error(await readErrorMessage(resp, "Unable to select model"));
        }
        if (updateTitle) {
            setAppModel(model);
        }
        ensureModelOption(model);
    } catch (e) {
        appendSystemMessage(`Failed to select model: ${e}`, true);
        throw e;
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

    const newChatOption = document.createElement("option");
    newChatOption.value = "__new__";
    newChatOption.textContent = "✨ Start new chat";
    select.appendChild(newChatOption);

    chats.forEach((chat) => {
        const option = document.createElement("option");
        option.value = chat.id;
        option.textContent = `💬 ${chat.title}`;
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
    setSendingEnabled(true);

    const resp = await fetch(`/chat/chats/${chatId}/messages`);
    const messages = await resp.json();

    messages.forEach((message) => {
        if (message.role === "user") {
            appendChatMessage("You", message.content);
        } else {
            appendChatMessage(
                "Cobalt",
                message.content,
                message.model || "Unknown Model"
            );
        }
    });
}

async function switchChat(chatId) {
    if (!chatId) return;
    if (chatId === "__new__") {
        await createNewChat();
        return;
    }
    currentChatId = Number(chatId);
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
    const renameButton = document.getElementById("rename-chat-button");
    const modelSelect = document.getElementById("model-select");
    const chatSelect = document.getElementById("chat-select");

    if (sendButton) {
        sendButton.disabled = !enabled;
    }
    if (input) {
        input.disabled = !enabled;
    }
    if (renameButton) {
        renameButton.disabled = !enabled;
    }
    if (modelSelect) {
        modelSelect.disabled = !enabled;
    }
    if (chatSelect) {
        chatSelect.disabled = !enabled;
    }
}

function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/service-worker.js").catch((error) => {
        console.error("Service worker registration failed:", error);
    });
}

function setupPWAInstallPrompt() {
    let deferredPrompt = null;

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredPrompt = event;
        console.log("PWA install prompt available (Android Chrome/Vivaldi/Edge)");
    });

    window.addEventListener("appinstalled", () => {
        console.log("PWA app installed successfully");
        deferredPrompt = null;
    });

    window.addEventListener("orientationchange", () => {
        // Reset on orientation change
    });

    return deferredPrompt;
}

function setupInputSendShortcut() {
    const input = document.getElementById("input");
    if (!input) return;
    input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" || event.shiftKey) return;
        event.preventDefault();
        sendMessage();
    });
}

async function sendMessage() {
    const input = document.getElementById("input");
    const modelSelect = document.getElementById("model-select");

    if (!input || input.disabled) return;
    const msg = input.value;
    if (!msg.trim()) return;
    if (!currentChatId) {
        await loadChats();
        return;
    }

    appendChatMessage("You", msg);
    input.value = "";
    setSendingEnabled(false);

    try {
        const resp = await fetch("/chat/send-stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                chat_id: currentChatId,
                role: "user",
                content: msg,
                model: modelSelect ? modelSelect.value : null,
            }),
        });

        if (!resp.ok) {
            const err = await resp.text();

            appendSystemMessage(`Network error: ${err}`, true);
            console.error("Send message failed:", err);
            setSendingEnabled(true);

            return;
        }

        const streamSpan = appendChatMessage("Cobalt", "");
        if (!streamSpan) {
            throw new Error("Chat container not found");
        }
        let streamedText = "";

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
                                appendSystemMessage(`Error: ${err}`, true);
                                setSendingEnabled(true);
                                streamEnded = true;
                                break;
                            }

                            if (payload.content) {
                                streamedText += payload.content;
                                streamSpan.innerHTML = formatMessageContent(streamedText);
                                scheduleMathRender(streamSpan);
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
        appendSystemMessage(`Error: ${e}`, true);
        setSendingEnabled(true);
    }
}

async function renameCurrentChat() {
    if (!currentChatId) return;
    const currentOption = document.querySelector(
        `#chat-select option[value="${currentChatId}"]`
    );
    const currentTitle = currentOption
        ? currentOption.textContent.replace(/^💬\s*/, "")
        : "Chat";
    const nextTitle = prompt("Rename chat:", currentTitle);
    if (nextTitle === null) return;
    const trimmed = nextTitle.trim();
    if (!trimmed) {
        appendSystemMessage("Chat title cannot be empty", true);
        return;
    }
    try {
        const resp = await fetch(`/chat/chats/${currentChatId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: trimmed }),
        });
        if (!resp.ok) {
            throw new Error(await readErrorMessage(resp, "Unable to rename chat"));
        }
        await loadChats(currentChatId);
    } catch (error) {
        appendSystemMessage(`Failed to rename chat: ${error}`, true);
    }
}

window.addEventListener("DOMContentLoaded", async () => {
    registerServiceWorker();
    setupPWAInstallPrompt();
    setupInputSendShortcut();
    await loadModelOptions();
    await loadChats();
});
