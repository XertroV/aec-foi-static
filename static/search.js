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
      ul.appendChild(li);
    });
    searchResults.appendChild(ul);
  }

  if (searchInput) {
    searchInput.addEventListener('input', function (e) {
      const query = e.target.value.trim();
      if (!idx || !query) {
        searchResults.innerHTML = '';
        return;
      }
      const results = idx.search(query);
      renderResults(results);
    });
  }
});
