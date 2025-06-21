// Detail page logic for tabbed file views and navigation state
(function() {
  console.log('[detail.js] Script loaded');
  // Show a specific tab in a tabbed view
  const showTab = (btn, tabId) => {
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

  // Select a file section and update sidebar state
  const selectFile = idx => {
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

  // Restore navigation and tab state from URL hash on page load
  document.addEventListener('DOMContentLoaded', () => {
    const hash = window.location.hash.replace(/^#/, '');
    let sectionId = null, tabId = null;
    if (hash) {
      const parts = hash.split(':');
      sectionId = parts[0];
      tabId = parts[1];
    }
    const section = sectionId ? document.getElementById(sectionId) : null;
    if (section) {
      // Hide all, show selected
      document.querySelectorAll('.foi-file-section').forEach(sec => sec.style.display = 'none');
      section.style.display = 'block';
      // Highlight sidebar
      const sidebarItem = document.querySelector('.foi-sidebar-item[data-file-idx="' + (sectionId.replace('foi-file-', '')) + '"]');
      if (sidebarItem) sidebarItem.classList.add('active');
      const tabBtn = sidebarItem ? sidebarItem.querySelector('.foi-sidebar-btn[role="tab"]') : null;
      if (tabBtn) tabBtn.setAttribute('aria-selected', 'true');
      // If a tab is specified, activate it
      if (tabId) {
        const tabBtnEl = section.querySelector('.foi-tab, .tab-btn[onclick*="' + tabId + '"]');
        const tabContent = section.querySelector('#' + tabId);
        if (tabBtnEl && tabContent) {
          section.querySelectorAll('.foi-tab, .tab-btn').forEach(b => b.classList.remove('active'));
          section.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
          tabBtnEl.classList.add('active');
          tabContent.style.display = 'block';
        }
      }
    } else {
      // Show the first file or first zip overview by default
      const first = document.querySelector('.foi-file-section');
      if (first) first.style.display = 'block';
      const firstSidebar = document.querySelector('.foi-sidebar-item');
      if (firstSidebar) firstSidebar.classList.add('active');
      const firstBtn = firstSidebar ? firstSidebar.querySelector('.foi-sidebar-btn[role="tab"]') : null;
      if (firstBtn) firstBtn.setAttribute('aria-selected', 'true');
    }
    // AI summary toggle
    const toggle = document.querySelector('.ai-summary-toggle');
    const summary = document.querySelector('.ai-summary-markdown');
    if (toggle && summary) {
      toggle.addEventListener('click', () => {
        summary.classList.toggle('collapsed');
        toggle.textContent = summary.classList.contains('collapsed') ? 'Show AI Generated Overview' : 'Hide AI Generated Overview';
      });
      // Ensure initial state is collapsed
      summary.classList.add('collapsed');
      toggle.textContent = 'Show AI Generated Overview';
    }
  });

  // Expose functions for template usage
  window.showTab = showTab;
  window.selectFile = selectFile;
  console.log('[detail.js] showTab and selectFile attached to window');
})();
