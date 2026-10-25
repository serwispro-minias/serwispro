const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class TestElement {
    constructor({ tagName = 'button', attrs = {}, parent = null } = {}) {
        this.tagName = tagName.toUpperCase();
        this.attrs = attrs;
        this.dataset = Object.fromEntries(Object.entries(attrs)
            .filter(([key]) => key.startsWith('data-'))
            .map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value]));
        this.parentElement = parent;
        this.disabled = false;
        this.clicked = 0;
        this.attributes = {};
    }
    hasAttribute(name) { return Object.hasOwn(this.attrs, name); }
    getAttribute(name) { return this.attrs[name] ?? null; }
    getClientRects() { return [1]; }
    matches(selector) {
        if (selector.includes('input') && this.tagName === 'INPUT') return true;
        if (selector.includes('textarea') && this.tagName === 'TEXTAREA') return true;
        if (selector.includes('select') && this.tagName === 'SELECT') return true;
        if (selector.includes('[contenteditable="true"]') && this.attrs.contenteditable === 'true') return true;
        if (selector.includes('[role="textbox"]') && this.attrs.role === 'textbox') return true;
        return false;
    }
    closest(selector) {
        for (let current = this; current; current = current.parentElement) {
            if (selector.includes('form') && current.tagName === 'FORM') {
                if (!selector.includes('[') || current.hasAttribute('data-shortcut-save') || current.hasAttribute('data-shortcut-submit')) return current;
            }
            if (selector.includes('[data-keyboard-listbox-input]') && current.hasAttribute('data-keyboard-listbox-input')) return current;
            if (selector.includes('[data-shortcut-insert-context]') && current.hasAttribute('data-shortcut-insert-context')) return current;
            if (selector.includes('[data-shortcut-insert-target]') && current.hasAttribute('data-shortcut-insert-target')) return current;
            if ((selector.includes('[role="listbox"]') && current.attrs.role === 'listbox') ||
                (selector.includes('[role="option"]') && current.attrs.role === 'option')) return current;
            if (this.matches(selector)) return this;
        }
        return null;
    }
    querySelectorAll(selector) { return this.childrenBySelector?.[selector] || []; }
    click() { this.clicked += 1; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    scrollIntoView() { this.scrolled = true; }
}

class TestForm extends TestElement {
    constructor({ explicit = [], submits = [], inserts = [] } = {}) {
        super({ tagName: 'form', attrs: { 'data-shortcut-save': '' } });
        this.method = 'post';
        this.explicit = explicit;
        this.submits = submits;
        this.inserts = inserts;
        this.requested = [];
        this.valid = true;
    }
    querySelectorAll(selector) {
        if (selector === '[data-shortcut-insert]') return this.inserts;
        if (selector.includes('data-shortcut-save-submit')) return this.explicit;
        if (selector.includes('button[type="submit"]')) return this.submits;
        return [];
    }
    requestSubmit(submitter) { this.requested.push(submitter); }
    reportValidity() { return this.valid; }
}

function setup({ insertActions = [], lookup = {} } = {}) {
    const listeners = new Map();
    const document = {
        activeElement: null,
        addEventListener(name, callback) { listeners.set(name, callback); },
        querySelectorAll(selector) { return selector === '[data-shortcut-insert]' ? insertActions : []; },
        getElementById(id) { return lookup[id] || null; },
    };
    const window = { addEventListener() { } };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../app/static/js/app.js'), 'utf8'), {
        document, window, Element: TestElement, HTMLElement: TestElement,
        KeyboardEvent: { DOM_KEY_LOCATION_LEFT: 1 },
    });
    return { keydown: listeners.get('keydown') };
}

function keyEvent(target, values = {}) {
    let prevented = 0;
    return {
        target, key: '', code: '', ctrlKey: false, shiftKey: false, altKey: false,
        metaKey: false, repeat: false, isComposing: false, defaultPrevented: false,
        getModifierState: () => false,
        preventDefault() { prevented += 1; this.defaultPrevented = true; },
        get prevented() { return prevented; },
        ...values,
    };
}

test('Ctrl+Enter requests exactly one validated submit on the focused save form', () => {
    const submit = new TestElement();
    const form = new TestForm({ explicit: [submit], submits: [submit] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.deepEqual(form.requested, [submit]);
    assert.equal(event.prevented, 1);
});

test('Ctrl+Enter does not guess between multiple submit actions', () => {
    const form = new TestForm({ submits: [new TestElement(), new TestElement()] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.equal(form.requested.length, 0);
    assert.equal(event.prevented, 0);
});

test('Ctrl+Enter selects the explicitly designated save action when other submit buttons exist', () => {
    const save = new TestElement();
    const secondary = new TestElement();
    const form = new TestForm({ explicit: [save], submits: [save, secondary] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.deepEqual(form.requested, [save]);
    assert.equal(event.prevented, 1);
});

test('a disabled designated save action never falls back to another submit button', () => {
    const disabledSave = new TestElement();
    disabledSave.disabled = true;
    const otherAction = new TestElement();
    const form = new TestForm({ explicit: [disabledSave], submits: [otherAction] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.equal(form.requested.length, 0);
    assert.equal(event.prevented, 0);
});

test('Ctrl+Enter does not submit an invalid form', () => {
    const save = new TestElement();
    const form = new TestForm({ explicit: [save] });
    form.valid = false;
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.equal(form.requested.length, 0);
    assert.equal(event.prevented, 1);
});

test('repeated Ctrl+Enter does not submit a second time', () => {
    const submit = new TestElement();
    const form = new TestForm({ explicit: [submit] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    const event = keyEvent(field, { key: 'Enter', ctrlKey: true, repeat: true });

    keydown(event);

    assert.equal(form.requested.length, 0);
    assert.equal(event.prevented, 0);
});

test('the same form is submitted only once while the first submission is in flight', () => {
    const save = new TestElement();
    const form = new TestForm({ explicit: [save] });
    const field = new TestElement({ tagName: 'input', parent: form });
    const { keydown } = setup();
    keydown(keyEvent(field, { key: 'Enter', ctrlKey: true }));
    const secondEvent = keyEvent(field, { key: 'Enter', ctrlKey: true });

    keydown(secondEvent);

    assert.deepEqual(form.requested, [save]);
    assert.equal(secondEvent.prevented, 0);
});

test('Insert invokes the unique current-view add action once', () => {
    const add = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const { keydown } = setup({ insertActions: [add] });
    const event = keyEvent(new TestElement(), { key: 'Insert' });

    keydown(event);

    assert.equal(add.clicked, 1);
    assert.equal(event.prevented, 1);
});

test('Insert is ignored in editable controls and suggestion listboxes', () => {
    const add = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const { keydown } = setup({ insertActions: [add] });
    for (const target of [new TestElement({ tagName: 'input' }), new TestElement({ tagName: 'textarea' }), new TestElement({ attrs: { role: 'option' } })]) {
        const event = keyEvent(target, { key: 'Insert' });
        keydown(event);
        assert.equal(event.prevented, 0);
    }
    assert.equal(add.clicked, 0);
});

test('Insert does nothing when there is no unique enabled add action', () => {
    const { keydown: noAction } = setup();
    const event = keyEvent(new TestElement(), { key: 'Insert' });
    noAction(event);
    assert.equal(event.prevented, 0);

    const first = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const second = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const { keydown: ambiguous } = setup({ insertActions: [first, second] });
    const ambiguousEvent = keyEvent(new TestElement(), { key: 'Insert' });
    ambiguous(ambiguousEvent);
    assert.equal(ambiguousEvent.prevented, 0);
    assert.equal(first.clicked + second.clicked, 0);

    const disabled = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    disabled.disabled = true;
    const unrelated = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const { keydown: disabledAndAvailable } = setup({ insertActions: [disabled, unrelated] });
    const disabledEvent = keyEvent(new TestElement(), { key: 'Insert' });
    disabledAndAvailable(disabledEvent);
    assert.equal(disabledEvent.prevented, 0);
    assert.equal(unrelated.clicked, 0);
});

test('Insert uses only the focused form and its matching selector context', () => {
    const customerAction = new TestElement({ attrs: { 'data-shortcut-insert': '', 'data-shortcut-insert-target': 'customer' } });
    const deviceAction = new TestElement({ attrs: { 'data-shortcut-insert': '', 'data-shortcut-insert-target': 'device' } });
    const form = new TestForm({ inserts: [customerAction, deviceAction] });
    customerAction.parentElement = form;
    deviceAction.parentElement = form;
    const { keydown } = setup();
    const event = keyEvent(customerAction, { key: 'Insert' });

    keydown(event);

    assert.equal(customerAction.clicked, 1);
    assert.equal(deviceAction.clicked, 0);
    assert.equal(event.prevented, 1);
});

test('Alt+D is not an add shortcut', () => {
    const add = new TestElement({ attrs: { 'data-shortcut-insert': '' } });
    const { keydown } = setup({ insertActions: [add] });
    const event = keyEvent(new TestElement(), { key: 'd', code: 'KeyD', altKey: true });

    keydown(event);

    assert.equal(add.clicked, 0);
    assert.equal(event.prevented, 0);
});

test('plain Enter still chooses the highlighted typeahead result', () => {
    const option = new TestElement({ attrs: { role: 'option', 'aria-selected': 'true' } });
    const list = { querySelectorAll: () => [option] };
    const input = new TestElement({ tagName: 'input', attrs: { 'data-keyboard-listbox-input': '', 'aria-controls': 'suggestions' } });
    const { keydown } = setup({ lookup: { suggestions: list } });
    const event = keyEvent(input, { key: 'Enter' });

    keydown(event);

    assert.equal(option.clicked, 1);
    assert.equal(event.prevented, 1);
});

test('Ctrl+Enter does not submit or select while a typeahead popup is open', () => {
    const save = new TestElement();
    const form = new TestForm({ explicit: [save] });
    const input = new TestElement({
        tagName: 'input', attrs: {
            'data-keyboard-listbox-input': '',
            'aria-controls': 'suggestions',
            'aria-expanded': 'true',
        }, parent: form
    });
    const option = new TestElement({ attrs: { role: 'option', 'aria-selected': 'true' } });
    const { keydown } = setup({ lookup: { suggestions: { querySelectorAll: () => [option] } } });
    const event = keyEvent(input, { key: 'Enter', ctrlKey: true });

    keydown(event);

    assert.equal(form.requested.length, 0);
    assert.equal(option.clicked, 0);
    assert.equal(event.prevented, 1);
});
