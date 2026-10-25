const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { URLSearchParams } = require('node:url');
const vm = require('node:vm');

const templatePath = path.join(__dirname, '../../app/templates/orders/partials/order_readiness_summary.html');
const template = fs.readFileSync(templatePath, 'utf8');
const scripts = [...template.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi)];
assert.equal(scripts.length, 1, 'Execute the actual readiness inline script, not a copied implementation');
const inlineScript = scripts[0][1];

class FakeElement {
    constructor() {
        this.textContent = 'server-rendered text';
        this.innerHTML = '<tr><td>server-rendered row</td></tr>';
        this.style = { width: '17%' };
        this.listeners = new Map();
    }
    addEventListener(type, callback) {
        const handlers = this.listeners.get(type) || [];
        handlers.push(callback);
        this.listeners.set(type, handlers);
    }
    async click() {
        for (const callback of this.listeners.get('click') || []) await callback({ target: this });
        await settle();
    }
}

function settle() {
    return new Promise((resolve) => setImmediate(resolve));
}

function summary(percentage = 75) {
    return {
        status: 'PARTIAL', percentage, pending_purchases: 2,
        purchase_statuses: { ORDERED: 2 }, expected_delivery: '2026-11-02',
        lines: [{ code: 'PART-1', name: 'Filter', required: 4, available: 3, reserved: 1, to_order: 1, status: 'PARTIAL' }],
    };
}

function setup({ initialResponse = { ok: true, payload: summary() } } = {}) {
    const nodes = Object.fromEntries([
        'status', 'percent', 'progress', 'purchases', 'purchase-status', 'delivery', 'lines',
    ].map((name) => [`[data-readiness-${name}]`, new FakeElement()]));
    const refresh = new FakeElement();
    const reserve = new FakeElement();
    const csrf = { tagName: 'INPUT', type: 'hidden', name: 'csrf_token', value: 'hidden-token +&=ąć' };
    nodes['[data-readiness-csrf]'] = csrf;
    nodes['[data-readiness-action="refresh"]'] = refresh;
    nodes['[data-readiness-action="reserve"]'] = reserve;
    const panel = {
        dataset: { readinessUrl: '/orders/42/readiness', reserveUrl: '/orders/42/readiness/reserve' },
        querySelector(selector) {
            assert.ok(Object.hasOwn(nodes, selector), `Unexpected panel selector: ${selector}`);
            return nodes[selector];
        },
    };
    const shortcut = () => { };
    const documentListeners = new Map([['keydown', [shortcut]]]);
    const windowListeners = new Map([['keydown', [shortcut]]]);
    function register(listeners, type, callback) {
        const handlers = listeners.get(type) || [];
        handlers.push(callback);
        listeners.set(type, handlers);
    }
    const intervals = [];
    const document = {
        onkeydown: shortcut,
        addEventListener: (type, callback) => register(documentListeners, type, callback),
        getElementById(id) {
            assert.equal(id, 'order-readiness-panel');
            return panel;
        },
    };
    const window = {
        onkeydown: shortcut,
        addEventListener: (type, callback) => register(windowListeners, type, callback),
        setInterval(callback, delay) { intervals.push({ callback, delay }); return intervals.length; },
    };
    const beforeDocument = Object.getOwnPropertyDescriptors(document);
    const beforeWindow = Object.getOwnPropertyDescriptors(window);
    const requests = [];
    const alerts = [];
    let nextResponse = initialResponse;
    const sandbox = {
        document, window, URLSearchParams,
        alert: (message) => alerts.push(message),
        fetch: async (url, options) => {
            requests.push({ url, options });
            const response = nextResponse;
            return { ok: response.ok, status: response.status ?? 200, json: async () => response.payload };
        },
    };
    const beforeGlobals = Object.keys(sandbox).sort();
    vm.runInNewContext(inlineScript, sandbox, { filename: templatePath });
    function snapshot() {
        return Object.fromEntries(Object.entries(nodes)
            .filter(([, node]) => node instanceof FakeElement)
            .map(([selector, node]) => [selector, {
                textContent: node.textContent, innerHTML: node.innerHTML, width: node.style.width,
            }]));
    }
    function assertShortcutsUnchanged() {
        assert.deepEqual(Object.getOwnPropertyDescriptors(document), beforeDocument);
        assert.deepEqual(Object.getOwnPropertyDescriptors(window), beforeWindow);
        assert.deepEqual([...documentListeners], [['keydown', [shortcut]]]);
        assert.deepEqual([...windowListeners], [['keydown', [shortcut]]]);
        assert.deepEqual(Object.keys(sandbox).sort(), beforeGlobals);
        assert.deepEqual([...refresh.listeners.keys()], ['click']);
        assert.deepEqual([...reserve.listeners.keys()], ['click']);
    }
    return {
        nodes, panel, csrf, refresh, reserve, requests, alerts, intervals, snapshot, assertShortcutsUnchanged,
        respondWith(response) { nextResponse = response; },
    };
}

function assertGet(request, expectedUrl) {
    assert.equal(request.url, expectedUrl);
    // Fetch defaults to GET when the method is omitted.
    assert.equal(request.options.method ?? 'GET', 'GET');
    assert.equal(request.options.body, undefined);
    assert.equal(request.options.headers['X-Requested-With'], 'XMLHttpRequest');
}

test('startup, refresh click and periodic refresh only GET the readiness endpoint', async () => {
    const fixture = setup();
    await settle();
    assert.equal(fixture.requests.length, 1);
    assertGet(fixture.requests[0], fixture.panel.dataset.readinessUrl);
    assert.equal(fixture.nodes['[data-readiness-percent]'].textContent, '75%');

    fixture.respondWith({ ok: true, payload: summary(80) });
    await fixture.refresh.click();
    assert.equal(fixture.requests.length, 2);
    assertGet(fixture.requests[1], fixture.panel.dataset.readinessUrl);
    assert.equal(fixture.nodes['[data-readiness-percent]'].textContent, '80%');

    assert.equal(fixture.intervals.length, 1);
    assert.equal(fixture.intervals[0].delay, 30000);
    await fixture.intervals[0].callback();
    await settle();
    assert.equal(fixture.requests.length, 3);
    assertGet(fixture.requests[2], fixture.panel.dataset.readinessUrl);
    assert.deepEqual(fixture.alerts, []);
    fixture.assertShortcutsUnchanged();
});

test('reserve click POSTs URLSearchParams with the current hidden-input CSRF token', async () => {
    assert.match(template, /<input\b(?=[^>]*type="hidden")(?=[^>]*name="csrf_token")(?=[^>]*data-readiness-csrf)[^>]*>/);
    const fixture = setup();
    await settle();
    assertGet(fixture.requests[0], fixture.panel.dataset.readinessUrl);
    fixture.csrf.value = 'changed hidden token +&=ąć';
    fixture.respondWith({ ok: true, payload: { ok: true, summary: summary(100) } });

    await fixture.reserve.click();

    assert.equal(fixture.requests.length, 2);
    const { url, options } = fixture.requests[1];
    assert.equal(url, fixture.panel.dataset.reserveUrl);
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['X-Requested-With'], 'XMLHttpRequest');
    assert.ok(options.body instanceof URLSearchParams);
    assert.deepEqual([...options.body], [['csrf_token', fixture.csrf.value]]);
    assert.equal(new URLSearchParams(options.body.toString()).get('csrf_token'), fixture.csrf.value);
    assert.equal(fixture.nodes['[data-readiness-percent]'].textContent, '100%');
    assert.deepEqual(fixture.alerts, []);
    fixture.assertShortcutsUnchanged();
});

for (const action of ['startup', 'refresh', 'reserve']) {
    for (const denial of [
        { name: 'HTTP 401', ok: false, status: 401, message: 'Authentication required' },
        { name: 'HTTP 403', ok: false, status: 403, message: 'Permission denied' },
        { name: 'payload ok=false', ok: true, status: 200, payloadOk: false, message: 'Reservation denied' },
        { name: 'denial without a message', ok: false, status: 403 },
    ]) {
        test(`${action}: ${denial.name} alerts without rendering the denied summary`, async () => {
            // Include a valid, visibly different summary so an accidental render cannot pass silently.
            const response = {
                ok: denial.ok, status: denial.status,
                payload: { ok: denial.payloadOk, message: denial.message, summary: summary(99) },
            };
            const fixture = setup(action === 'startup' ? { initialResponse: response } : {});
            if (action !== 'startup') await settle();
            const before = fixture.snapshot();
            if (action === 'startup') {
                await settle();
            } else {
                fixture.respondWith(response);
                await fixture[action].click();
            }

            assert.deepEqual(fixture.snapshot(), before);
            assert.deepEqual(fixture.alerts, [denial.message || 'Nie udało się wykonać operacji.']);
            assert.equal(fixture.requests.length, action === 'startup' ? 1 : 2);
            const request = fixture.requests.at(-1);
            if (action === 'reserve') {
                assert.equal(request.url, fixture.panel.dataset.reserveUrl);
                assert.equal(request.options.method, 'POST');
                assert.ok(request.options.body instanceof URLSearchParams);
                assert.equal(request.options.body.get('csrf_token'), fixture.csrf.value);
            } else {
                assertGet(request, fixture.panel.dataset.readinessUrl);
            }
            fixture.assertShortcutsUnchanged();
        });
    }
}