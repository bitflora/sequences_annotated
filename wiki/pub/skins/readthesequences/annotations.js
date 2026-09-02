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

    function loadPrefs() {
        try {
            return JSON.parse(window.localStorage.getItem(PREF_KEY)) || {};
        } catch (e) {
            return {};
        }
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
        wikitext.querySelectorAll('.margin-note').forEach(function (el) { el.remove(); });
        wikitext.querySelectorAll('.annotation-target').forEach(function (span) {
            var parent = span.parentNode;
            while (span.firstChild) parent.insertBefore(span.firstChild, span);
            parent.removeChild(span);
        });
        wikitext.normalize();
    }

    function render(annotations, multiSet) {
        var wikitext = document.getElementById('wikitext');
        if (!wikitext) return;

        clear(wikitext);

        annotations.forEach(function (ann, i) {
            ann._elId = 'annotation-' + ann._setId + '-' + ann.id;
            ann._label = multiSet ? (ann._setCode + ann.id) : ('A' + ann.id);
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
        placeNotes(pendingNotes);
        pendingNotes.forEach(function (n) { n.el.style.visibility = ''; });
    }

    function fetchJson(path) {
        return fetch(path).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
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
            if (merged.length) render(merged, enabled.length > 1);
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

            row.appendChild(cb);
            row.appendChild(document.createTextNode(' ' + s.label));
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
                ann._setCode = 'A';
            });
            render(data, false);
        });
    }

    function init() {
        var name = getArticleName();
        fetchJson('annotations/' + name + '.index.json').then(function (sets) {
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
