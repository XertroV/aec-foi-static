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

  function generateSnippet(body, matchData) {
    let earliestMatchPos = null;
    let allHighlightedRanges = [];
    // Find all match positions in body
    for (const term in matchData.metadata) {
      const meta = matchData.metadata[term];
      if (meta && meta.body && meta.body.position) {
        for (const pos of meta.body.position) {
          if (!earliestMatchPos || pos[0] < earliestMatchPos[0]) {
            earliestMatchPos = pos;
          }
          allHighlightedRanges.push({ start: pos[0], end: pos[0] + pos[1] });
        }
      }
    }
    let matchCount = allHighlightedRanges.length;
    if (!earliestMatchPos) {
      // fallback: try to find the first occurrence of any matched term in the body
      const matchedTerms = Object.keys(matchData.metadata).filter(Boolean);
      let firstIdx = -1;
      let firstTerm = '';
      for (const term of matchedTerms) {
        const idx = body.toLowerCase().indexOf(term.toLowerCase());
        if (idx !== -1 && (firstIdx === -1 || idx < firstIdx)) {
          firstIdx = idx;
          firstTerm = term;
        }
      }
      let snippet = '';
      if (firstIdx !== -1) {
        const contextWindow = 70;
        const snippetStart = Math.max(0, firstIdx - contextWindow);
        const snippetEnd = Math.min(body.length, firstIdx + firstTerm.length + contextWindow);
        snippet = body.substring(snippetStart, snippetEnd);
        const prefix = snippetStart > 0 ? '...' : '';
        const suffix = snippetEnd < body.length ? '...' : '';
        snippet = prefix + highlightTermsInSnippet(snippet, matchedTerms) + suffix;
      } else {
        snippet = body.slice(0, 140) + (body.length > 140 ? '...' : '');
        snippet = highlightTermsInSnippet(snippet, matchedTerms);
      }
      if (matchCount > 1) {
        snippet += ` <span class="search-match-count">and ${matchCount - 1} other match${matchCount - 1 === 1 ? '' : 'es'}</span>`;
      }
      return snippet;
    }
    const contextWindow = 70;
    const snippetStart = Math.max(0, earliestMatchPos[0] - contextWindow);
    const snippetEnd = Math.min(body.length, earliestMatchPos[0] + earliestMatchPos[1] + contextWindow);
    const snippetText = body.substring(snippetStart, snippetEnd);
    const prefix = snippetStart > 0 ? '...' : '';
    const suffix = snippetEnd < body.length ? '...' : '';
    // Only highlight matches that intersect with the snippet
    const relevantHighlights = allHighlightedRanges
      .filter(r => r.end > snippetStart && r.start < snippetEnd)
      .map(r => ({ start: Math.max(0, r.start - snippetStart), end: Math.min(snippetText.length, r.end - snippetStart) }))
      .sort((a, b) => a.start - b.start);
    // Build snippet with <strong> tags
    let finalSnippetHtml = '';
    let lastIndex = 0;
    for (const range of relevantHighlights) {
      if (range.start > lastIndex) {
        finalSnippetHtml += snippetText.substring(lastIndex, range.start);
      }
      finalSnippetHtml += '<strong>' + snippetText.substring(range.start, range.end) + '</strong>';
      lastIndex = range.end;
    }
    finalSnippetHtml += snippetText.substring(lastIndex);
    // Also highlight any other matched terms in the snippet (for partial/fallback matches)
    const matchedTerms = Object.keys(matchData.metadata);
    finalSnippetHtml = highlightTermsInSnippet(finalSnippetHtml, matchedTerms);
    let matchCountHtml = '';
    if (matchCount > 1) {
      matchCountHtml = ` <span class="search-match-count">and ${matchCount - 1} other match${matchCount - 1 === 1 ? '' : 'es'}</span>`;
    }
    return prefix + finalSnippetHtml + suffix + matchCountHtml;
  }

  // Helper to highlight all matched terms in a snippet (case-insensitive, avoids double-highlighting)
  function highlightTermsInSnippet(snippet, terms) {
    terms.forEach(term => {
      if (!term) return;
      // Only highlight if not already inside <strong>
      const re = new RegExp('(?<!<strong>)(' + term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')(?![^<]*<\/strong>)', 'gi');
      snippet = snippet.replace(re, '<strong>$1</strong>');
    });
    return snippet;
  }

  function renderResults(results) {
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
      const snippet = generateSnippet(doc.body, result.matchData);
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
      // For true partial matching, add trailing wildcard to every part
      const queryParts = query.split(/\s+/).filter(Boolean).map(part => part.toLowerCase());
      let results = idx.query(function (q) {
        queryParts.forEach(function (part) {
          if (!part) return;
          q.term(part, { wildcard: lunr.Query.wildcard.TRAILING });
        });
      });
      renderResults(results);
    });
  }
});
