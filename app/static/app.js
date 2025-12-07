const messagesEl = document.getElementById('messages');
const promptEl = document.getElementById('prompt');
const formEl = document.getElementById('chat-form');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const showToolsToggle = document.getElementById('show-tools');
const modelLabelEl = document.getElementById('model-label');
const settingsToggle = document.getElementById('settings-toggle');
const settingsClose = document.getElementById('settings-close');
const settingsPanel = document.getElementById('settings-panel');
const toolsTreeEl = document.getElementById('tools-tree');
const modelSelectEl = document.getElementById('model-select');
const reasoningSelectEl = document.getElementById('reasoning-effort');
const verbositySelectEl = document.getElementById('text-verbosity');
const maxTokensInput = document.getElementById('max-output-tokens');
const chatListEl = document.getElementById('chat-list');
const suggestionButtons = document.querySelectorAll('.suggestion-card');
const suggestionsContainer = document.querySelector('.suggestions');

let chatId = null;
let streaming = false;
let showTools = true;
let settingsOpen = false;
let activeProgress = null;

if (showToolsToggle) {
    showToolsToggle.checked = true;
    const toggleWrapper = showToolsToggle.closest('.toggle');
    if (toggleWrapper) toggleWrapper.style.display = 'none';
}

if (settingsToggle && settingsPanel) {
    settingsToggle.addEventListener('click', () => {
        settingsOpen = !settingsOpen;
        settingsPanel.classList.toggle('open', settingsOpen);
    });
}

if (settingsClose && settingsPanel) {
    settingsClose.addEventListener('click', () => {
        settingsOpen = false;
        settingsPanel.classList.remove('open');
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
    else if (role === 'status') avatar.textContent = '⏳';
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

function addProcessingBubble() {
    const start = performance.now();
    const { wrapper, bubble } = addMessage('status', '', { typing: false });
    wrapper.classList.add('processing');

    bubble.innerHTML = '';
    const header = document.createElement('div');
    header.className = 'progress-header';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'progress-toggle';
    toggle.textContent = '▼';
    const summary = document.createElement('span');
    summary.className = 'progress-summary';
    header.appendChild(toggle);
    header.appendChild(summary);
    bubble.appendChild(header);

    const detailsContainer = document.createElement('div');
    detailsContainer.className = 'progress-detail-wrapper collapsed';
    const details = document.createElement('div');
    details.className = 'progress-details';
    detailsContainer.appendChild(details);
    bubble.appendChild(detailsContainer);

    let collapsed = true;
    const setCollapsed = (next) => {
        collapsed = next;
        detailsContainer.classList.toggle('collapsed', collapsed);
        toggle.textContent = collapsed ? '▼' : '▲';
    };
    toggle.addEventListener('click', () => setCollapsed(!collapsed));

    const setSummary = (text) => {
        summary.textContent = text;
    };

    const tick = () => {
        const elapsed = (performance.now() - start) / 1000;
        setSummary(`Processing… (${elapsed.toFixed(1)}s)`);
    };

    tick();
    const interval = setInterval(tick, 300);
    let finished = false;

    const stop = () => {
        if (interval) clearInterval(interval);
    };

    return {
        addDetailEntry(eventType, payload, verbose = true) {
            const item = document.createElement('div');
            item.className = 'bubble detail-bubble';

            const headerRow = document.createElement('div');
            headerRow.className = 'detail-header';
            const dToggle = document.createElement('button');
            dToggle.type = 'button';
            dToggle.className = 'detail-toggle';
            dToggle.textContent = '▼';
            const title = document.createElement('span');
            title.className = 'detail-title';

            if (eventType === 'tool_start') {
                title.textContent = `Calling tool: ${payload.name || 'unknown'}`;
            } else if (eventType === 'tool_result') {
                title.textContent = `Tool result: ${payload.name || 'unknown'}`;
            } else if (eventType === 'reasoning') {
                title.textContent = 'Reasoning';
            } else {
                title.textContent = payload.message || 'Status update';
            }

            headerRow.appendChild(dToggle);
            headerRow.appendChild(title);

            const body = document.createElement('div');
            body.className = 'detail-body';

            const lines = [];
            if (eventType === 'tool_start' && verbose) {
                lines.push(`Args:\n${JSON.stringify(payload.arguments ?? {}, null, 2)}`);
            }
            if (eventType === 'tool_result' && verbose) {
                const output = typeof payload.output === 'string' ? payload.output : JSON.stringify(payload.output, null, 2);
                lines.push(`Output:\n${output}`);
            }
            if (eventType === 'reasoning' && verbose) {
                const reasoning = payload.reasoning || payload;
                const summaryText = Array.isArray(reasoning.summary)
                    ? reasoning.summary.map((s) => s.text).filter(Boolean).join('\n')
                    : '';
                const contentText = Array.isArray(reasoning.content)
                    ? reasoning.content.map((c) => c.text).filter(Boolean).join('\n')
                    : '';
                const combined = [summaryText, contentText].filter(Boolean).join('\n\n');
                if (combined) {
                    lines.push(combined);
                }
            }
            if (!lines.length && payload && verbose) {
                lines.push(JSON.stringify(payload, null, 2));
            }
            body.innerHTML = renderText(lines.join('\n\n'));
            body.style.display = 'none';

            let dCollapsed = true;
            const setDetailCollapsed = (next) => {
                dCollapsed = next;
                body.style.display = dCollapsed ? 'none' : 'block';
                dToggle.textContent = dCollapsed ? '▼' : '▲';
            };
            dToggle.addEventListener('click', () => setDetailCollapsed(!dCollapsed));

            item.appendChild(headerRow);
            item.appendChild(body);
            details.appendChild(item);
            scrollToBottom();
            return { setDetailCollapsed };
        },
        complete(label = 'Completed') {
            if (finished) return;
            finished = true;
            stop();
            const elapsed = (performance.now() - start) / 1000;
            wrapper.classList.remove('processing');
            setSummary(`${label} in ${elapsed.toFixed(1)}s`);
        },
        fail(label = 'Request failed') {
            if (finished) return;
            finished = true;
            stop();
            const elapsed = (performance.now() - start) / 1000;
            wrapper.classList.add('error');
            setSummary(`${label} (${elapsed.toFixed(1)}s)`);
        },
    };
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
        if (modelSelectEl && payload.available) {
            const currentValue = modelSelectEl.value;
            modelSelectEl.innerHTML = '';
            (payload.available || []).forEach((m) => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (payload.model === m) opt.selected = true;
                modelSelectEl.appendChild(opt);
            });
            if (currentValue && payload.available.includes(currentValue)) {
                modelSelectEl.value = currentValue;
            }
        }
    } catch (err) {
        console.error(err);
    }
}

async function refreshGenerationSettings() {
    try {
        const res = await fetch('/api/generation');
        if (!res.ok) return;
        const payload = await res.json();
        if (reasoningSelectEl && payload.reasoning_effort) {
            reasoningSelectEl.value = payload.reasoning_effort;
        }
        if (verbositySelectEl && payload.text_verbosity) {
            verbositySelectEl.value = payload.text_verbosity;
        }
        if (maxTokensInput && payload.max_output_tokens) {
            maxTokensInput.value = payload.max_output_tokens;
        }
    } catch (err) {
        console.error(err);
    }
}

async function refreshTools() {
    try {
        const res = await fetch('/api/tools');
        if (!res.ok) return;
        const tools = await res.json();
        renderToolsTree(Array.isArray(tools) ? tools : []);
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
    const progress = addProcessingBubble();
    activeProgress = progress;
    const stream = startAssistantStream();
    let completed = false;

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
            if (['status', 'tool_start', 'tool_result', 'reasoning'].includes(event)) {
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
                progress.complete();
                completed = true;
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
        progress.complete();
        completed = true;
    } finally {
        if (!completed) {
            progress.complete();
        }
        activeProgress = null;
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

async function refreshSamples() {
    try {
        const res = await fetch('/api/samples');
        if (!res.ok) return;
        const samples = await res.json();
        if (!Array.isArray(samples) || !suggestionsContainer) return;
        suggestionsContainer.innerHTML = '';
        samples.forEach((s) => {
            const btn = document.createElement('button');
            btn.className = 'suggestion-card';
            btn.dataset.prompt = s.prompt || '';
            btn.innerHTML = `
                <div class="suggestion-title">${s.title || 'Sample'}</div>
                <p>${s.description || ''}</p>
            `;
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt || btn.textContent;
                promptEl.value = prompt;
                promptEl.focus();
            });
            suggestionsContainer.appendChild(btn);
        });
    } catch (err) {
        console.error(err);
    }
}

// seed welcome message & data
addMessage('assistant', 'Hey! I am BlueGPT. I use OpenAI plus optional MCP tools via a local agentic loop. Ask me anything, or click a suggestion to start.');
refreshSessions();
refreshModel();
refreshTools();
refreshSamples();
refreshGenerationSettings();

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
        text = `Calling tool: ${payload.name || 'unknown'}`;
    } else if (eventType === 'tool_result') {
        text = `Tool result: ${payload.name || 'unknown'}`;
    } else if (eventType === 'reasoning') {
        const reasoning = payload.reasoning || payload;
        const summaryText = Array.isArray(reasoning.summary)
            ? reasoning.summary.map((s) => s.text).filter(Boolean).join('\n')
            : '';
        const contentText = Array.isArray(reasoning.content)
            ? reasoning.content.map((c) => c.text).filter(Boolean).join('\n')
            : '';
        text = summaryText || contentText || 'Reasoning...';
    } else {
        text = payload.message || JSON.stringify(payload);
    }
    if (activeProgress && typeof activeProgress.addDetailEntry === 'function') {
        activeProgress.addDetailEntry(eventType, payload, verbose);
    } else {
        const summary = addMessage('tool', text);
        if (eventType === 'tool_result' && verbose) {
            const output = typeof payload.output === 'string' ? payload.output : JSON.stringify(payload.output, null, 2);
            addMessage('tool', `Output:\n${output}`);
        }
    }
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

function renderToolsTree(tools = []) {
    if (!toolsTreeEl) return;
    toolsTreeEl.innerHTML = '';
    if (!tools.length) {
        toolsTreeEl.innerHTML = '<div class="empty-chat">No tools available</div>';
        return;
    }
    const grouped = tools.reduce((acc, tool) => {
        const key = tool.source || 'unknown';
        acc[key] = acc[key] || { tools: [], active: true };
        acc[key].tools.push(tool);
        return acc;
    }, {});

    Object.entries(grouped).forEach(([source, list]) => {
        const group = document.createElement('div');
        group.className = 'tool-group';

        const titleRow = document.createElement('div');
        titleRow.className = 'tool-group-title';
        const groupCb = document.createElement('input');
        groupCb.type = 'checkbox';
        const allActive = list.tools.every((t) => t.active !== false);
        groupCb.checked = allActive;
        groupCb.addEventListener('change', async () => {
            const active = groupCb.checked;
            await Promise.all(
                list.tools.map(async (tool) => {
                    await toggleTool(tool.name, active);
                    tool.active = active;
                })
            );
            renderToolsTree(tools);
        });
        const title = document.createElement('span');
        title.textContent = source;
        titleRow.appendChild(groupCb);
        titleRow.appendChild(title);
        group.appendChild(titleRow);

        list.tools.forEach((tool) => {
            const item = document.createElement('label');
            item.className = 'tool-item';
            if (!groupCb.checked) item.classList.add('disabled');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = tool.active !== false;
            cb.disabled = !groupCb.checked;
            cb.addEventListener('change', async () => {
                try {
                    await toggleTool(tool.name, cb.checked);
                    tool.active = cb.checked;
                } catch (err) {
                    console.error(err);
                    cb.checked = !cb.checked;
                }
            });
            const name = document.createElement('span');
            name.textContent = tool.name;
            item.appendChild(cb);
            item.appendChild(name);
            group.appendChild(item);
        });

        toolsTreeEl.appendChild(group);
    });
}

async function toggleTool(name, active) {
    await fetch(`/api/tools/${encodeURIComponent(name)}/active`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
    });
}

if (modelSelectEl) {
    modelSelectEl.addEventListener('change', async () => {
        try {
            const val = modelSelectEl.value;
            const res = await fetch('/api/model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: val }),
            });
            if (!res.ok) throw new Error('Failed to set model');
            await refreshModel();
        } catch (err) {
            console.error(err);
        }
    });
}

if (reasoningSelectEl || verbositySelectEl || maxTokensInput) {
    const pushGeneration = async () => {
        try {
            const body = {
                reasoning_effort: reasoningSelectEl ? reasoningSelectEl.value : 'none',
                text_verbosity: verbositySelectEl ? verbositySelectEl.value : 'low',
                max_output_tokens: maxTokensInput ? parseInt(maxTokensInput.value, 10) || 1000 : 1000,
            };
            const res = await fetch('/api/generation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error('Failed to update generation settings');
        } catch (err) {
            console.error(err);
        }
    };

    if (reasoningSelectEl) reasoningSelectEl.addEventListener('change', pushGeneration);
    if (verbositySelectEl) verbositySelectEl.addEventListener('change', pushGeneration);
    if (maxTokensInput) maxTokensInput.addEventListener('change', pushGeneration);
}
