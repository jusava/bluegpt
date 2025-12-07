import { addMessage, addProcessingBubble, startAssistantStream, renderHistory, renderStatusEvent } from './ui/messages.js';
import { attachSettingsListeners, loadChat, refreshGenerationSettings, refreshModel, refreshSessions, refreshTools } from './ui/settings.js';

const promptEl = document.getElementById('prompt');
const formEl = document.getElementById('chat-form');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const settingsToggle = document.getElementById('settings-toggle');
const settingsClose = document.getElementById('settings-close');
const settingsPanel = document.getElementById('settings-panel');
const suggestionButtons = document.querySelectorAll('.suggestion-card');
const suggestionsContainer = document.querySelector('.suggestions');

let chatId = null;
let streaming = false;
let settingsOpen = false;
let activeProgress = null;

const handleChatSelect = async (id) => {
    chatId = id;
    try {
        await loadChat(id);
    } catch (err) {
        console.error(err);
        addMessage('assistant', 'Could not load chat history.');
    } finally {
        refreshSessions(chatId, handleChatSelect);
    }
};

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
                    if (payload.endsWith('\r')) payload = payload.slice(0, -1);
                    // Strip the leading 'data:' marker but keep the rest verbatim (including newlines).
                    dataLines.push(payload);
                }
            }
            const eventName = event.toLowerCase();
            const data = dataLines.join('\n').replace(/\r$/, '');

            if (eventName === 'error') throw new Error(data || 'Stream error');
            if (['status', 'tool_start', 'tool_result', 'reasoning'].includes(eventName)) {
                try {
                    const parsed = data ? JSON.parse(data) : {};
                    renderStatusEvent(activeProgress, eventName, parsed);
                } catch (e) {
                    console.error('Failed to parse status event', e);
                }
                return false;
            }
            if (eventName === 'done') {
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
                // console.debug('SSE raw event:', rawEvent);
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
    renderHistory([]);
    addMessage('assistant', 'New chat started. How can I help?');
    refreshSessions(chatId, handleChatSelect);
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
refreshSessions(chatId, handleChatSelect);
refreshModel();
refreshTools();
refreshSamples();
refreshGenerationSettings();
attachSettingsListeners();
