// General UI logic for persona switching, summary popovers, and tabbed file views
(() => {
  // --- Globals ---
  let currentPageData = null;
  let allDocumentsData = null;
  let isDetailPage = false;
  let isIndexPage = false;
  let personaSelector = null;
  const personaStorageKey = 'aec_foi_selected_persona';
  let selectedPersona = null;
  let popover = null;

  // --- Data Loading ---
  function loadPageData() {
    const detailScript = document.getElementById('current-foi-data');
    const indexScript = document.getElementById('documents-data');
    if (detailScript) {
      try {
        currentPageData = JSON.parse(detailScript.textContent);
        isDetailPage = true;
        console.log('[AEC FOI JS] Loaded detail page data:', currentPageData);
      } catch (e) { console.error('[AEC FOI JS] Failed to parse current-foi-data:', e); }
    }
    if (indexScript) {
      try {
        allDocumentsData = JSON.parse(indexScript.textContent);
        isIndexPage = true;
        console.log('[AEC FOI JS] Loaded index page data:', allDocumentsData);
      } catch (e) { console.error('[AEC FOI JS] Failed to parse documents-data:', e); }
    }
  }

  // --- Persona UI Update ---
  function updatePersonaUI(personaId) {
    console.log('[AEC FOI JS] updatePersonaUI called with persona:', personaId);
    localStorage.setItem(personaStorageKey, personaId);
    if (personaSelector) personaSelector.value = personaId;

    // --- Detail Page Logic ---
    if (isDetailPage && currentPageData) {
      // Overall summary
      const overallBlock = document.querySelector('.overall-ai-summary');
      if (overallBlock) {
        const summaryData = currentPageData.ai_summaries?.[personaId]?.overall;
        const summaryDiv = overallBlock.querySelector('.ai-summary-markdown-content');
        const label = overallBlock.querySelector('.ai-summary-label');
        if (summaryData && summaryData.text) {
          if (!window.marked) {
            console.warn('[AEC FOI JS] window.marked not found. Markdown will not be rendered.');
          }
          summaryDiv.innerHTML = window.marked ? window.marked.parse(summaryData.text) : summaryData.text;
          if (label) {
            label.setAttribute('data-summary-model', summaryData.model || '');
            label.setAttribute('data-summary-date', summaryData.generated_at || '');
          }
          overallBlock.style.display = '';
        } else {
          overallBlock.style.display = 'none';
        }
      }

      // Per-file summaries in tabs
      document.querySelectorAll('.foi-file-section').forEach(section => {
        const sectionId = section.id;
        let fileIdx = null, innerIdx = null, isZip = false;
        const zipMatch = sectionId.match(/^foi-file-zip-(\d+)(?:-(\d+))?$/);
        if (zipMatch) {
          isZip = true;
          fileIdx = parseInt(zipMatch[1], 10);
          if (zipMatch[2] !== undefined) innerIdx = parseInt(zipMatch[2], 10);
        } else {
          const normMatch = sectionId.match(/^foi-file-(\d+)$/);
          if (normMatch) fileIdx = parseInt(normMatch[1], 10);
        }

        let summaryData = null, tabId = null, tabBtn = null, tabContent = null;
        if (isZip && innerIdx !== null) {
          summaryData = currentPageData.files?.[fileIdx]?.content_files?.[innerIdx]?.ai_summaries?.[personaId];
          tabId = `innerpdf-${fileIdx}-${innerIdx}-ai`;
        } else if (isZip) {
          summaryData = currentPageData.files?.[fileIdx]?.ai_summaries?.[personaId];
          tabId = `pdf-${fileIdx}-ai`;
        } else if (fileIdx !== null) {
          summaryData = currentPageData.files?.[fileIdx]?.ai_summaries?.[personaId];
          tabId = `pdf-${fileIdx}-ai`;
        }
        if (tabId) {
          tabContent = section.querySelector(`#${tabId}`);
          tabBtn = section.querySelector(`.foi-tab[onclick*="${tabId}"]`);
        }

        // DEBUG LOGGING
        console.log('[AEC FOI JS][DEBUG] Tab:', tabId, 'summaryData:', summaryData, 'tabBtn:', tabBtn, 'tabContent:', tabContent);

        // Show/hide AI summary tab and update content
        if (tabContent && tabBtn) {
          if (summaryData && typeof summaryData.text === 'string') {
            const contentDiv = tabContent.querySelector('.ai-summary-markdown-content');
            const label = tabContent.querySelector('.ai-summary-label');
            if (!window.marked) {
              console.warn('[AEC FOI JS] window.marked not found. Markdown will not be rendered.');
            }
            contentDiv.innerHTML = window.marked ? window.marked.parse(summaryData.text) : summaryData.text;
            if (label) {
              label.setAttribute('data-summary-model', summaryData.model || '');
              label.setAttribute('data-summary-date', summaryData.generated_at || '');
            }
            tabContent.style.display = '';
            tabBtn.style.display = '';
          } else {
            tabContent.style.display = 'none';
            tabBtn.style.display = 'none';
            if (tabBtn.classList.contains('active')) {
              // Try to find a visible tab to switch to
              const fallbackTab = Array.from(section.querySelectorAll('.foi-tab')).find(t => t.style.display !== 'none');
              if (fallbackTab) {
                fallbackTab.click();
                console.log('[AEC FOI JS] Switched to fallback tab:', fallbackTab);
              } else {
                console.warn('[AEC FOI JS] No visible fallback tab found in section:', sectionId);
              }
            }
          }
        }
      });
    }

    // --- Index Page Logic ---
    if (isIndexPage && allDocumentsData) {
      document.querySelectorAll('li.document-item').forEach(item => {
        const docId = item.getAttribute('data-doc-id');
        const doc = allDocumentsData.find(d => d.id === docId);
        const block = item.querySelector('.ai-summary-block');
        if (!block || !doc) return;
        const summaryData = doc.ai_summaries?.[personaId]?.short_index;
        const label = block.querySelector('.ai-summary-label');
        if (summaryData && summaryData.text) {
          const aiSummaryTextDiv = block.querySelector('.ai-summary-text');
          if (!window.marked) {
            console.warn('[AEC FOI JS] window.marked not found. Markdown will not be rendered.');
          }
          aiSummaryTextDiv.innerHTML = window.marked ? window.marked.parse(summaryData.text) : summaryData.text;
          if (label) {
            label.setAttribute('data-summary-model', summaryData.model || '');
            label.setAttribute('data-summary-date', summaryData.generated_at || '');
          }
          block.style.display = '';
        } else {
          block.style.display = 'none';
        }
      });
    }
    // Re-attach popover handlers after UI update
    setupAiSummaryPopovers();
    // No need to re-init toggles as event delegation is used
  }

  // --- AI Summary Toggle (Event Delegation) ---
  function initAiSummaryToggle() {
    // Reset all toggles to collapsed state
    document.querySelectorAll('.ai-summary-toggle').forEach(toggle => {
      const summary = toggle.parentNode.querySelector('.ai-summary-markdown');
      if (summary) {
        summary.classList.add('collapsed');
        toggle.textContent = 'Show AI Generated Overview';
      }
    });
    console.log('[AEC FOI JS] AI summary toggles initialized.');
  }
  // Attach event delegation for toggles
  document.body.addEventListener('click', function(e) {
    if (e.target && e.target.classList.contains('ai-summary-toggle')) {
      const summary = e.target.parentNode.querySelector('.ai-summary-markdown');
      if (summary) {
        summary.classList.toggle('collapsed');
        e.target.textContent = summary.classList.contains('collapsed')
          ? 'Show AI Generated Overview'
          : 'Hide AI Generated Overview';
      }
    }
  });

  // --- Popover Logic (Event Delegation) ---
  function setupAiSummaryPopovers() {
    if (!popover) {
      popover = document.createElement('div');
      popover.id = 'ai-summary-hover-popover';
      popover.className = 'ai-summary-popover';
      document.body.appendChild(popover);
      console.log('[AEC FOI JS] Popover created.');
    }
    // Hide popover on scroll/resize
    function hidePopover() {
      popover.classList.remove('visible');
      popover.style.pointerEvents = 'none';
    }
    window.addEventListener('scroll', hidePopover);
    window.addEventListener('resize', hidePopover);

    document.body.addEventListener('mouseover', function(e) {
      const label = e.target.closest('.ai-summary-label');
      if (!label) return;
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
      console.log('[AEC FOI JS] Popover shown for label:', label);
    });
    document.body.addEventListener('mouseleave', function(e) {
      if (e.target && e.target.classList && e.target.classList.contains('ai-summary-label')) {
        popover.classList.remove('visible');
        popover.style.pointerEvents = 'none';
        console.log('[AEC FOI JS] Popover hidden.');
      }
    }, true);
    popover.onmouseenter = function() { popover.classList.add('visible'); };
    popover.onmouseleave = function() { popover.classList.remove('visible'); };
  }

  // --- Tabbed File View Logic ---
  window.showTab = function(btn, tabId) {
    const container = btn.closest('.tabbed-view');
    if (!container) return;
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
      const sectionId = section.id;
      const newHash = sectionId + (tabId ? ':' + tabId : '');
      if (window.location.hash.replace(/^#/, '') !== newHash) {
        window.location.hash = newHash;
      }
    }
    console.log('[AEC FOI JS] showTab called:', tabId, 'in section', container);
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
    if (section && window.location.hash.replace(/^#/, '') !== section.id) {
      window.location.hash = section.id;
    }
    console.log('[AEC FOI JS] selectFile called for idx:', idx);
  };

  // --- Hash Navigation ---
  function handleHashNavigation() {
    const hash = window.location.hash.replace(/^#/, '');
    if (!isDetailPage) return;
    if (!hash) {
      // Default: select first file section and first tab
      const firstSidebar = document.querySelector('.foi-sidebar-item');
      if (firstSidebar) {
        const idx = firstSidebar.getAttribute('data-file-idx');
        if (idx !== null) window.selectFile(idx);
      }
      const firstTabBtn = document.querySelector('.tabbed-view .foi-tab');
      if (firstTabBtn) firstTabBtn.click();
      console.log('[AEC FOI JS] handleHashNavigation: defaulted to first file and tab.');
      return;
    }
    // Hash format: sectionId[:tabId]
    const [sectionId, tabId] = hash.split(':');
    if (sectionId) {
      const idx = sectionId.replace('foi-file-', '');
      window.selectFile(idx);
    }
    if (tabId) {
      // Find the tab button for this tabId and click it
      const tabBtn = document.querySelector(`.tabbed-view .foi-tab[onclick*="${tabId}"]`);
      if (tabBtn) tabBtn.click();
    }
    console.log('[AEC FOI JS] handleHashNavigation: navigated to', hash);
  }

  // --- Initialization ---
  document.addEventListener('DOMContentLoaded', function() {
    loadPageData();
    personaSelector = document.getElementById('persona-selector');
    selectedPersona = localStorage.getItem(personaStorageKey) || (window.DEFAULT_PERSONA || 'balanced');
    if (personaSelector) {
      personaSelector.value = selectedPersona;
      personaSelector.onchange = function() {
        updatePersonaUI(this.value);
        setTimeout(handleHashNavigation, 0);
      };
    }
    updatePersonaUI(selectedPersona);
    setupAiSummaryPopovers();
    setTimeout(handleHashNavigation, 0);
    window.addEventListener('hashchange', handleHashNavigation);
  });

  // --- Helper: Find persona data for a tab by id (for legacy support) ---
  function findPersonaDataForTab(requestData, tabId, personaId) {
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
})();
