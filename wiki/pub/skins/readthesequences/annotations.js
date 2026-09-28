(function () {
    'use strict';

    var PREF_KEY = 'seq-annotation-sets';

    function getArticleName() {
        // Prefer the canonical filename: some articles are reachable under an
        // alias URL (e.g. Evaporative-Cooling-Of-Group-Beliefs.html) that points
        // via <link rel="canonical"> at the real page. Annotation JSON is keyed
        // to the canonical name, so resolve from there when available.
        var name;
        var canonical = document.querySelector('link[rel="canonical"]');
        if (canonical && canonical.getAttribute('href')) {
            name = canonical.getAttribute('href').split('/').pop();
        } else {
            name = window.location.pathname.split('/').pop() || 'index.html';
        }
        return name.replace(/\.html$/, '');
    }

    // Superseded sets; stored choices for them are dropped once so they fall
    // back to their index default (off).
    var OLD_SET_IDS = ['OpusOld', 'ropusOld'];
    var OLD_SETS_RESET_FLAG = '_oldSetsReset2';

    function loadPrefs() {
        var prefs;
        try {
            prefs = JSON.parse(window.localStorage.getItem(PREF_KEY)) || {};
        } catch (e) {
            return {};
        }
        if (!prefs[OLD_SETS_RESET_FLAG]) {
            OLD_SET_IDS.forEach(function (id) { delete prefs[id]; });
            prefs[OLD_SETS_RESET_FLAG] = true;
            savePrefs(prefs);
        }
        return prefs;
    }

    function savePrefs(prefs) {
        try {
            window.localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
        } catch (e) {
            // ignore (private browsing / storage disabled)
        }
    }

    function isEnabled(set, prefs) {
        return Object.prototype.hasOwnProperty.call(prefs, set.id) ? !!prefs[set.id] : !!set.default;
    }

    // Build a map of all text nodes within root, concatenated into one string.
    function buildTextMap(root) {
        var nodes = [];
        var offsets = [];
        var combined = '';
        var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                var tag = node.parentElement && node.parentElement.tagName;
                return (tag === 'SCRIPT' || tag === 'STYLE')
                    ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            }
        });
        var node;
        while ((node = walker.nextNode())) {
            offsets.push(combined.length);
            combined += node.textContent;
            nodes.push(node);
        }
        return { nodes: nodes, offsets: offsets, combined: combined };
    }

    function lastIndexNotExceeding(offsets, limit) {
        var result = 0;
        for (var i = offsets.length - 1; i >= 0; i--) {
            if (offsets[i] <= limit) { result = i; break; }
        }
        return result;
    }

    // Find quote in DOM, wrap it in span.annotation-target, insert sup ref after it.
    // Returns the injected <a> element (used for positioning), or null if not found.
    function injectMarker(wikitext, quote, elId, label) {
        var map = buildTextMap(wikitext);
        var idx = map.combined.indexOf(quote);
        if (idx === -1) return null;

        var endIdx = idx + quote.length;
        var startNodeIdx = lastIndexNotExceeding(map.offsets, idx);
        var endNodeIdx = lastIndexNotExceeding(map.offsets, endIdx - 1);

        var range = document.createRange();
        range.setStart(map.nodes[startNodeIdx], idx - map.offsets[startNodeIdx]);
        range.setEnd(map.nodes[endNodeIdx], endIdx - map.offsets[endNodeIdx]);

        var contents = range.extractContents();
        var span = document.createElement('span');
        span.className = 'annotation-target';
        span.dataset.note = elId;
        span.appendChild(contents);
        range.insertNode(span);

        var a = document.createElement('a');
        a.href = '#' + elId;
        a.id = elId + '-ref';
        a.textContent = '[' + label + ']';
        var sup = document.createElement('sup');
        sup.className = 'annotation-ref';
        sup.appendChild(a);
        span.after(sup);

        return a;
    }

    function placeNotes(notes) {
        notes.sort(function (a, b) { return a.top - b.top; });
        var floorLeft = 0;
        var floorRight = 0;
        notes.forEach(function (note) {
            var top = note.top;
            if (note.el.classList.contains('left')) {
                if (top < floorLeft) top = floorLeft;
                floorLeft = top + note.el.offsetHeight + 12;
            } else {
                if (top < floorRight) top = floorRight;
                floorRight = top + note.el.offsetHeight + 12;
            }
            note.el.style.top = top + 'px';
        });
        return Math.max(floorLeft, floorRight);
    }

    function buildNote(ann, elId, label) {
        var el = document.createElement('aside');
        el.className = 'margin-note ' + (ann.side || 'right');
        el.id = elId;
        el.innerHTML = '<span class="margin-note-number">[' + label + ']</span> ' + ann.content;
        return el;
    }

    // Remove any previously injected markers/notes so a toggle can re-render cleanly.
    function clear(wikitext) {
        closeSheet();
        wikitext.style.minHeight = '';
        wikitext.querySelectorAll('.margin-note').forEach(function (el) { el.remove(); });
        wikitext.querySelectorAll('.annotation-ref').forEach(function (el) { el.remove(); });
        wikitext.querySelectorAll('.annotation-target').forEach(function (span) {
            var parent = span.parentNode;
            while (span.firstChild) parent.insertBefore(span.firstChild, span);
            parent.removeChild(span);
        });
        wikitext.normalize();
    }

    // Narrow screens: margin notes are hidden, so a tap on annotated text or
    // its marker opens the note(s) in a sheet fixed to the bottom of the screen.
    var NARROW = window.matchMedia('(max-width: 1000px)');
    var sheet = null;
    var sheetIndex = -1;  // index into refList() of the group now shown

    function refList() {
        var wikitext = document.getElementById('wikitext');
        return wikitext ? Array.prototype.slice.call(wikitext.querySelectorAll('sup.annotation-ref a')) : [];
    }

    // The annotation-target spans sharing a passage with span: itself, the
    // targets it sits inside, and those inside it (shared quotes nest).
    function groupSpans(span) {
        var spans = [span];
        for (var p = span.parentElement; p; p = p.parentElement) {
            if (p.classList.contains('annotation-target')) spans.unshift(p);
        }
        span.querySelectorAll('.annotation-target').forEach(function (s) { spans.push(s); });
        return spans;
    }

    function spanForRef(a) {
        var sup = a.parentElement;
        var span = sup && sup.previousElementSibling;
        return span && span.classList.contains('annotation-target') ? span : null;
    }

    function buildSheet() {
        sheet = document.createElement('div');
        sheet.className = 'annotation-sheet';
        sheet.hidden = true;
        sheet.innerHTML =
            '<div class="annotation-sheet-bar">' +
            '<button type="button" class="annotation-sheet-prev" aria-label="Previous note">‹</button>' +
            '<span class="annotation-sheet-pos"></span>' +
            '<button type="button" class="annotation-sheet-next" aria-label="Next note">›</button>' +
            '<button type="button" class="annotation-sheet-close" aria-label="Close">×</button>' +
            '</div>' +
            '<div class="annotation-sheet-body"></div>';
        sheet.querySelector('.annotation-sheet-prev').addEventListener('click', function () { step(-1); });
        sheet.querySelector('.annotation-sheet-next').addEventListener('click', function () { step(1); });
        sheet.querySelector('.annotation-sheet-close').addEventListener('click', closeSheet);
        document.body.appendChild(sheet);
    }

    function openGroup(spans, scroll) {
        if (!sheet) buildSheet();
        document.querySelectorAll('.annotation-active').forEach(function (el) {
            el.classList.remove('annotation-active');
        });

        var body = sheet.querySelector('.annotation-sheet-body');
        body.innerHTML = '';
        spans.forEach(function (span) {
            span.classList.add('annotation-active');
            var note = document.getElementById(span.dataset.note);
            if (!note) return;
            var div = document.createElement('div');
            div.className = 'annotation-sheet-note';
            div.innerHTML = note.innerHTML;
            body.appendChild(div);
        });

        var refs = refList();
        var ids = spans.map(function (s) { return s.dataset.note + '-ref'; });
        sheetIndex = -1;
        refs.forEach(function (a, i) {
            if (sheetIndex === -1 && ids.indexOf(a.id) !== -1) sheetIndex = i;
        });
        sheet.querySelector('.annotation-sheet-pos').textContent = (sheetIndex + 1) + ' / ' + refs.length;
        sheet.querySelector('.annotation-sheet-prev').disabled = sheetIndex <= 0;
        var last = -1;
        refs.forEach(function (a, i) { if (ids.indexOf(a.id) !== -1) last = i; });
        sheet.querySelector('.annotation-sheet-next').disabled = last >= refs.length - 1;

        sheet.hidden = false;
        body.scrollTop = 0;
        document.body.classList.add('annotation-sheet-open');

        if (scroll) {
            var top = spans[0].getBoundingClientRect().top + window.scrollY;
            window.scrollTo({ top: Math.max(0, top - window.innerHeight * 0.15), behavior: 'smooth' });
        }
    }

    // Move to the previous/next group of notes in document order.
    function step(dir) {
        var refs = refList();
        var current = document.querySelectorAll('.annotation-active');
        var ids = Array.prototype.map.call(current, function (s) { return s.dataset.note + '-ref'; });
        var i = sheetIndex;
        do { i += dir; } while (i >= 0 && i < refs.length && ids.indexOf(refs[i].id) !== -1);
        if (i < 0 || i >= refs.length) return;
        var span = spanForRef(refs[i]);
        if (span) openGroup(groupSpans(span), true);
    }

    function closeSheet() {
        if (sheet) sheet.hidden = true;
        sheetIndex = -1;
        document.body.classList.remove('annotation-sheet-open');
        document.querySelectorAll('.annotation-active').forEach(function (el) {
            el.classList.remove('annotation-active');
        });
    }

    function onWikitextClick(e) {
        if (!NARROW.matches) return;
        var ref = e.target.closest('sup.annotation-ref a');
        var span;
        if (ref) {
            e.preventDefault();
            span = spanForRef(ref);
        } else if (!e.target.closest('a')) {
            span = e.target.closest('.annotation-target');
        }
        if (span) openGroup(groupSpans(span), false);
    }

    function initSheet() {
        var wikitext = document.getElementById('wikitext');
        if (!wikitext) return;
        wikitext.addEventListener('click', onWikitextClick);
        document.addEventListener('click', function (e) {
            if (!sheet || sheet.hidden) return;
            if (e.target.closest('.annotation-sheet, .annotation-target, .annotation-ref')) return;
            closeSheet();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeSheet();
        });
        NARROW.addEventListener('change', function () { if (!NARROW.matches) closeSheet(); });
    }

    function render(annotations) {
        var wikitext = document.getElementById('wikitext');
        if (!wikitext) return;

        clear(wikitext);

        annotations.forEach(function (ann, i) {
            ann._elId = 'annotation-' + ann._setId + '-' + ann.id;
            ann._label = ann._setCode + ann.id;
        });

        // Inject inline markers from quotes
        annotations.forEach(function (ann) {
            if (ann.quote) injectMarker(wikitext, ann.quote, ann._elId, ann._label);
        });

        var wikitextTop = wikitext.getBoundingClientRect().top + window.scrollY;
        var pendingNotes = [];

        annotations.forEach(function (ann) {
            var ref = document.getElementById(ann._elId + '-ref');
            if (!ref) return;

            var note = buildNote(ann, ann._elId, ann._label);
            note.style.visibility = 'hidden';
            note.style.top = '0px';
            wikitext.appendChild(note);

            var refTop = ref.getBoundingClientRect().top + window.scrollY - wikitextTop;
            pendingNotes.push({ el: note, top: refTop });
        });

        pendingNotes.forEach(function (n) { void n.el.offsetHeight; });
        // Grow #wikitext to hold notes that run past the article's end
        var notesBottom = placeNotes(pendingNotes);
        if (notesBottom > 0) wikitext.style.minHeight = (notesBottom + 80) + 'px';
        pendingNotes.forEach(function (n) { n.el.style.visibility = ''; });
    }

    var jsonCache = {};
    function fetchJson(path) {
        if (!jsonCache[path]) {
            jsonCache[path] = fetch(path).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
        }
        return jsonCache[path];
    }

    function loadAndRender(sets, prefs) {
        var enabled = sets.filter(function (s) { return isEnabled(s, prefs); });
        if (!enabled.length) {
            var wikitext = document.getElementById('wikitext');
            if (wikitext) clear(wikitext);
            return;
        }
        Promise.all(enabled.map(function (s) { return fetchJson(s.file); })).then(function (results) {
            var merged = [];
            results.forEach(function (list, i) {
                if (!list) return;
                list.forEach(function (ann) {
                    ann._setId = enabled[i].id;
                    ann._setCode = enabled[i].code || enabled[i].id.charAt(0).toUpperCase();
                    merged.push(ann);
                });
            });
            if (merged.length) render(merged);
        });
    }

    function buildToggleUi(sets, prefs, onChange) {
        var panel = document.createElement('div');
        panel.className = 'annotation-toggle-panel';

        var summary = document.createElement('button');
        summary.type = 'button';
        summary.className = 'annotation-toggle-summary';
        summary.textContent = 'Annotations ▾';
        panel.appendChild(summary);

        var body = document.createElement('div');
        body.className = 'annotation-toggle-body';
        body.hidden = true;

        sets.forEach(function (s) {
            var row = document.createElement('label');
            row.className = 'annotation-toggle-row';

            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = isEnabled(s, prefs);
            cb.addEventListener('change', function () {
                prefs[s.id] = cb.checked;
                savePrefs(prefs);
                onChange();
            });

            var count = document.createElement('span');
            count.className = 'annotation-toggle-count';
            fetchJson(s.file).then(function (list) {
                if (list) count.textContent = list.length;
            });

            row.appendChild(cb);
            row.appendChild(document.createTextNode(' ' + s.label));
            row.appendChild(count);
            body.appendChild(row);
        });

        panel.appendChild(body);
        summary.addEventListener('click', function () {
            body.hidden = !body.hidden;
        });

        document.body.appendChild(panel);
    }

    function initWithIndex(sets) {
        var prefs = loadPrefs();
        loadAndRender(sets, prefs);
        if (sets.length) {
            buildToggleUi(sets, prefs, function () { loadAndRender(sets, prefs); });
        }
    }

    // Legacy fallback: a single un-indexed annotations/<name>.json, always on, no toggle.
    function initLegacy(name) {
        fetchJson('annotations/' + name + '.json').then(function (data) {
            if (!data || !data.length) return;
            data.forEach(function (ann) {
                ann._setId = 'default';
                ann._setCode = 'O';
            });
            render(data);
        });
    }

    // Cited-study bar under the article title, written by scripts/build_findings.py.
    // It goes inside the <h1> so the skin's h1 + p rules still apply, and notes
    // are placed only after it lands, since it changes the height above them.
    function addTitleBar(name) {
        return fetchJson('analysis/article-studies.json').then(function (bars) {
            var h1 = document.querySelector('#wikitext h1');
            if (!bars || !bars[name] || !h1 || h1.querySelector('.article-studies')) return;
            h1.insertAdjacentHTML('beforeend', bars[name]);
        });
    }

    function init() {
        var name = getArticleName();
        var barReady = addTitleBar(name);
        initSheet();
        Promise.all([fetchJson('annotations/' + name + '.index.json'), barReady]).then(function (r) {
            var sets = r[0];
            if (sets && sets.length) {
                initWithIndex(sets);
            } else {
                initLegacy(name);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
