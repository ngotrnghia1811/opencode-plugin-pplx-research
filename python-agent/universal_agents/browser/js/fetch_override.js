(function () {
    'use strict';

    if (window.fetch.isOverridden) {
        console.log('[FetchOverride] Already installed.');
        return;
    }

    console.log('[FetchOverride] Installing fetch intercept...');

    window.__claude_api_responses = window.__claude_api_responses || [];
    window.__claude_thinking_data = window.__claude_thinking_data || null;

    const originalFetch = window.fetch;

    window.fetch = async function (...args) {
        const [url, options] = args;

        try {
            const response = await originalFetch.apply(this, args);
            const clonedResponse = response.clone();

            if (typeof url === 'string' && url.includes('/api/organizations/') && url.includes('/chat_conversations')) {
                console.log(`[FetchOverride] >> Potential thinking data in ${url}`);

                try {
                    const data = await clonedResponse.json();

                    window.__claude_api_responses.push({
                        url: url,
                        timestamp: new Date().toISOString(),
                        data: data
                    });

                    if (data && data.chat_messages) {
                        console.log('[FetchOverride] >> Found chat_messages in response. Caching for extraction.');
                        window.__claude_thinking_data = { convoData: data };
                    }

                } catch (jsonError) {
                    // Not JSON or parsing failed
                }
            }

            return response;

        } catch (fetchError) {
            console.error('[FetchOverride] Fetch error:', fetchError);
            throw fetchError;
        }
    };

    window.fetch.isOverridden = true;

    window.getThinkingFromCapturedData = function () {
        if (!window.__claude_thinking_data) {
            return null;
        }

        const data = window.__claude_thinking_data;
        const chatMessages = data.convoData?.chat_messages || [];

        for (let i = chatMessages.length - 1; i >= 0; i--) {
            const message = chatMessages[i];
            if (!message.content || !Array.isArray(message.content)) continue;

            for (let j = 0; j < message.content.length; j++) {
                const block = message.content[j];
                if (block && block.type === 'thinking' && block.thinking) {
                    return {
                        thinking: block.thinking,
                        summaries: block.summaries || [],
                        found_in: `chat_messages[${i}].content[${j}]`,
                    };
                }
            }
        }

        return null;
    };

    window.clearCapturedThinking = function () {
        window.__claude_thinking_data = null;
    };

    console.log('[FetchOverride] Fetch intercept installed successfully.');
})();
