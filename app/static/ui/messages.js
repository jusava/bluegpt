const messagesEl = document.getElementById('messages');

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
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

export function renderText(text) {
    if (window.marked && window.DOMPurify) {
        if (marked.setOptions) {
            marked.setOptions({ breaks: true, gfm: true });
        }
        const html = marked.parse(text);
        return DOMPurify.sanitize(html);
    }
    return fallbackMarkdown(text);
}

export function addMessage(role, content, options = {}) {
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

export function addProcessingBubble() {
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

export function startAssistantStream() {
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

export function renderHistory(history = []) {
    messagesEl.innerHTML = '';
    history.forEach((msg) => addMessage(msg.role, msg.content));
    scrollToBottom();
}

export function renderStatusEvent(activeProgress, eventType, payload = {}, verbose = true) {
    if (activeProgress && typeof activeProgress.addDetailEntry === 'function') {
        activeProgress.addDetailEntry(eventType, payload, verbose);
    }
}
