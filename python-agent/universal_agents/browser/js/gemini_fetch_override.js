/**
 * Gemini API fetch interceptor for thinking/reasoning extraction.
 *
 * Captures responses from /generate and /stream endpoints and extracts
 * thinking content from streaming JSON chunks.
 */
(function () {
    if (window.__gemini_thinking_override_installed) return;
    window.__gemini_thinking_override_installed = true;

    window._gemini_api_responses = [];
    window._gemini_last_thinking = null;

    const originalFetch = window.fetch;
    window.fetch = function (...args) {
        const url = args[0];
        if (
            typeof url === "string" &&
            (url.includes("/generate") || url.includes("/stream"))
        ) {
            return originalFetch.apply(this, args).then(function (response) {
                const clonedResponse = response.clone();
                clonedResponse
                    .text()
                    .then(function (text) {
                        const lines = text.split("\n").filter(function (line) {
                            return line.trim();
                        });
                        for (var i = 0; i < lines.length; i++) {
                            try {
                                var data = JSON.parse(lines[i]);
                                var thinking =
                                    data.thinking || data.thought || data.reasoning;
                                if (thinking) {
                                    window._gemini_last_thinking = thinking;
                                }
                                window._gemini_api_responses.push(data);
                            } catch (e) {
                                // Skip non-JSON lines
                            }
                        }
                    })
                    .catch(function () { });
                return response;
            });
        }
        return originalFetch.apply(this, args);
    };

    window.getGeminiThinking = function () {
        return window._gemini_last_thinking;
    };

    window.clearGeminiThinking = function () {
        window._gemini_last_thinking = null;
        window._gemini_api_responses = [];
    };
})();
