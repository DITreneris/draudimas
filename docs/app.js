(function () {
  'use strict';

  var DATA_URL = 'items.json';
  var REFRESH_MS = 60 * 1000;

  var els = {
    tbody: document.querySelector('#items tbody'),
    empty: document.getElementById('empty'),
    search: document.getElementById('search'),
    keywordFilter: document.getElementById('keyword-filter'),
    autoRefresh: document.getElementById('auto-refresh'),
    refreshBtn: document.getElementById('refresh-btn'),
    metaGenerated: document.getElementById('meta-generated'),
    metaTotal: document.getElementById('meta-total'),
    metaKeywords: document.getElementById('meta-keywords'),
    status: document.getElementById('status'),
    footDigest: document.getElementById('foot-digest')
  };

  var state = {
    items: [],
    generatedAt: null,
    keywords: [],
    timer: null
  };

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatUtc(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()) +
      ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  }

  function relativeTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var diffMs = Date.now() - d.getTime();
    var mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'ka tik';
    if (mins < 60) return 'pries ' + mins + ' min';
    var hrs = Math.round(mins / 60);
    if (hrs < 48) return 'pries ' + hrs + ' val';
    var days = Math.round(hrs / 24);
    return 'pries ' + days + ' d';
  }

  function render() {
    var q = (els.search.value || '').toLowerCase().trim();
    var kwFilter = els.keywordFilter.value;

    var filtered = state.items.filter(function (it) {
      if (kwFilter && it.keyword_first_seen !== kwFilter) return false;
      if (!q) return true;
      var hay = [it.title || '', it.pirkimo_id || ''].join(' ').toLowerCase();
      return hay.indexOf(q) !== -1;
    });

    if (filtered.length === 0) {
      els.tbody.innerHTML = '';
      els.empty.hidden = false;
    } else {
      els.empty.hidden = true;
      var html = filtered.map(function (it) {
        var title = escapeHtml(it.title || '(be pavadinimo)');
        var titleHtml = it.url
          ? '<a href="' + escapeHtml(it.url) + '" target="_blank" rel="noopener noreferrer">' + title + '</a>'
          : title;
        return '<tr>' +
          '<td class="pid">' + escapeHtml(it.pirkimo_id || '') + '</td>' +
          '<td>' + titleHtml + '</td>' +
          '<td><span class="kw">' + escapeHtml(it.keyword_first_seen || '') + '</span></td>' +
          '<td class="date">' + escapeHtml(it.published_at || '') + '</td>' +
          '<td class="date">' + escapeHtml(formatUtc(it.first_seen_at)) + '</td>' +
          '</tr>';
      }).join('');
      els.tbody.innerHTML = html;
    }

    els.metaTotal.textContent = 'Rodomi: ' + filtered.length + ' / Viso: ' + state.items.length;
  }

  function rebuildKeywordOptions() {
    var existing = new Set();
    state.items.forEach(function (it) {
      if (it.keyword_first_seen) existing.add(it.keyword_first_seen);
    });
    var current = els.keywordFilter.value;
    els.keywordFilter.innerHTML = '<option value="">Visi raktazodziai</option>' +
      Array.from(existing).sort().map(function (kw) {
        return '<option value="' + escapeHtml(kw) + '">' + escapeHtml(kw) + '</option>';
      }).join('');
    if (current && existing.has(current)) els.keywordFilter.value = current;
  }

  function setStatus(msg, isError) {
    els.status.textContent = msg || '';
    els.status.classList.toggle('error', !!isError);
  }

  function load() {
    setStatus('Kraunama...', false);
    var url = DATA_URL + '?t=' + Date.now();
    fetch(url, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state.items = Array.isArray(data.items) ? data.items : [];
        state.generatedAt = data.generated_at || null;
        state.keywords = (data.stats && data.stats.keywords) || [];

        els.metaGenerated.textContent = state.generatedAt
          ? 'Atnaujinta: ' + formatUtc(state.generatedAt) + ' UTC (' + relativeTime(state.generatedAt) + ')'
          : 'Atnaujinta: -';
        els.metaKeywords.textContent = state.keywords.length
          ? 'Stebimi: ' + state.keywords.join(', ')
          : '';
        els.footDigest.textContent = 'items.json | ' + state.items.length + ' irasu';

        rebuildKeywordOptions();
        render();
        setStatus('', false);
      })
      .catch(function (err) {
        setStatus('Nepavyko uzkrauti items.json: ' + err.message, true);
      });
  }

  function scheduleAutoRefresh() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    if (els.autoRefresh.checked) {
      state.timer = setInterval(load, REFRESH_MS);
    }
  }

  els.search.addEventListener('input', render);
  els.keywordFilter.addEventListener('change', render);
  els.refreshBtn.addEventListener('click', load);
  els.autoRefresh.addEventListener('change', scheduleAutoRefresh);

  load();
  scheduleAutoRefresh();
})();
