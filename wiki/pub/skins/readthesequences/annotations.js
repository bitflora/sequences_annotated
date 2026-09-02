(function () {
    'use strict';

    function getAnnotationPath() {
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
        name = name.replace(/\.html$/, '');
        return 'annotations/' + name + '.json';
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
    function injectMarker(wikitext, quote, id) {
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
        a.href = '#annotation-' + id;
        a.id = 'annotation-ref-' + id;
        a.textContent = '[A' + id + ']';
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

    function buildNote(ann) {
        var el = document.createElement('aside');
        el.className = 'margin-note ' + (ann.side || 'right');
        el.id = 'annotation-' + ann.id;
        el.innerHTML = '<span class="margin-note-number">[A' + ann.id + ']</span> ' + ann.content;
        return el;
    }

    function render(annotations) {
        var wikitext = document.getElementById('wikitext');
        if (!wikitext) return;

        // Inject inline markers from quotes
        annotations.forEach(function (ann) {
            if (ann.quote) injectMarker(wikitext, ann.quote, ann.id);
        });

        var wikitextTop = wikitext.getBoundingClientRect().top + window.scrollY;
        var pendingNotes = [];

        annotations.forEach(function (ann) {
            var ref = document.getElementById('annotation-ref-' + ann.id);
            if (!ref) return;

            var note = buildNote(ann);
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

    function init() {
        var path = getAnnotationPath();
        fetch(path)
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) { if (data && data.length) render(data); })
            .catch(function () {});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
