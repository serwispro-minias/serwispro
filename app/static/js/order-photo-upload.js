(() => {
    const databaseName = 'serwispro-order-photo-drafts';
    const storeName = 'drafts';
    const maxFiles = 10;
    const maxBytes = 10 * 1024 * 1024;
    const accepted = new Set(['image/jpeg', 'image/png', 'image/webp']);

    function openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(databaseName, 1);
            request.onupgradeneeded = () => request.result.createObjectStore(storeName, { keyPath: 'token' });
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function draftRequest(mode, token, value) {
        const database = await openDatabase();
        return new Promise((resolve, reject) => {
            const transaction = database.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = mode === 'put' ? store.put(value) : mode === 'get' ? store.get(token) : store.delete(token);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
            transaction.oncomplete = () => database.close();
            transaction.onerror = () => { database.close(); reject(transaction.error); };
        });
    }

    function validateFiles(files) {
        if (files.length > maxFiles) return `Można dodać maksymalnie ${maxFiles} zdjęć.`;
        if (files.some((file) => !accepted.has(file.type))) return 'Dozwolone formaty zdjęć: JPEG, PNG i WebP.';
        if (files.some((file) => file.size > maxBytes)) return 'Maksymalny rozmiar pojedynczego zdjęcia to 10 MB.';
        return '';
    }

    function initializePicker({ input, button, preview, feedback, form, createMode, tokenInput }) {
        if (!input || !button || !preview || !feedback) return;
        if (!createMode) input.name = 'files';
        let selected = [];
        let locked = false;
        const render = () => {
            preview.replaceChildren();
            selected.forEach((file, index) => {
                const item = document.createElement('div');
                item.className = 'd-flex align-items-center justify-content-between border rounded p-2 mb-1';
                const label = document.createElement('span');
                label.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`;
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'btn btn-sm btn-outline-danger';
                remove.textContent = 'Usuń';
                remove.addEventListener('click', () => { selected.splice(index, 1); render(); });
                item.append(label, remove);
                preview.append(item);
            });
            if (!selected.length) preview.textContent = 'Brak wybranych zdjęć.';
        };

        if (createMode && tokenInput?.value) {
            draftRequest('get', tokenInput.value).then((draft) => {
                if (draft?.files?.length) { selected = draft.files; render(); }
            }).catch(() => { feedback.textContent = 'Nie udało się odtworzyć kolejki zdjęć.'; });
        }

        button.addEventListener('click', () => input.click());
        input.addEventListener('change', () => {
            const incoming = Array.from(input.files || []);
            const candidate = [...selected, ...incoming];
            const error = validateFiles(candidate);
            if (error) feedback.textContent = error;
            else { selected = candidate; feedback.textContent = ''; }
            input.value = '';
            render();
        });

        if (createMode && form) {
            form.addEventListener('submit', (event) => {
                if (locked || !selected.length) return;
                event.preventDefault();
                locked = true;
                feedback.textContent = 'Zapisywanie zlecenia i kolejki zdjęć…';
                const token = tokenInput.value || crypto.randomUUID();
                tokenInput.value = token;
                draftRequest('put', token, { token, files: selected }).then(() => {
                    HTMLFormElement.prototype.submit.call(form);
                }).catch(() => {
                    locked = false;
                    feedback.textContent = 'Nie udało się przygotować zdjęć. Zlecenie nie zostało wysłane — spróbuj ponownie.';
                    tokenInput.value = '';
                });
            });
            return;
        }

        if (form) {
            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                if (locked) return;
                const error = validateFiles(selected);
                if (!selected.length || error) { feedback.textContent = error || 'Wybierz co najmniej jedno zdjęcie.'; return; }
                locked = true;
                const submit = form.querySelector('[type="submit"]');
                if (submit) submit.disabled = true;
                feedback.textContent = 'Przesyłanie zdjęć…';
                try {
                    const data = new FormData(form);
                    selected.forEach((file) => data.append(input.name, file, file.name));
                    const response = await fetch(form.action, { method: 'POST', body: data, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                    const result = await response.json();
                    if (!response.ok || !result.ok) throw new Error(result.message || 'Nie udało się przesłać zdjęć.');
                    selected = [];
                    render();
                    feedback.textContent = result.message || 'Zdjęcia zostały zapisane.';
                    form.dispatchEvent(new CustomEvent('order-photos:uploaded', { bubbles: true }));
                } catch (error) {
                    feedback.textContent = error.message || 'Błąd połączenia. Możesz ponowić przesyłanie.';
                } finally {
                    locked = false;
                    if (submit) submit.disabled = false;
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const createForm = document.getElementById('order-create-form');
        if (createForm) {
            initializePicker({
                input: document.getElementById('order-create-photo-files'),
                button: document.getElementById('order-create-add-photo'),
                preview: document.getElementById('order-create-photo-preview'),
                feedback: document.getElementById('order-create-photo-feedback'),
                form: createForm,
                createMode: true,
                tokenInput: document.getElementById('order-photo-draft-token'),
            });
        }
        const editForm = document.getElementById('order-edit-photo-upload-form');
        if (editForm) initializePicker({
            input: document.getElementById('order-edit-photo-files'),
            button: document.getElementById('order-edit-add-photo'),
            preview: document.getElementById('order-edit-photo-preview'),
            feedback: document.getElementById('order-edit-photo-feedback'),
            form: editForm,
            createMode: false,
        });

        const pending = document.getElementById('pending-order-photo-upload');
        if (!pending) return;
        const retry = pending.querySelector('[data-retry-photo-upload]');
        const reload = pending.querySelector('[data-reload-photo-upload]');
        const status = pending.querySelector('[data-photo-upload-status]');
        const token = pending.dataset.token;
        const orderUploadForm = document.getElementById('order-photos-upload-form');
        const filesInput = orderUploadForm?.querySelector('input[type="file"][name="files"]');
        let uploadPromise = null;

        function uploadPending() {
            if (uploadPromise) return uploadPromise;
            uploadPromise = (async () => {
                if (retry) retry.disabled = true;
                try {
                    const draft = await draftRequest('get', token);
                    if (!draft?.files?.length) {
                        status.textContent = 'Nie znaleziono oczekujących zdjęć w tej przeglądarce.';
                        document.dispatchEvent(new CustomEvent('order-photos:pending-failed'));
                        return false;
                    }
                    const data = new FormData(orderUploadForm);
                    draft.files.forEach((file) => data.append('files', file, file.name));
                    status.textContent = `Przesyłanie ${draft.files.length} zdjęć do zlecenia…`;
                    const response = await fetch(orderUploadForm.action, { method: 'POST', body: data, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                    let result;
                    try {
                        if (response.redirected || !(response.headers.get('content-type') || '').includes('application/json')) throw new Error('invalid upload response');
                        result = await response.json();
                    } catch {
                        const reloadRequired = response.redirected || !(response.headers.get('content-type') || '').includes('application/json') || response.status === 400 || response.status === 403;
                        const error = new Error(reloadRequired
                            ? 'Sesja lub token CSRF wygasł. Odśwież stronę i ponów upload.'
                            : 'Serwer zwrócił nieprawidłową odpowiedź.');
                        error.requiresReload = reloadRequired;
                        throw error;
                    }
                    if (!response.ok || !result.ok) throw new Error(result.message || 'Zlecenie zapisano, ale nie udało się przesłać zdjęć.');
                    await draftRequest('delete', token);
                    status.textContent = 'Zdjęcia przypisano do zapisanego zlecenia.';
                    pending.dataset.complete = 'true';
                    const printPrompt = document.getElementById('print-intake-prompt');
                    if (printPrompt) {
                        printPrompt.dataset.photosPending = 'false';
                        const printWithPhotos = printPrompt.querySelector('[data-print-intake-action="print-photos"]');
                        if (printWithPhotos) printWithPhotos.disabled = false;
                    }
                    const completedUrl = new URL(window.location.href);
                    completedUrl.searchParams.delete('pending_photo_token');
                    window.history?.replaceState({}, '', completedUrl);
                    if (filesInput) filesInput.value = '';
                    pending.dispatchEvent(new CustomEvent('order-photos:uploaded', { bubbles: true }));
                    document.dispatchEvent(new CustomEvent('order-photos:pending-complete'));
                    return true;
                } catch (error) {
                    status.textContent = 'Zlecenie zapisano. ' + (error.message || 'Zdjęcia oczekują na ponowienie.');
                    if (retry) retry.hidden = false;
                    if (reload && error.requiresReload) reload.hidden = false;
                    document.dispatchEvent(new CustomEvent('order-photos:pending-failed'));
                    return false;
                } finally {
                    if (retry) retry.disabled = false;
                }
            })();
            return uploadPromise.finally(() => { uploadPromise = null; });
        }
        window.retryPendingOrderPhotoUpload = uploadPending;
        retry?.addEventListener('click', uploadPending);
        void uploadPending();
    });
})();