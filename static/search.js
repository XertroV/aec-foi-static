// search.js: Lunr.js client-side search for AEC FOI Archive

document.addEventListener('DOMContentLoaded', function () {
  const searchInput = document.getElementById('search-input');
  const searchResults = document.getElementById('search-results');
  let idx = null;
  let documents = [];
  let docMap = {};

  fetch('/search_index.json')
    .then(response => response.json())
    .then(data => {
      documents = data;
      docMap = {};
      documents.forEach(doc => { docMap[doc.id] = doc; });
      idx = lunr(function () {
        this.ref('id');
        this.field('title');
        this.field('body');
        documents.forEach(function (doc) {
          this.add(doc);
        }, this);
      });
    })
    .catch(err => {
      console.error('Failed to load search index:', err);
    });

  function generateSnippet(body, matchData, queryTerms) {
    // Find first match position in body
    let firstPos = null;
    let firstTerm = null;
    for (const term of queryTerms) {
      const meta = matchData.metadata[term];
      if (meta && meta.body && meta.body.position && meta.body.position.length > 0) {
        const [start, len] = meta.body.position[0];
        if (firstPos === null || start < firstPos) {
          firstPos = start;
          firstTerm = term;
        }
      }
    }
    if (firstPos === null) {
      // fallback: show start of body
      return body.slice(0, 140) + (body.length > 140 ? '...' : '');
    }
    const context = 70;
    const startIdx = Math.max(0, firstPos - context);
    const endIdx = Math.min(body.length, firstPos + context);
    let snippet = body.slice(startIdx, endIdx);
    // Highlight all query terms (case-insensitive)
    queryTerms.forEach(term => {
      if (!term) return;
      const re = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      snippet = snippet.replace(re, match => `<strong>${match}</strong>`);
    });
    if (startIdx > 0) snippet = '...' + snippet;
    if (endIdx < body.length) snippet = snippet + '...';
    return snippet;
  }

  function renderResults(results, queryTerms) {
    searchResults.innerHTML = '';
    if (results.length === 0) {
      searchResults.innerHTML = '<div class="no-results">No results found.</div>';
      return;
    }
    const ul = document.createElement('ul');
    ul.className = 'search-results-list';
    results.forEach(result => {
      const doc = docMap[result.ref];
      if (!doc) return;
      const li = document.createElement('li');
      li.className = 'search-result-item';
      li.innerHTML = `<a href="${doc.url}"><strong>${doc.title}</strong></a>`;
      // Add contextual snippet
      const snippet = generateSnippet(doc.body, result.matchData, queryTerms);
      const snippetP = document.createElement('p');
      snippetP.className = 'search-snippet';
      snippetP.innerHTML = snippet;
      li.appendChild(snippetP);
      ul.appendChild(li);
    });
    searchResults.appendChild(ul);
  }

  if (searchInput) {
    searchInput.addEventListener('input', function (e) {
      let query = e.target.value.trim();
      if (!idx || !query) {
        searchResults.innerHTML = '';
        return;
      }
      // Partial matching: add wildcard to last word
      const words = query.split(/\s+/);
      if (words.length > 0 && words[words.length - 1]) {
        words[words.length - 1] = words[words.length - 1] + '*';
      }
      const lunrQuery = words.join(' ');
      const results = idx.search(lunrQuery);
      // Pass original query terms (lowercased, no wildcards)
      const queryTerms = e.target.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      renderResults(results, queryTerms);
    });
  }
});
