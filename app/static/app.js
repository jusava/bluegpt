const messagesEl = document.getElementById('messages');
const promptEl = document.getElementById('prompt');
const formEl = document.getElementById('chat-form');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const showToolsToggle = document.getElementById('show-tools');
const modelLabelEl = document.getElementById('model-label');
const chatListEl = document.getElementById('chat-list');
const suggestionButtons = document.querySelectorAll('.suggestion-card');

let chatId = null;
let streaming = false;
let showTools = showToolsToggle ? showToolsToggle.checked : true;

if (showToolsToggle) {
    showToolsToggle.addEventListener('change', () => {
        showTools = showToolsToggle.checked;
    });
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderText(text) {
    if (window.marked && window.DOMPurify) {
        if (marked.setOptions) {
            marked.setOptions({ breaks: true, gfm: true });
        }
        const html = marked.parse(text);
        return DOMPurify.sanitize(html);
    }
    return fallbackMarkdown(text);
}

function addMessage(role, content, options = {}) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    if (role === 'assistant') avatar.textContent = '🤖';
    else if (role === 'tool') avatar.textContent = '🛠️';
    else avatar.textContent = '🙂';

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerHTML = options.typing ? '<div class="typing"><span></span><span></span><span></span></div>' : renderText(content);

    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    scrollToBottom();

    return { wrapper, bubble };
}

function renderHistory(history = []) {
    messagesEl.innerHTML = '';
    history.forEach((msg) => addMessage(msg.role, msg.content));
    scrollToBottom();
}

function startAssistantStream() {
    // Create the assistant bubble but keep it detached until final text is ready.
    const { bubble, wrapper } = addMessage('assistant', '', { typing: true });
    if (wrapper.parentElement === messagesEl) {
        messagesEl.removeChild(wrapper);
    }
    let text = '';
    return {
        append(chunk) {
            text += chunk;
            bubble.innerHTML = renderText(text);
            scrollToBottom();
        },
        done() {
            bubble.innerHTML = renderText(text);
            wrapper.classList.remove('streaming');
            scrollToBottom();
        },
        text() {
            return text;
        },
        attach() {
            messagesEl.appendChild(wrapper);
            scrollToBottom();
        },
    };
}

async function refreshSessions() {
    try {
        const res = await fetch('/api/sessions');
        if (!res.ok) return;
        const sessions = await res.json();
        chatListEl.innerHTML = '';
        if (!sessions.length) {
            chatListEl.innerHTML = '<div class="empty-chat">No conversations yet</div>';
            return;
        }
        sessions.forEach((s) => {
            const item = document.createElement('button');
            item.className = 'chat-item' + (s.chat_id === chatId ? ' active' : '');
            item.textContent = s.title || 'Chat';
            item.addEventListener('click', () => {
                loadChat(s.chat_id);
            });
            chatListEl.appendChild(item);
        });
    } catch (err) {
        console.error(err);
    }
}

async function refreshModel() {
    try {
        const res = await fetch('/api/model');
        if (!res.ok) return;
        const payload = await res.json();
        if (modelLabelEl && payload.model) {
            modelLabelEl.textContent = `Model: ${payload.model}`;
        }
    } catch (err) {
        console.error(err);
    }
}

async function loadChat(id) {
    chatId = id;
    try {
        const res = await fetch(`/api/chat/${encodeURIComponent(id)}`);
        if (!res.ok) throw new Error('Failed to load chat');
        const payload = await res.json();
        renderHistory(payload.messages || []);
    } catch (err) {
        console.error(err);
        messagesEl.innerHTML = '';
        addMessage('assistant', 'Could not load chat history.');
    } finally {
        refreshSessions();
    }
}

async function sendMessage(text) {
    streaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';
    const stream = startAssistantStream();

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, chat_id: chatId || null }),
        });

        if (!response.ok || !response.body) {
            throw new Error('Stream not available');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const flushEvent = (rawEvent) => {
            if (!rawEvent) return false;
            const lines = rawEvent.split(/\r?\n/);
            let event = 'message';
            const dataLines = [];
            for (const line of lines) {
                if (line.startsWith('event:')) event = line.slice(6).trim();
                if (line.startsWith('data:')) {
                    let payload = line.slice(5);
                    if (payload.startsWith(' ')) payload = payload.slice(1);
                    // Strip the leading 'data:' marker but keep the rest verbatim (including newlines).
                    dataLines.push(payload);
                }
            }
            const data = dataLines.join('\n');

            if (event === 'error') throw new Error(data || 'Stream error');
            if (event === 'tools') return false;
            if (['status', 'tool_start', 'tool_result'].includes(event)) {
                try {
                    const parsed = data ? JSON.parse(data) : {};
                    renderStatusEvent(event, parsed, showTools);
                } catch (e) {
                    console.error('Failed to parse status event', e);
                }
                return false;
            }
            if (event === 'done') {
                if (data) chatId = data;
                if (stream.attach) stream.attach();
                stream.done();
                return true;
            }
            if (data) stream.append(data);
            return false;
        };

        while (true) {
            const { done, value } = await reader.read();
            buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

            while (true) {
                const idxNN = buffer.indexOf('\n\n');
                const idxCRNN = buffer.indexOf('\r\n\r\n');
                const boundaryIdx =
                    idxNN === -1 ? idxCRNN : idxCRNN === -1 ? idxNN : Math.min(idxNN, idxCRNN);
                const boundaryLen = boundaryIdx === idxCRNN ? 4 : 2;
                if (boundaryIdx === -1) break;

                const rawEvent = buffer.slice(0, boundaryIdx);
                buffer = buffer.slice(boundaryIdx + boundaryLen);
                console.debug('SSE raw event:', rawEvent);
                const stop = flushEvent(rawEvent);
                if (stop) {
                    await refreshSessions();
                    streaming = false;
                    sendBtn.disabled = false;
                    sendBtn.textContent = 'Send';
                    return;
                }
            }

            if (done) {
                if (buffer.trim()) flushEvent(buffer);
                stream.done();
                break;
            }
        }
    } catch (err) {
        console.warn('Falling back to non-stream mode', err);
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, chat_id: chatId || null }),
        });
        const payload = await res.json();
        chatId = payload.chat_id;
        if (showTools) renderToolCalls(payload.tool_calls || []);
        stream.append(payload.reply || 'No response.');
        stream.done();
    } finally {
        streaming = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        await refreshSessions();
    }
}

formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = promptEl.value.trim();
    if (!text || streaming) return;
    addMessage('user', text);
    promptEl.value = '';
    sendMessage(text);
});

promptEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        formEl.dispatchEvent(new Event('submit'));
    }
});

newChatBtn.addEventListener('click', () => {
    chatId = null;
    messagesEl.innerHTML = '';
    addMessage('assistant', 'New chat started. How can I help?');
    refreshSessions();
});

suggestionButtons.forEach((btn) =>
    btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt || btn.textContent;
        promptEl.value = prompt;
        promptEl.focus();
    })
);

// seed welcome message
addMessage('assistant', 'Hey! I am BlueGPT. I use OpenAI plus optional MCP tools via a local agentic loop. Ask me anything, or click a suggestion to start.');
refreshSessions();
refreshModel();

function renderToolCalls(calls = []) {
    if (!Array.isArray(calls) || !calls.length) return;
    calls.forEach((call) => {
        const args = JSON.stringify(call.arguments ?? {}, null, 2);
        const output = typeof call.output === 'string' ? call.output : JSON.stringify(call.output, null, 2);
        const content = `Tool: ${call.name || 'unknown'}\nArgs:\n${args}\nResult:\n${output}`;
        addMessage('tool', content);
    });
}

function renderStatusEvent(eventType, payload = {}, verbose = true) {
    let text = '';
    if (eventType === 'tool_start') {
        text = verbose
            ? `Calling tool: ${payload.name || 'unknown'}\nArgs: ${JSON.stringify(payload.arguments ?? {}, null, 2)}`
            : `Calling tool: ${payload.name || 'unknown'}...`;
    } else if (eventType === 'tool_result') {
        if (!verbose) return;
        if (verbose) {
            const output = typeof payload.output === 'string' ? payload.output : JSON.stringify(payload.output, null, 2);
            text = `Tool result: ${payload.name || 'unknown'}\nOutput: ${output}`;
        } else {
            text = `Tool result: ${payload.name || 'unknown'}`;
        }
    } else {
        text = payload.message || JSON.stringify(payload);
    }
    addMessage('tool', text);
}

function fallbackMarkdown(raw) {
    // Escape basic HTML.
    let text = String(raw ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Fenced code blocks ``` ```
    text = text.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
    // Inline code `code`
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold **text**
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Italic *text*
    text = text.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    // Simple lists: lines starting with -, *, or number.
    const lines = text.split(/\r?\n/);
    const htmlParts = [];
    let listBuf = [];
    const flushList = () => {
        if (!listBuf.length) return;
        const items = listBuf.map((item) => `<li>${item}</li>`).join('');
        htmlParts.push(`<ul>${items}</ul>`);
        listBuf = [];
    };
    lines.forEach((line) => {
        const trimmed = line.trim();
        const listMatch = trimmed.match(/^([-*]|\d+\.)\s+(.*)$/);
        if (listMatch) {
            listBuf.push(listMatch[2]);
        } else {
            flushList();
            if (trimmed.length) {
                htmlParts.push(`<p>${trimmed}</p>`);
            }
        }
    });
    flushList();
    return htmlParts.join('') || text.replace(/\n/g, '<br>');
}
