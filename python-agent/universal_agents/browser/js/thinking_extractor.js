(function () {
    'use strict';

    const START_TIME = Date.now();
    const MAX_TIME_MS = 20000;
    let searchCount = 0;
    const MAX_SEARCHES = 5000;

    function shouldStop() {
        return (Date.now() - START_TIME) > MAX_TIME_MS || searchCount++ > MAX_SEARCHES;
    }

    function fastSearch(obj, maxDepth) {
        maxDepth = maxDepth || 5;
        const queue = [{ obj: obj, depth: 0 }];

        while (queue.length > 0 && !shouldStop()) {
            const { obj: current, depth } = queue.shift();

            if (!current || typeof current !== 'object' || depth > maxDepth) {
                continue;
            }

            // Direct check: is this object a thinking block?
            if (current.type === 'thinking' && current.thinking && typeof current.thinking === 'string') {
                return {
                    thinking: current.thinking,
                    summaries: current.summaries || [],
                    found_via: 'direct'
                };
            }

            // Check for chat_messages structure
            if (Array.isArray(current.chat_messages)) {
                for (let msg of current.chat_messages) {
                    if (Array.isArray(msg.content)) {
                        for (let block of msg.content) {
                            if (block && block.type === 'thinking' && block.thinking) {
                                return {
                                    thinking: block.thinking,
                                    summaries: block.summaries || [],
                                    found_via: 'chat_messages'
                                };
                            }
                        }
                    }
                }
            }

            // Check content array
            if (Array.isArray(current.content)) {
                for (let item of current.content) {
                    if (item && item.type === 'thinking' && item.thinking) {
                        return {
                            thinking: item.thinking,
                            summaries: item.summaries || [],
                            found_via: 'content_array'
                        };
                    }
                }
            }

            // Queue children for BFS
            if (depth < maxDepth) {
                for (let key in current) {
                    if (current.hasOwnProperty(key) && current[key] && typeof current[key] === 'object') {
                        if (current[key] instanceof Node || typeof current[key] === 'function') continue;
                        try {
                            queue.push({ obj: current[key], depth: depth + 1 });
                        } catch (e) { }
                    }
                }
            }
        }

        return null;
    }

    window.claudeThinkingExtractor = {
        extractAll: function () {
            // Strategy 1: Search window global objects
            const globalTargets = ['__NEXT_DATA__', '__remixContext', '__REACT_CONTEXT__'];

            for (let target of globalTargets) {
                if (shouldStop()) break;
                if (window[target]) {
                    const result = fastSearch(window[target], 4);
                    if (result) {
                        result.found_via = 'window.' + target;
                        return result;
                    }
                }
            }

            // Strategy 2: Search React Fiber
            if (!shouldStop()) {
                const root = document.querySelector('#__next') || document.querySelector('[data-reactroot]');
                if (root) {
                    const fiberKey = Object.keys(root).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternal'));
                    if (fiberKey && root[fiberKey]) {
                        const fiber = root[fiberKey];

                        if (fiber.memoizedState) {
                            const result = fastSearch(fiber.memoizedState, 3);
                            if (result) {
                                result.found_via = 'react_fiber_state';
                                return result;
                            }
                        }

                        if (fiber.memoizedProps) {
                            const result = fastSearch(fiber.memoizedProps, 3);
                            if (result) {
                                result.found_via = 'react_fiber_props';
                                return result;
                            }
                        }
                    }
                }
            }

            return null;
        }
    };
})();
