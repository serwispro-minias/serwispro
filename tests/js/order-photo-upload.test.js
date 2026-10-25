const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Element {
    constructor({ id = '', name = '', files = [] } = {}) {
        this.id = id;
        this.name = name;
        this.files = files;
        this.value = '';
        this.textContent = '';
        this.children = [];
        this.listeners = new Map();
    }
    addEventListener(type, callback) {
        const list = this.listeners.get(type) || [];
        list.push(callback);
        this.listeners.set(type, list);
    }
    dispatch(type, event = {}) {
        for (const listener of this.listeners.get(type) || []) listener({ target: this, preventDefault() { this.defaultPrevented = true; }, ...event });
    }
    click() { this.clicked = true; }
    replaceChildren() { this.children = []; }
    append(child) { this.children.push(child); }
    querySelector(selector) { return this.children.find((child) => child.selector === selector) || null; }
}

class Form extends Element {
    submit() { this.nativeSubmitCount = (this.nativeSubmitCount || 0) + 1; }
}

function setupCreatePicker() {
    const elements = {
        'order-create-photo-files': new Element({ id: 'order-create-photo-files' }),
        'order-create-add-photo': new Element({ id: 'order-create-add-photo' }),
        'order-create-photo-preview': new Element({ id: 'order-create-photo-preview' }),
        'order-create-photo-feedback': new Element({ id: 'order-create-photo-feedback' }),
        'order-photo-draft-token': new Element({ id: 'order-photo-draft-token' }),
    };
    const form = new Form({ id: 'order-create-form' });
    elements['order-create-form'] = form;
    const documentListeners = new Map();
    const records = new Map();
    const document = {
        addEventListener(type, callback) {
            const list = documentListeners.get(type) || [];
            list.push(callback);
            documentListeners.set(type, list);
        },
        createElement() { return new Element(); },
        getElementById(id) { return elements[id] || null; },
    };
    const indexedDB = {
        open() {
            const request = {};
            queueMicrotask(() => {
                const store = {
                    put(value) { records.set(value.token, value); const operation = { result: value }; queueMicrotask(() => operation.onsuccess?.()); return operation; },
                    get(key) { const operation = { result: records.get(key) }; queueMicrotask(() => operation.onsuccess?.()); return operation; },
                    delete(key) { records.delete(key); const operation = {}; queueMicrotask(() => operation.onsuccess?.()); return operation; },
                };
                request.result = {
                    createObjectStore() { },
                    transaction() { return { objectStore: () => store, set oncomplete(callback) { queueMicrotask(callback); }, set onerror(callback) { this._onerror = callback; } }; },
                    close() { },
                };
                request.onsuccess?.();
            });
            return request;
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../app/static/js/order-photo-upload.js'), 'utf8'), {
        document, indexedDB, HTMLFormElement: Form, crypto: { randomUUID: () => 'draft-test-token' },
        URL, URLSearchParams, console,
    });
    for (const callback of documentListeners.get('DOMContentLoaded') || []) callback();
    return { elements, form, records };
}

test('new-order photos are staged locally and create submits only after the draft is stored', async () => {
    const { elements, form, records } = setupCreatePicker();
    const photo = { name: 'intake.jpg', size: 2048, type: 'image/jpeg' };
    elements['order-create-photo-files'].files = [photo];
    elements['order-create-photo-files'].dispatch('change');
    assert.equal(elements['order-create-photo-preview'].children.length, 1);
    assert.equal(form.nativeSubmitCount, undefined);

    let prevented = false;
    for (const listener of form.listeners.get('submit') || []) listener({ preventDefault() { prevented = true; } });
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(prevented, true);
    assert.equal(form.nativeSubmitCount, 1);
    assert.equal(elements['order-photo-draft-token'].value, 'draft-test-token');
    const staged = records.get('draft-test-token').files;
    assert.equal(staged.length, 1);
    assert.equal(staged[0].name, photo.name);
    assert.equal(staged[0].size, photo.size);
    assert.equal(staged[0].type, photo.type);
});
