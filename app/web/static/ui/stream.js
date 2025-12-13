export async function* ChatStream(response) {
    if (!response.ok || !response.body) {
        throw new Error('Stream not available');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                if (buffer.trim()) yield* processBuffer(buffer, true);
                break;
            }
            buffer += decoder.decode(value, { stream: true });

            // Yield events as we find them
            const { events, remaining } = extractEvents(buffer);
            buffer = remaining;

            for (const event of events) {
                yield event;
            }
        }
    } finally {
        reader.releaseLock();
    }
}

function extractEvents(buffer) {
    const events = [];
    while (true) {
        const idxNN = buffer.indexOf('\n\n');
        const idxCRNN = buffer.indexOf('\r\n\r\n');

        let boundaryIdx = -1;
        let boundaryLen = 0;

        if (idxNN !== -1 && idxCRNN !== -1) {
            boundaryIdx = Math.min(idxNN, idxCRNN);
            boundaryLen = boundaryIdx === idxCRNN ? 4 : 2;
        } else if (idxNN !== -1) {
            boundaryIdx = idxNN;
            boundaryLen = 2;
        } else if (idxCRNN !== -1) {
            boundaryIdx = idxCRNN;
            boundaryLen = 4;
        } else {
            break;
        }

        const rawEvent = buffer.slice(0, boundaryIdx);
        buffer = buffer.slice(boundaryIdx + boundaryLen);
        const parsed = parseEvent(rawEvent);
        if (parsed) events.push(parsed);
    }
    return { events, remaining: buffer };
}

function* processBuffer(buffer, final = false) {
    // Final flush if needed, though extractEvents usually handles loop
    const { events } = extractEvents(buffer);
    for (const event of events) yield event;
}

function parseEvent(rawEvent) {
    if (!rawEvent) return null;
    const lines = rawEvent.split(/\r?\n/);
    let eventName = 'message';
    const dataLines = [];

    for (const line of lines) {
        if (line.startsWith('event:')) {
            eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
            let payload = line.slice(5);
            if (payload.startsWith(' ')) payload = payload.slice(1);
            if (payload.endsWith('\r')) payload = payload.slice(0, -1);
            dataLines.push(payload);
        }
    }

    const data = dataLines.join('\n');
    return { event: eventName, data };
}
