import { renderHistory } from './messages.js';

const modelLabelEl = document.getElementById('model-label');
const modelSelectEl = document.getElementById('model-select');
const reasoningSelectEl = document.getElementById('reasoning-effort');
const verbositySelectEl = document.getElementById('text-verbosity');
const maxTokensInput = document.getElementById('max-output-tokens');
const toolsTreeEl = document.getElementById('tools-tree');
const chatListEl = document.getElementById('chat-list');
let reasoningOptionsMap = {};

export async function refreshSessions(currentChatId, onSelectChat) {
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
            item.className = 'chat-item' + (s.chat_id === currentChatId ? ' active' : '');
            item.textContent = s.title || 'Chat';
            item.addEventListener('click', () => onSelectChat?.(s.chat_id));
            chatListEl.appendChild(item);
        });
    } catch (err) {
        console.error('Failed to refresh sessions:', err);
    }
}

export async function loadChat(id) {
    const res = await fetch(`/api/chat/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error('Failed to load chat');
    const payload = await res.json();
    renderHistory(payload.messages || []);
}

export async function refreshModel() {
    try {
        const res = await fetch('/api/model');
        if (!res.ok) return;
        const payload = await res.json();
        if (payload.reasoning_options) {
            reasoningOptionsMap = payload.reasoning_options;
        }
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
        const allowed = (payload.reasoning_options && payload.reasoning_options[payload.model]) || [];
        applyReasoningOptions(allowed, payload.reasoning_effort);
    } catch (err) {
        console.error('Failed to refresh model:', err);
    }
}

export async function refreshGenerationSettings() {
    try {
        const res = await fetch('/api/generation');
        if (!res.ok) return;
        const payload = await res.json();
        const model = modelSelectEl ? modelSelectEl.value : null;
        const allowed = (model && reasoningOptionsMap[model]) || reasoningOptionsMap.default || [];
        applyReasoningOptions(allowed, payload.reasoning_effort);
        setSelectOptions(verbositySelectEl, ["low", "medium", "high"], payload.text_verbosity);
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
        console.error('Failed to refresh generation settings:', err);
    }
}

export async function refreshTools() {
    try {
        const res = await fetch('/api/tools');
        if (!res.ok) return;
        const tools = await res.json();
        renderToolsTree(Array.isArray(tools) ? tools : []);
    } catch (err) {
        console.error('Failed to refresh tools:', err);
    }
}

function setSelectOptions(selectEl, options, current) {
    if (!selectEl || !Array.isArray(options)) return;
    const prev = selectEl.value;
    selectEl.innerHTML = '';
    options.forEach((opt) => {
        const optionEl = document.createElement('option');
        optionEl.value = opt;
        optionEl.textContent = opt.charAt(0).toUpperCase() + opt.slice(1);
        if (current === opt || (!current && prev === opt)) optionEl.selected = true;
        selectEl.appendChild(optionEl);
    });
    // console.debug('Set select options:', selectEl.id, options, current);
    if (current && options.includes(current)) {
        selectEl.value = current;
    } else {
        selectEl.value = options[0] || '';
    }
}

function applyReasoningOptions(allowed, current) {
    if (!Array.isArray(allowed) || !allowed.length) return;
    setSelectOptions(reasoningSelectEl, allowed, current);
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

export function attachSettingsListeners() {
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
                const payload = await res.json();
                if (payload.reasoning_options) {
                    reasoningOptionsMap = payload.reasoning_options;
                }
                const allowed =
                    (payload.reasoning_options && payload.reasoning_options[payload.model]) ||
                    (reasoningOptionsMap && reasoningOptionsMap[payload.model]) ||
                    [];
                applyReasoningOptions(allowed, payload.reasoning_effort);
                if (modelLabelEl) modelLabelEl.textContent = `Model: ${payload.model}`;
            } catch (err) {
                console.error('Model selection error:', err);
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
}
