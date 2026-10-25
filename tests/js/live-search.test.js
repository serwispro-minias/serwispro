const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class FakeElement {
    constructor({ tagName = 'div', attrs = {}, dataset = {}, value = '' } = {}) {
        this.tagName = tagName.toUpperCase();
        this.attrs = { ...attrs };
        this.dataset = { ...dataset };
        this.value = value;
        this.children = [];
        this.listeners = new Map();
        this.className = '';
        this.textContent = '';
        this.disabled = false;
        const classes = new Set((attrs.class || '').split(/\s+/).filter(Boolean));
        this.classList = {
            add: (...names) => names.forEach((name) => classes.add(name)),
            remove: (...names) => names.forEach((name) => classes.delete(name)),
            contains: (name) => classes.has(name),
        };
    }
    hasAttribute(name) { return Object.hasOwn(this.attrs, name); }
    getAttribute(name) { return this.attrs[name] ?? null; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    removeAttribute(name) { delete this.attrs[name]; }
    closest(selector) {
        if (selector.includes('[data-live-search-url]') && this.hasAttribute('data-live-search-url')) return this;
        if (selector.includes('[data-print-intake-action]') && this.hasAttribute('data-print-intake-action')) return this;
        return null;
    }
    contains(element) { return this === element || this.children.includes(element); }
    addEventListener(name, callback) {
        const handlers = this.listeners.get(name) || [];
        handlers.push(callback);
        this.listeners.set(name, handlers);
    }
    dispatchEvent(event) {
        event.target = this;
        for (const callback of this.listeners.get(event.type) || []) callback(event);
        return true;
    }
    replaceChildren(...children) { this.children = [...children]; }
    append(...children) { this.children.push(...children); }
    click() { for (const callback of this.listeners.get('click') || []) callback({ target: this }); }
    querySelectorAll(selector) {
        if (selector === '[data-print-intake-action]') return this.children.filter((child) => child.hasAttribute('data-print-intake-action'));
        return selector === '[role="option"]' ? this.children.filter((child) => child.getAttribute('role') === 'option') : [];
    }
}

class FakeCustomEvent {
    constructor(type, options = {}) { this.type = type; this.detail = options.detail; this.bubbles = options.bubbles; }
}

function setup({ responsePayload, dependentValue = null, withPrintPrompt = false, photosPending = false } = {}) {
    const documentListeners = new Map();
    const input = new FakeElement({
        tagName: 'input',
        attrs: {
            'aria-controls': 'suggestions',
            'data-keyboard-listbox-input': '',
            'data-live-search-url': '/customers/search',
            'data-result-limit': '15',
            'data-min-length': '2',
        },
        dataset: {
            liveSearchUrl: '/customers/search',
            resultLimit: '15',
            minLength: '2',
            debounce: '0',
        },
    });
    const results = new FakeElement({ attrs: { class: 'list-group contextual-search-list d-none' } });
    const dependent = dependentValue === null ? null : new FakeElement({ value: String(dependentValue) });
    const nodes = { suggestions: results, customer_id: dependent };
    let prompt = null;
    let modalStats = { show: 0, hide: 0 };
    if (withPrintPrompt) {
        prompt = new FakeElement({ dataset: { photosPending: String(photosPending) } });
        const print = new FakeElement({ attrs: { 'data-print-intake-action': 'print', 'data-action-url': '/orders/5/print/intake?mode=inline' }, dataset: { printIntakeAction: 'print', actionUrl: '/orders/5/print/intake?mode=inline' } });
        const printPhotos = new FakeElement({ attrs: { 'data-print-intake-action': 'print-photos', 'data-action-url': '/orders/5/print/intake?mode=inline&include_photos=1' }, dataset: { printIntakeAction: 'print-photos', actionUrl: '/orders/5/print/intake?mode=inline&include_photos=1' } });
        const skip = new FakeElement({ attrs: { 'data-print-intake-action': 'skip', 'data-action-url': '/orders/' }, dataset: { printIntakeAction: 'skip', actionUrl: '/orders/' } });
        prompt.children.push(print, printPhotos, skip);
        nodes['print-intake-prompt'] = prompt;
    }
    const document = {
        activeElement: input,
        addEventListener(name, callback) {
            const handlers = documentListeners.get(name) || [];
            handlers.push(callback);
            documentListeners.set(name, handlers);
        },
        getElementById(id) { return nodes[id] || null; },
        dispatchEvent(event) {
            for (const handler of documentListeners.get(event.type) || []) handler(event);
            return true;
        },
        createElement(tagName) { return new FakeElement({ tagName }); },
        querySelectorAll() { return []; },
    };
    const requestedUrls = [];
    const navigations = [];
    const opened = [];
    const window = {
        location: { href: 'http://localhost/orders/new', assign: (url) => navigations.push(url) },
        addEventListener() { },
        open: (...args) => { const openedWindow = { opener: 'parent', location: { href: args[0] }, close() { this.closed = true; } }; opened.push({ args, openedWindow }); return openedWindow; },
        setTimeout(callback) { queueMicrotask(callback); return 1; },
        clearTimeout() { },
    };
    const bootstrap = withPrintPrompt ? { Modal: { getOrCreateInstance: () => ({ show: () => { modalStats.show += 1; }, hide: () => { modalStats.hide += 1; } }) } } : undefined;
    window.bootstrap = bootstrap;
    const sandbox = {
        document, window, bootstrap, Element: FakeElement, HTMLElement: FakeElement,
        CustomEvent: FakeCustomEvent, URL, URLSearchParams, AbortController,
        fetch: async (url) => {
            requestedUrls.push(String(url));
            return { ok: true, json: async () => responsePayload };
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../app/static/js/app.js'), 'utf8'), sandbox);
    const emitInput = async (value) => {
        input.value = value;
        for (const callback of documentListeners.get('input') || []) callback({ target: input });
        await new Promise((resolve) => setImmediate(resolve));
        await new Promise((resolve) => setImmediate(resolve));
    };
    return { input, results, dependent, requestedUrls, emitInput, prompt, modalStats, documentListeners, navigations, opened, window, document };
}

test('customer autocomplete shows fetched results and dispatches the selected record id', async () => {
    const { input, results, requestedUrls, emitInput } = setup({
        responsePayload: { items: [{ id: 42, name: 'Acme Serwis', display: 'Acme Serwis', tax_id: '1234567890' }] },
    });
    let chosen = null;
    input.addEventListener('live-search:select', (event) => { chosen = event.detail; });

    await emitInput('Acme');

    assert.equal(new URL(requestedUrls[0]).pathname, '/customers/search');
    assert.equal(new URL(requestedUrls[0]).searchParams.get('q'), 'Acme');
    assert.equal(input.getAttribute('aria-expanded'), 'true');
    assert.equal(results.classList.contains('d-none'), false);
    const [option] = results.querySelectorAll('[role="option"]');
    assert.ok(option);
    assert.equal(option.children[0].textContent, 'Acme Serwis');

    option.click();
    assert.equal(chosen.id, 42);
    assert.equal(input.getAttribute('aria-expanded'), 'false');
    assert.equal(results.classList.contains('d-none'), true);
});

test('dependent device autocomplete sends the customer id and displays an empty state', async () => {
    const { input, results, requestedUrls, emitInput } = setup({ responsePayload: { items: [] }, dependentValue: 17 });
    input.dataset.searchParamName = 'customer_id';
    input.dataset.searchParamInput = 'customer_id';

    await emitInput('Laser');

    const requestUrl = new URL(requestedUrls[0]);
    assert.equal(requestUrl.searchParams.get('q'), 'Laser');
    assert.equal(requestUrl.searchParams.get('customer_id'), '17');
    assert.equal(results.classList.contains('d-none'), false);
    assert.equal(results.children[0].textContent, 'Brak wyników.');
});

test('print without photos closes once, then opens the intake PDF without photo opt-in', () => {
    const { prompt, modalStats, documentListeners, opened } = setup({ withPrintPrompt: true });
    const [print, printPhotos, skip] = prompt.children;
    let prevented = 0;
    const event = { target: print, preventDefault() { prevented += 1; } };
    for (const handler of documentListeners.get('click') || []) handler(event);
    for (const handler of documentListeners.get('click') || []) handler(event);

    assert.equal(prevented, 2);
    assert.equal(modalStats.show, 1);
    assert.equal(modalStats.hide, 1);
    assert.equal(print.disabled, true);
    assert.equal(printPhotos.disabled, true);
    assert.equal(skip.disabled, true);
    assert.equal(opened.length, 1);
    assert.equal(opened[0].openedWindow.opener, null);
    assert.equal(opened[0].openedWindow.location.href, '');

    prompt.dispatchEvent({ type: 'hidden.bs.modal' });
    assert.equal(opened[0].openedWindow.location.href, '/orders/5/print/intake?mode=inline');
});

test('print with photos explicitly opens the photos-enabled intake PDF for this order', () => {
    const { prompt, modalStats, documentListeners, opened } = setup({ withPrintPrompt: true });
    const [, printPhotos] = prompt.children;
    const event = { target: printPhotos, preventDefault() { } };
    for (const handler of documentListeners.get('click') || []) handler(event);
    for (const handler of documentListeners.get('click') || []) handler(event);

    assert.equal(modalStats.hide, 1);
    assert.equal(opened.length, 1);
    prompt.dispatchEvent({ type: 'hidden.bs.modal' });
    assert.equal(opened[0].openedWindow.location.href, '/orders/5/print/intake?mode=inline&include_photos=1');
});

test('print prompt waits for staged photos and retries before enabling the photo PDF', async () => {
    const { prompt, modalStats, document, documentListeners, opened, window } = setup({ withPrintPrompt: true, photosPending: true });
    const [, printPhotos] = prompt.children;
    let attempts = 0;
    window.retryPendingOrderPhotoUpload = async () => { attempts += 1; return true; };
    assert.equal(modalStats.show, 0);
    document.dispatchEvent({ type: 'order-photos:pending-failed' });
    assert.equal(modalStats.show, 1);
    for (const handler of documentListeners.get('click') || []) handler({ target: printPhotos, preventDefault() { } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(attempts, 1);
    assert.equal(prompt.dataset.photosPending, 'false');
    assert.equal(modalStats.hide, 1);
    prompt.dispatchEvent({ type: 'hidden.bs.modal' });
    assert.equal(opened[0].openedWindow.location.href, '/orders/5/print/intake?mode=inline&include_photos=1');
});

test('skip choice closes once, then navigates to order list without submitting anything', () => {
    const { prompt, modalStats, documentListeners, navigations, opened } = setup({ withPrintPrompt: true });
    const [print, printPhotos, skip] = prompt.children;
    const event = { target: skip, preventDefault() { } };
    for (const handler of documentListeners.get('click') || []) handler(event);
    for (const handler of documentListeners.get('click') || []) handler(event);

    assert.equal(modalStats.hide, 1);
    assert.equal(print.disabled, true);
    assert.equal(printPhotos.disabled, true);
    assert.equal(skip.disabled, true);
    assert.equal(opened.length, 0);
    assert.deepEqual(navigations, []);

    prompt.dispatchEvent({ type: 'hidden.bs.modal' });
    assert.deepEqual(navigations, ['/orders/']);
});

test('photo-print choice waits for staged upload to complete before closing and printing', async () => {
    const { prompt, modalStats, documentListeners, opened, window, document } = setup({ withPrintPrompt: true, photosPending: true });
    const [, printPhotos] = prompt.children;
    let uploadAttempts = 0;
    window.retryPendingOrderPhotoUpload = async () => { uploadAttempts += 1; return true; };
    document.dispatchEvent({ type: 'order-photos:pending-failed' });
    assert.equal(modalStats.show, 1);
    const event = { target: printPhotos, preventDefault() { } };
    for (const handler of documentListeners.get('click') || []) handler(event);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(uploadAttempts, 1);
    assert.equal(prompt.dataset.photosPending, 'false');
    assert.equal(modalStats.hide, 1);
    prompt.dispatchEvent({ type: 'hidden.bs.modal' });
    assert.equal(opened[0].openedWindow.location.href, '/orders/5/print/intake?mode=inline&include_photos=1');
});

test('photo-print upload failure keeps prompt open and does not start printing', async () => {
    const { prompt, modalStats, documentListeners, opened, window, document } = setup({ withPrintPrompt: true, photosPending: true });
    const [, printPhotos] = prompt.children;
    window.retryPendingOrderPhotoUpload = async () => false;
    document.dispatchEvent({ type: 'order-photos:pending-failed' });
    for (const handler of documentListeners.get('click') || []) handler({ target: printPhotos, preventDefault() { } });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(modalStats.hide, 0);
    assert.equal(opened.length, 1);
    assert.equal(opened[0].openedWindow.closed, true);
    assert.equal(printPhotos.disabled, false);
});
