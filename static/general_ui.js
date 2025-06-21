// General UI logic for persona switching, summary popovers, and tabbed file views
(function() {
  // --- Data Fetching and Initialization ---
  let currentPageData = null;
  let allDocumentsData = null;
  let isDetailPage = false;
  let isIndexPage = false;
  const personaSelector = document.getElementById('persona-selector');
  const personaStorageKey = 'aec_foi_selected_persona';
  let selectedPersona = localStorage.getItem(personaStorageKey) || (window.DEFAULT_PERSONA || 'balanced');

  // Parse JSON data embedded in the page
  function loadPageData() {
    const detailScript = document.getElementById('current-foi-data');
    const indexScript = document.getElementById('documents-data');
    if (detailScript) {
      try {
        currentPageData = JSON.parse(detailScript.textContent);
        isDetailPage = true;
      } catch (e) { console.error('Failed to parse current-foi-data:', e); }
    }
    if (indexScript) {
      try {
        allDocumentsData = JSON.parse(indexScript.textContent);
        isIndexPage = true;
      } catch (e) { console.error('Failed to parse documents-data:', e); }
    }
  }

  // --- Persona Switching Logic ---
  function updateSummaries(personaId) {
    localStorage.setItem(personaStorageKey, personaId);
    if (personaSelector) personaSelector.value = personaId;
    // Detail Page
    if (isDetailPage && currentPageData) {
      // Overall summary
      const overallBlock = document.querySelector('.overall-ai-summary');
      if (overallBlock) {
        const personaData = currentPageData.ai_summaries[personaId] || {};
        const overall = personaData.overall || {};
        const summaryDiv = overallBlock.querySelector('.ai-summary-markdown-content');
        const label = overallBlock.querySelector('.ai-summary-label');
        if (overall.text && overall.text !== '') {
          summaryDiv.innerHTML = window.marked ? window.marked.parse(overall.text) : overall.text;
          if (label) {
            label.setAttribute('data-summary-model', overall.model || '');
            label.setAttribute('data-summary-date', overall.generated_at || '');
          }
          overallBlock.style.display = '';
        } else {
          overallBlock.style.display = 'none';
        }
      }
      // Per-file summaries in tabs
      document.querySelectorAll('.tab-content[data-persona-id]').forEach(tab => {
        const fileId = tab.getAttribute('id');
        const personaData = findPersonaDataForTab(currentPageData, fileId, personaId);
        const label = tab.querySelector('.ai-summary-label');
        if (personaData && personaData.text && personaData.text !== '') {
          tab.querySelector('.ai-summary-markdown-content').innerHTML = window.marked ? window.marked.parse(personaData.text) : personaData.text;
          if (label) {
            label.setAttribute('data-summary-model', personaData.model || '');
            label.setAttribute('data-summary-date', personaData.generated_at || '');
          }
          tab.style.display = '';
          // Show tab button
          const tabBtn = document.querySelector(`[onclick*="${fileId}"]`);
          if (tabBtn) tabBtn.style.display = '';
        } else {
          tab.style.display = 'none';
          // Hide tab button
          const tabBtn = document.querySelector(`[onclick*="${fileId}"]`);
          if (tabBtn) tabBtn.style.display = 'none';
        }
      });
      // Re-initialize AI summary toggle
      initAiSummaryToggle();
    }
    // Index Page
    if (isIndexPage && allDocumentsData) {
      document.querySelectorAll('li.document-item').forEach(item => {
        const docId = item.getAttribute('data-doc-id');
        const doc = allDocumentsData.find(d => d.id === docId);
        const block = item.querySelector('.ai-summary-block');
        if (!block || !doc) return;
        const personaData = doc.ai_summaries[personaId] || {};
        const shortIndex = personaData.short_index || {};
        const label = block.querySelector('.ai-summary-label');
        if (shortIndex.text && shortIndex.text !== '') {
          block.querySelector('.ai-summary-text').innerHTML = window.marked ? window.marked.parse(shortIndex.text) : shortIndex.text;
          if (label) {
            label.setAttribute('data-summary-model', shortIndex.model || '');
            label.setAttribute('data-summary-date', shortIndex.generated_at || '');
          }
          block.style.display = '';
        } else {
          block.style.display = 'none';
        }
      });
    }
    // Re-attach popover listeners
    attachPopoverHandlers();
  }

  // Helper: Find persona data for a tab by id
  function findPersonaDataForTab(requestData, tabId, personaId) {
    // For main file tabs: pdf-0-ai, for inner: innerpdf-0-0-ai
    if (!requestData || !requestData.files) return null;
    for (const [fileIdx, file] of requestData.files.entries()) {
      if (tabId === `pdf-${fileIdx}-ai` && file.ai_summaries && file.ai_summaries[personaId]) {
        return file.ai_summaries[personaId];
      }
      if (file.type === 'zip' && file.content_files) {
        for (const [innerIdx, inner] of file.content_files.entries()) {
          if (tabId === `innerpdf-${fileIdx}-${innerIdx}-ai` && inner.ai_summaries && inner.ai_summaries[personaId]) {
            return inner.ai_summaries[personaId];
          }
        }
      }
    }
    return null;
  }

  // --- AI Summary Toggle ---
  function initAiSummaryToggle() {
    document.querySelectorAll('.ai-summary-toggle').forEach(toggle => {
      const summary = toggle.parentElement.querySelector('.ai-summary-markdown');
      if (!summary) return;
      toggle.onclick = function() {
        summary.classList.toggle('collapsed');
        toggle.textContent = summary.classList.contains('collapsed') ? 'Show AI Generated Overview' : 'Hide AI Generated Overview';
      };
      // Ensure initial state is collapsed
      summary.classList.add('collapsed');
      toggle.textContent = 'Show AI Generated Overview';
    });
  }

  // --- Popover Logic ---
  let popover = null;
  function attachPopoverHandlers() {
    if (!popover) {
      popover = document.createElement('div');
      popover.id = 'ai-summary-hover-popover';
      popover.className = 'ai-summary-popover';
      document.body.appendChild(popover);
    }
    document.querySelectorAll('.ai-summary-label').forEach(label => {
      label.onmouseenter = function(e) {
        const model = label.getAttribute('data-summary-model') || '';
        const date = label.getAttribute('data-summary-date') || '';
        let modelDisplay = model ? `Generated by: <strong>${model.replace(/gemini[-_]?/i, 'Gemini ')}</strong>` : '';
        let dateDisplay = '';
        if (date) {
          let d = new Date(date);
          if (!isNaN(d)) {
            let y = d.getFullYear();
            let m = String(d.getMonth()+1).padStart(2, '0');
            let day = String(d.getDate()).padStart(2, '0');
            let h = String(d.getHours()).padStart(2, '0');
            let min = String(d.getMinutes()).padStart(2, '0');
            dateDisplay = `<span class="popover-date">Date: ${y}-${m}-${day} ${h}:${min}</span>`;
          } else {
            dateDisplay = `<span class="popover-date">Date: ${date}</span>`;
          }
        }
        popover.innerHTML = `${modelDisplay}${dateDisplay}`;
        const rect = label.getBoundingClientRect();
        const scrollY = window.scrollY || window.pageYOffset;
        const scrollX = window.scrollX || window.pageXOffset;
        let top = rect.bottom + scrollY + 8;
        let left = rect.left + scrollX + 8;
        popover.style.top = `${top}px`;
        popover.style.left = `${left}px`;
        popover.style.minWidth = '250px';
        popover.style.maxWidth = '350px';
        popover.style.pointerEvents = 'auto';
        setTimeout(() => popover.classList.add('visible'), 0);
      };
      label.onmouseleave = function() {
        popover.classList.remove('visible');
        popover.style.pointerEvents = 'none';
      };
    });
    popover.onmouseenter = function() { popover.classList.add('visible'); };
    popover.onmouseleave = function() { popover.classList.remove('visible'); };
  }

  // --- Tabbed File View Logic (from detail.js) ---
  window.showTab = function(btn, tabId) {
    const container = btn.closest('.tabbed-view');
    const buttons = container.querySelectorAll('.foi-tab, .tab-btn');
    const tabs = container.querySelectorAll('.tab-content');
    buttons.forEach(b => b.classList.remove('active'));
    tabs.forEach(t => t.style.display = 'none');
    btn.classList.add('active');
    const tab = container.querySelector('#' + tabId);
    if (tab) tab.style.display = 'block';
    // Save tab state in hash if possible
    const section = btn.closest('.foi-file-section');
    if (section && section.id) {
      const hash = window.location.hash.replace(/^#/, '');
      const parts = hash.split(':');
      const sectionId = section.id;
      const tabPart = tabId;
      window.location.hash = sectionId + (tabPart ? ':' + tabPart : '');
    }
  };
  window.selectFile = function(idx) {
    const sections = document.querySelectorAll('.foi-file-section');
    const sidebarItems = document.querySelectorAll('.foi-sidebar-item');
    const sidebarBtns = document.querySelectorAll('.foi-sidebar-btn[role="tab"]');
    sections.forEach(sec => sec.style.display = 'none');
    sidebarItems.forEach(item => item.classList.remove('active'));
    sidebarBtns.forEach(btn => btn.setAttribute('aria-selected', 'false'));
    const section = document.getElementById('foi-file-' + idx);
    const sidebarItem = document.querySelector('.foi-sidebar-item[data-file-idx="' + idx + '"]');
    const tabBtn = sidebarItem ? sidebarItem.querySelector('.foi-sidebar-btn[role="tab"]') : null;
    if (section) section.style.display = 'block';
    if (sidebarItem) sidebarItem.classList.add('active');
    if (tabBtn) tabBtn.setAttribute('aria-selected', 'true');
    // Save file state in hash
    window.location.hash = section ? section.id : '';
  };

  // --- Initialization ---
  document.addEventListener('DOMContentLoaded', function() {
    loadPageData();
    if (personaSelector) {
      personaSelector.value = selectedPersona;
      personaSelector.onchange = function() {
        updateSummaries(this.value);
      };
    }
    updateSummaries(selectedPersona);
  });
})();
