export const createEvents = () => {
    const handlers = new Map();
    return {
        addEventListener(name, handler) {
            if (!handlers.has(name)) {
                handlers.set(name, []);
            }
            handlers.get(name).push(handler);
        },
        emit(name, event = {}) {
            handlers.get(name)?.forEach((handler) => handler(event));
        },
    };
};
