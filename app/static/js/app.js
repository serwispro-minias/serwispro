// Shared, context-declared keyboard support. Page actions opt in with data attributes.
(() => {
    const editable = (target) => target instanceof Element && Boolean(target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]'));
    const visible = (element) => Boolean(element && element.getClientRects().length && !element.disabled);
    const firstVisible = (selector) => [...document.querySelectorAll(selector)].find(visible);
    const modalReturnFocus = new WeakMap();

    function currentShortcutScope(target) {
        const element = target instanceof Element ? target : document.activeElement;
        return element?.closest('.modal.show, .tab-pane.show.active') || document;
    }

    function findInsertAction(target) {
        const element = target instanceof Element ? target : document.activeElement;
        if (editable(element) || element?.closest('[role="listbox"], [role="option"], [data-keyboard-listbox-input]')) return null;

        const form = element?.closest('form');
        const scope = form || currentShortcutScope(element);
        const context = element?.closest('[data-shortcut-insert-target]')?.dataset.shortcutInsertTarget;
        const candidates = [...scope.querySelectorAll('[data-shortcut-insert]')]
            .filter((candidate) => !context || candidate.dataset.shortcutInsertTarget === context);
        return candidates.length === 1 && visible(candidates[0]) ? candidates[0] : null;
    }

    function findSaveSubmitter(form) {
        if (!form || form.method?.toLowerCase() === 'get') return null;
        const explicit = [...form.querySelectorAll('[data-shortcut-save-submit], [data-shortcut-submit]')];
        if (explicit.length) return explicit.length === 1 && visible(explicit[0]) ? explicit[0] : null;

        const submits = [...form.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]')]
            .filter(visible);
        return submits.length === 1 ? submits[0] : null;
    }

    function submitCurrentForm(target) {
        const focused = target instanceof Element ? target : document.activeElement;
        const form = focused?.closest('form');
        const submitter = findSaveSubmitter(form);
        const explicitSave = form?.hasAttribute('data-shortcut-save') || form?.hasAttribute('data-shortcut-submit')
            || submitter?.hasAttribute('data-shortcut-save-submit') || submitter?.hasAttribute('data-shortcut-submit');
        if (!form || !explicitSave || !submitter || submitter.disabled || form.dataset.shortcutSubmitting === 'true') return false;
        if (!form.reportValidity()) return true;
        form.dataset.shortcutSubmitting = 'true';
        form.requestSubmit(submitter);
        return true;
    }

    document.addEventListener('show.bs.modal', (event) => {
        if (event.target instanceof HTMLElement) modalReturnFocus.set(event.target, event.relatedTarget || document.activeElement);
    });
    document.addEventListener('shown.bs.modal', (event) => {
        if (!(event.target instanceof HTMLElement)) return;
        const autofocus = event.target.querySelector('[autofocus], input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href]');
        autofocus?.focus();
    });
    document.addEventListener('hidden.bs.modal', (event) => {
        if (!(event.target instanceof HTMLElement)) return;
        const returnTarget = modalReturnFocus.get(event.target);
        if (returnTarget instanceof HTMLElement && returnTarget.isConnected) returnTarget.focus();
        modalReturnFocus.delete(event.target);
    });

    function showShortcutHelp() {
        let modal = document.getElementById('keyboard-shortcuts-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'keyboard-shortcuts-modal';
            modal.className = 'modal fade';
            modal.tabIndex = -1;
            modal.setAttribute('aria-labelledby', 'keyboard-shortcuts-title');
            modal.setAttribute('aria-hidden', 'true');
            modal.innerHTML = '<div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-header"><h2 class="modal-title fs-5" id="keyboard-shortcuts-title">Skróty klawiszowe</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Zamknij"></button></div><div class="modal-body"><p class="text-muted">Dostępne skróty zależą od bieżącego widoku.</p><dl class="shortcut-help-list"></dl></div></div></div>';
            document.body.appendChild(modal);
            modal.addEventListener('show.bs.modal', () => {
                const list = modal.querySelector('.shortcut-help-list');
                list.replaceChildren();
                const entries = [
                    ['Insert', 'Dodanie rekordu lub pozycji', 'Gdy bieżący widok udostępnia przycisk dodawania i fokus nie jest w edytowalnym polu.'],
                    ['Delete', 'Usunięcie zaznaczonego elementu', 'Poza edytowalnym polem; jeśli element ma akcję usuwania.'],
                    ['Ctrl + S / Ctrl + Enter', 'Zapis formularza', 'W formularzu z jednoznacznym, dostępnym przyciskiem zapisu.'],
                    ['F10', 'Drukowanie', 'Gdy bieżący widok udostępnia przycisk drukowania.'],
                    ['Ctrl + F', 'Przejście do wyszukiwarki', 'Gdy widok zawiera pole wyszukiwania.'],
                    ['Ctrl + Shift + F', 'Wyczyszczenie filtrów', 'Gdy widok udostępnia czyszczenie filtrów.'],
                    ['Strzałki / Enter / Esc', 'Obsługa listy podpowiedzi', 'Gdy fokus jest w polu wyszukiwania z wynikami.'],
                    ['Shift + F1', 'Ta pomoc', 'Dostępne w całej aplikacji.'],
                ];
                entries.forEach(([shortcut, action, context]) => {
                    const dt = document.createElement('dt'); dt.textContent = shortcut;
                    const dd = document.createElement('dd'); dd.textContent = `${action} — ${context}`;
                    list.append(dt, dd);
                });
            });
        }
        bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    document.addEventListener('keydown', (event) => {
        if (event.shiftKey && event.key === 'F1' && !event.ctrlKey && !event.altKey && !event.metaKey) {
            event.preventDefault(); showShortcutHelp(); return;
        }
        if (event.defaultPrevented || event.metaKey || event.isComposing) return;
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'f') {
            const clear = firstVisible('[data-shortcut-clear]');
            if (clear) { event.preventDefault(); clear.click(); }
            return;
        }
        if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'f') {
            const search = firstVisible('[data-main-search], input[type="search"], input[name="q"]');
            if (search) { event.preventDefault(); search.focus(); search.select?.(); }
            return;
        }

        const input = event.target instanceof Element ? event.target.closest('[data-keyboard-listbox-input]') : null;
        if (input) {
            if (event.ctrlKey && event.key === 'Enter' && input.getAttribute('aria-expanded') === 'true') {
                event.preventDefault();
                return;
            }
            const list = document.getElementById(input.getAttribute('aria-controls'));
            const options = list ? [...list.querySelectorAll('[role="option"]')].filter(visible) : [];
            const active = options.findIndex((option) => option.getAttribute('aria-selected') === 'true');
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                if (options.length) {
                    event.preventDefault();
                    const next = options[(active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length];
                    options.forEach((option) => option.setAttribute('aria-selected', String(option === next)));
                    next.scrollIntoView({ block: 'nearest' });
                }
                return;
            }
            if (event.key === 'Enter' && !event.ctrlKey && !event.altKey && !event.metaKey && options.length) { event.preventDefault(); (options[active] || options[0]).click(); return; }
            if (event.key === 'Escape') {
                const picker = input.closest('[data-search-picker]');
                if (picker) { event.preventDefault(); picker.classList.add('d-none'); picker.hidden = true; closePicker(input); document.getElementById(picker.dataset.triggerId)?.focus(); }
                else { event.preventDefault(); closePicker(input); document.getElementById(input.getAttribute('aria-controls'))?.classList.add('d-none'); }
                return;
            }
        }

        if (event.ctrlKey && !event.shiftKey && !event.altKey && !event.repeat && event.key.toLowerCase() === 's') {
            if (submitCurrentForm(event.target)) event.preventDefault();
            return;
        }
        if (event.ctrlKey && !event.shiftKey && !event.altKey && !event.repeat && event.key === 'Enter') {
            if (submitCurrentForm(event.target)) event.preventDefault();
            return;
        }
        if (event.altKey) return;
        if (event.key === 'Insert' && !event.ctrlKey && !event.shiftKey && !event.metaKey && !event.repeat) {
            const addAction = findInsertAction(event.target);
            if (addAction) { event.preventDefault(); addAction.click(); }
            return;
        }
        if (event.key === 'Delete' && !editable(event.target)) {
            const row = event.target instanceof Element ? event.target.closest('[data-selected-row="true"]') : null;
            const remove = row?.querySelector('[data-shortcut-delete]');
            if (remove && !remove.disabled) { event.preventDefault(); remove.click(); }
            return;
        }
        if (event.key === 'F10') {
            const print = firstVisible('[data-shortcut-print]');
            if (print) { event.preventDefault(); print.click(); }
            return;
        }
    });

    document.addEventListener('click', (event) => {
        const row = event.target instanceof Element ? event.target.closest('[data-selectable-row]') : null;
        if (row) row.closest('tbody')?.querySelectorAll('[data-selectable-row]').forEach((item) => {
            item.dataset.selectedRow = String(item === row);
            item.setAttribute('aria-selected', String(item === row));
        });
    });

    const typeaheadState = new WeakMap();
    const liveFilterState = new WeakMap();
    const closePicker = (input) => {
        const list = document.getElementById(input.getAttribute('aria-controls'));
        if (list) {
            list.replaceChildren();
            list.classList.add('d-none');
        }
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-busy');
    };

    const printPrompt = document.getElementById('print-intake-prompt');
    if (printPrompt && window.bootstrap?.Modal) {
        const promptModal = window.bootstrap.Modal.getOrCreateInstance(printPrompt, { backdrop: 'static', keyboard: false });
        let actionStarted = false;
        const showPrompt = () => {
            if (printPrompt.dataset.promptShown === 'true') return;
            printPrompt.dataset.promptShown = 'true';
            promptModal.show();
        };
        if (printPrompt.dataset.photosPending === 'true') {
            document.addEventListener('order-photos:pending-complete', showPrompt, { once: true });
            document.addEventListener('order-photos:pending-failed', showPrompt, { once: true });
        } else {
            showPrompt();
        }
        document.addEventListener('click', (event) => {
            const button = event.target instanceof Element ? event.target.closest('[data-print-intake-action]') : null;
            if (!button || !printPrompt.contains(button)) return;
            event.preventDefault();
            if (actionStarted) return;
            actionStarted = true;
            printPrompt.querySelectorAll('[data-print-intake-action]').forEach((actionButton) => { actionButton.disabled = true; });
            const action = button.dataset.printIntakeAction;
            const targetUrl = button.dataset.actionUrl;
            const shouldPrint = action === 'print' || action === 'print-photos';
            const printWindow = shouldPrint ? window.open('', '_blank') : null;
            if (printWindow) printWindow.opener = null;
            const finishAction = () => {
                printPrompt.addEventListener('hidden.bs.modal', () => {
                    if (shouldPrint && printWindow) printWindow.location.href = targetUrl;
                    else window.location.assign(targetUrl);
                }, { once: true });
                promptModal.hide();
            };
            if (action === 'print-photos' && printPrompt.dataset.photosPending === 'true') {
                const photoStatus = document.getElementById('print-intake-photo-status');
                if (photoStatus) photoStatus.textContent = 'Przesyłanie zdjęć przed wydrukiem…';
                const retryUpload = window.retryPendingOrderPhotoUpload;
                if (!retryUpload) {
                    if (printWindow) printWindow.close();
                    actionStarted = false;
                    printPrompt.querySelectorAll('[data-print-intake-action]').forEach((actionButton) => { actionButton.disabled = false; });
                    if (photoStatus) photoStatus.textContent = 'Nie można teraz przesłać oczekujących zdjęć. Ponów upload na stronie zlecenia.';
                    return;
                }
                Promise.resolve(retryUpload()).then((uploaded) => {
                    if (uploaded) {
                        printPrompt.dataset.photosPending = 'false';
                        finishAction();
                        return;
                    }
                    if (printWindow) printWindow.close();
                    actionStarted = false;
                    printPrompt.querySelectorAll('[data-print-intake-action]').forEach((actionButton) => { actionButton.disabled = false; });
                    if (photoStatus) photoStatus.textContent = 'Nie udało się przesłać zdjęć. Możesz ponowić wybór „Tak ze zdjęciami” albo wybrać wydruk bez zdjęć.';
                }).catch(() => {
                    if (printWindow) printWindow.close();
                    actionStarted = false;
                    printPrompt.querySelectorAll('[data-print-intake-action]').forEach((actionButton) => { actionButton.disabled = false; });
                    if (photoStatus) photoStatus.textContent = 'Błąd uploadu zdjęć. Możesz ponowić próbę.';
                });
                return;
            }
            finishAction();
        });
    }

    function makeOption(item, input, list) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'list-group-item list-group-item-action text-start';
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', 'false');
        const primary = document.createElement('span');
        primary.className = 'd-block fw-semibold';
        const code = item.code || item.number || '';
        const name = item.name || item.supplier || '';
        primary.textContent = item.display || (input.hasAttribute('data-navigate-on-select') && item.url ? name : [code, name].filter(Boolean).join(' | ')) || String(item.label || item.id || 'Wynik');
        button.append(primary);
        const metadata = [item.item_type, item.tax_id ? `NIP: ${item.tax_id}` : null, item.barcode, item.category, item.current_stock != null ? `stan: ${item.current_stock}` : null]
            .filter(Boolean).join(' · ');
        if (metadata) {
            const secondary = document.createElement('span');
            secondary.className = 'd-block small text-muted';
            secondary.textContent = metadata;
            button.append(secondary);
        }
        button.addEventListener('click', () => {
            input.dispatchEvent(new CustomEvent('live-search:select', { bubbles: true, detail: item }));
            closePicker(input);
            if (input.hasAttribute('data-navigate-on-select') && item.url) window.location.assign(item.url);
        });
        list.append(button);
    }

    function renderEmpty(list, message) {
        list.replaceChildren();
        const status = document.createElement('div');
        status.className = 'list-group-item text-muted';
        status.setAttribute('role', 'status');
        status.textContent = message;
        list.append(status);
    }

    document.addEventListener('input', (event) => {
        const input = event.target instanceof Element ? event.target.closest('[data-live-search-url]') : null;
        if (!input) return;
        const list = document.getElementById(input.getAttribute('aria-controls'));
        if (!list) return;
        let state = typeaheadState.get(input);
        if (!state) { state = { timer: null, controller: null, sequence: 0 }; typeaheadState.set(input, state); }
        window.clearTimeout(state.timer);
        state.controller?.abort();
        const query = input.value.trim();
        if (query.length < Number(input.dataset.minLength || 1)) { closePicker(input); return; }
        state.timer = window.setTimeout(async () => {
            const sequence = ++state.sequence;
            state.controller = new AbortController();
            input.setAttribute('aria-expanded', 'true');
            input.setAttribute('aria-busy', 'true');
            list.classList.remove('d-none');
            list.replaceChildren();
            const loading = document.createElement('div'); loading.className = 'list-group-item small text-muted';
            loading.setAttribute('role', 'status'); loading.textContent = 'Wyszukiwanie…'; list.append(loading);
            try {
                const url = new URL(input.dataset.liveSearchUrl, window.location.href);
                url.searchParams.set('q', query);
                url.searchParams.set('limit', input.dataset.resultLimit || '20');
                const dependentField = input.dataset.searchParamInput && document.getElementById(input.dataset.searchParamInput);
                if (input.dataset.searchParamName && dependentField?.value) {
                    url.searchParams.set(input.dataset.searchParamName, dependentField.value);
                }
                if (input.dataset.searchParamOrderId) url.searchParams.set('order_id', input.dataset.searchParamOrderId);
                const response = await fetch(url, { signal: state.controller.signal, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (!response.ok) throw new Error(`Search failed (${response.status})`);
                const payload = await response.json();
                if (sequence !== state.sequence || input.value.trim() !== query) return;
                const items = Array.isArray(payload.items) ? payload.items : [];
                if (!items.length) renderEmpty(list, 'Brak wyników.');
                else { list.replaceChildren(); items.forEach((item) => makeOption(item, input, list)); }
                input.removeAttribute('aria-busy');
            } catch (error) {
                if (error.name === 'AbortError') return;
                if (sequence === state.sequence) { renderEmpty(list, 'Nie udało się pobrać wyników. Spróbuj ponownie.'); input.removeAttribute('aria-busy'); }
            }
        }, Number(input.dataset.debounce || 250));
    });

    document.addEventListener('pointerdown', (event) => {
        document.querySelectorAll('[data-keyboard-listbox-input][aria-expanded="true"]').forEach((input) => {
            const list = document.getElementById(input.getAttribute('aria-controls'));
            if (!input.contains(event.target) && !list?.contains(event.target)) {
                closePicker(input);
                if (!input.closest('[data-search-picker]')) list?.classList.add('d-none');
            }
        });
    });

    function liveFilterUrl(form, page = '1') {
        const url = new URL(form.action || window.location.href, window.location.href);
        const params = new URLSearchParams(new FormData(form));
        params.set('page', page);
        url.search = params.toString();
        return url;
    }

    async function refreshLiveFilter(form, url, { push = false } = {}) {
        let state = liveFilterState.get(form);
        if (!state) { state = { timer: null, controller: null, sequence: 0 }; liveFilterState.set(form, state); }
        state.controller?.abort();
        state.controller = new AbortController();
        const sequence = ++state.sequence;
        const selector = form.dataset.liveTarget || '[data-live-results]';
        const target = document.querySelector(selector);
        if (!target) return;
        target.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(url, { signal: state.controller.signal, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok || response.redirected) throw new Error(`Filter failed (${response.status})`);
            const html = await response.text();
            if (sequence !== state.sequence) return;
            const parsed = new DOMParser().parseFromString(html, 'text/html');
            const replacement = parsed.querySelector(selector);
            if (!replacement) throw new Error('Missing live results container');
            target.replaceChildren(...Array.from(replacement.childNodes, (node) => document.importNode(node, true)));
            target.removeAttribute('aria-busy');
            if (push) history.pushState({}, '', url);
            else history.replaceState({}, '', url);
        } catch (error) {
            if (error.name !== 'AbortError') target.removeAttribute('aria-busy');
        }
    }

    document.addEventListener('input', (event) => {
        const field = event.target instanceof Element ? event.target : null;
        const form = field?.closest('form[data-live-filter]');
        if (!form || !field.matches('input[type="search"], input[type="text"], input:not([type])')) return;
        if (form.querySelector('[data-filter-select]')?.dataset.filterSelect === field.id) return;
        const state = liveFilterState.get(form) || { timer: null, controller: null, sequence: 0 };
        liveFilterState.set(form, state);
        window.clearTimeout(state.timer);
        const query = field.value.trim();
        const minLength = Number(form.dataset.minLength || 1);
        if (query && query.length < minLength) return;
        state.timer = window.setTimeout(() => refreshLiveFilter(form, liveFilterUrl(form)), Number(form.dataset.debounce || 300));
    });

    document.addEventListener('change', (event) => {
        const form = event.target instanceof Element ? event.target.closest('form[data-live-filter]') : null;
        if (form && event.target.matches('select')) refreshLiveFilter(form, liveFilterUrl(form));
    });

    document.addEventListener('submit', (event) => {
        const form = event.target instanceof HTMLFormElement ? event.target.closest('form[data-live-filter]') : null;
        if (!form) return;
        event.preventDefault();
        refreshLiveFilter(form, liveFilterUrl(form), { push: true });
    });

    document.addEventListener('click', (event) => {
        const link = event.target instanceof Element ? event.target.closest('[data-live-results] .pagination a[href]') : null;
        if (!link) return;
        const target = link.closest('[data-live-results]');
        const form = [...document.querySelectorAll('form[data-live-filter]')].find((candidate) => document.querySelector(candidate.dataset.liveTarget || '[data-live-results]') === target);
        if (!form) return;
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin) return;
        event.preventDefault();
        refreshLiveFilter(form, url, { push: true });
    });

    window.addEventListener('popstate', () => {
        document.querySelectorAll('form[data-live-filter]').forEach((form) => refreshLiveFilter(form, new URL(window.location.href)));
    });

    document.querySelectorAll('[data-filter-select]').forEach((select) => {
        const input = document.getElementById(select.dataset.filterSelect);
        if (!input) return;
        let list = document.getElementById(input.getAttribute('aria-controls'));
        if (!list) {
            list = document.createElement('div');
            list.id = `${input.id}-suggestions`;
            list.className = 'list-group contextual-search-list d-none';
            list.setAttribute('role', 'listbox');
            input.insertAdjacentElement('afterend', list);
            input.setAttribute('aria-controls', list.id);
        }
        input.parentElement?.classList.add('contextual-search-host');
        input.addEventListener('input', () => {
            const terms = input.value.normalize('NFC').toLocaleLowerCase('pl').trim().split(/\s+/).filter(Boolean);
            [...select.options].forEach((option) => {
                const searchable = `${option.text} ${option.dataset.search || ''}`.normalize('NFC').toLocaleLowerCase('pl');
                option.hidden = Boolean(option.value) && !terms.every((term) => searchable.includes(term));
            });
            list.replaceChildren();
            if (!terms.length) { list.classList.add('d-none'); input.setAttribute('aria-expanded', 'false'); return; }
            const matches = [...select.options].filter((option) => !option.hidden && option.value !== '');
            if (!matches.length) renderEmpty(list, 'Brak wyników.');
            else matches.slice(0, 20).forEach((option) => {
                const button = document.createElement('button'); button.type = 'button';
                button.className = 'list-group-item list-group-item-action text-start';
                button.setAttribute('role', 'option'); button.setAttribute('aria-selected', 'false');
                button.textContent = option.text;
                button.addEventListener('click', () => {
                    select.value = option.value; input.value = option.text; select.dispatchEvent(new Event('change', { bubbles: true }));
                    list.replaceChildren(); list.classList.add('d-none'); input.setAttribute('aria-expanded', 'false');
                });
                list.append(button);
            });
            list.classList.remove('d-none'); input.setAttribute('aria-expanded', 'true');
        });
    });
})();
