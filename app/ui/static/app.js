let currentChatId = null;
let isPullRunning = false;

function setAppModel(model) {
    const title = document.getElementById("app-title");
    if (title && model) {
        title.textContent = `Cobalt - ${model}`;
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
    if (sendButton) {
        sendButton.disabled = !enabled;
    }
    if (input) {
        input.disabled = !enabled;
    }
    if (newChatButton) {
        newChatButton.disabled = !enabled;
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
    
    try {
        // Use streaming endpoint and render partial assistant content as it arrives
        const resp = await fetch("/chat/send-stream", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({chat_id: currentChatId, role: "user", content: msg})
        });

        if (!resp.ok) {
            const err = await resp.text();
            chat.innerHTML += `<p style="color:red">Error: ${err}</p>`;
            return;
        }

        // Prepare a placeholder for the assistant streaming response
        const assistantElem = document.createElement('p');
        assistantElem.innerHTML = `<strong>Cobalt: </strong> <span class="streaming"></span>`;
        chat.appendChild(assistantElem);
        const streamSpan = assistantElem.querySelector('.streaming');

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // SSE framing: events separated by double newline, lines start with 'data: '
            let parts = buffer.split('\n\n');
            buffer = parts.pop(); // last partial
            for (const part of parts) {
                const lines = part.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const payload = JSON.parse(line.replace(/^data: /, ''));
                            if (payload.type === 'meta' && payload.model) {
                                setAppModel(payload.model);
                                continue;
                            }
                            if (payload.error) {
                                chat.innerHTML += `<p style="color:red"><strong>Cobalt:</strong> ${payload.error}</p>`;
                                setSendingEnabled(true);
                                return;
                            }
                            if (payload.content) {
                                // append partial content
                                streamSpan.textContent += payload.content;
                            }
                        } catch (e) {
                            // ignore malformed chunks
                        }
                    }
                }
            }
        }

        // streaming finished, refresh chats to update titles/listings
        await loadChats(currentChatId);
        setSendingEnabled(true);
    } catch (e) {
        chat.innerHTML += `<p style="color:red">Error: ${e}</p>`;
        setSendingEnabled(true);
    }
}

async function pullModel() {
    const chat = document.getElementById("chat");
    isPullRunning = true;
    setSendingEnabled(false);
    setPullStatus("Pulling model... please wait.");
    chat.innerHTML += `<p><strong>Cobalt:</strong> Starting model pull...</p>`;

    try {
        const resp = await fetch("/chat/pull-model", { method: "POST" });
        const data = await resp.json();

        if (data.ok && data.started) {
            chat.innerHTML += `<p><strong>Cobalt:</strong> Pull started for ${data.model}. Waiting for completion...</p>`;
            await waitForPullToFinish();
        } else if (data.ok) {
            chat.innerHTML += `<p><strong>Cobalt:</strong> Pull already running for ${data.model}.</p>`;
            await waitForPullToFinish();
        } else {
            chat.innerHTML += `<p style="color:red"><strong>Cobalt:</strong> Pull failed: ${data.error || data.status || "unknown error"}</p>`;
            setSendingEnabled(true);
            setPullStatus("", false);
        }
    } catch (e) {
        chat.innerHTML += `<p style="color:red">Error pulling model: ${e}</p>`;
        setSendingEnabled(true);
        setPullStatus("", false);
    }
}

async function waitForPullToFinish() {
    const chat = document.getElementById("chat");

    while (true) {
        try {
            const resp = await fetch("/chat/pull-model/status");
            const data = await resp.json();

            if (!data.running) {
                if (data.done) {
                    chat.innerHTML += `<p><strong>Cobalt:</strong> Model ${data.model} is ready.</p>`;
                    setPullStatus(`Model ${data.model} is ready.`);
                } else if (data.error) {
                    chat.innerHTML += `<p style="color:red"><strong>Cobalt:</strong> Pull failed: ${data.error}</p>`;
                    setPullStatus(`Pull failed: ${data.error}`);
                }
                setSendingEnabled(true);
                isPullRunning = false;
                return;
            }

            setPullStatus(`Pulling ${data.model}... still working.`);
            await new Promise((resolve) => setTimeout(resolve, 3000));
        } catch (e) {
            chat.innerHTML += `<p style="color:red">Error checking pull status: ${e}</p>`;
            setSendingEnabled(true);
            setPullStatus("", false);
            isPullRunning = false;
            return;
        }
    }
}

window.addEventListener("DOMContentLoaded", async () => {
    await loadChats();
});
