function showTab(btn, tabId) {
  var container = btn.closest('.tabbed-view');
  var buttons = container.querySelectorAll('.foi-tab, .tab-btn');
  var tabs = container.querySelectorAll('.tab-content');
  buttons.forEach(function(b) { b.classList.remove('active'); });
  tabs.forEach(function(t) { t.style.display = 'none'; });
  btn.classList.add('active');
  var tab = container.querySelector('#' + tabId);
  if (tab) tab.style.display = 'block';
  // Save tab state in hash if possible
  var section = btn.closest('.foi-file-section');
  if (section && section.id) {
    var hash = window.location.hash.replace(/^#/, '');
    var parts = hash.split(':');
    var sectionId = section.id;
    var tabPart = tabId;
    window.location.hash = sectionId + (tabPart ? ':' + tabPart : '');
  }
}
function selectFile(idx) {
  var sections = document.querySelectorAll('.foi-file-section');
  var sidebarItems = document.querySelectorAll('.foi-sidebar-item');
  var sidebarBtns = document.querySelectorAll('.foi-sidebar-btn[role="tab"]');
  sections.forEach(function(sec) { sec.style.display = 'none'; });
  sidebarItems.forEach(function(item) { item.classList.remove('active'); });
  sidebarBtns.forEach(function(btn) { btn.setAttribute('aria-selected', 'false'); });
  var section = document.getElementById('foi-file-' + idx);
  var sidebarItem = document.querySelector('.foi-sidebar-item[data-file-idx="' + idx + '"]');
  var tabBtn = sidebarItem ? sidebarItem.querySelector('.foi-sidebar-btn[role="tab"]') : null;
  if (section) section.style.display = 'block';
  if (sidebarItem) sidebarItem.classList.add('active');
  if (tabBtn) tabBtn.setAttribute('aria-selected', 'true');
  // Save file state in hash
  window.location.hash = section ? section.id : '';
}
document.addEventListener('DOMContentLoaded', function() {
  // Restore state from hash if present
  var hash = window.location.hash.replace(/^#/, '');
  var sectionId = null, tabId = null;
  if (hash) {
    var parts = hash.split(':');
    sectionId = parts[0];
    tabId = parts[1];
  }
  var section = sectionId ? document.getElementById(sectionId) : null;
  if (section) {
    // Hide all, show selected
    document.querySelectorAll('.foi-file-section').forEach(function(sec) { sec.style.display = 'none'; });
    section.style.display = 'block';
    // Highlight sidebar
    var sidebarItem = document.querySelector('.foi-sidebar-item[data-file-idx="' + (sectionId.replace('foi-file-', '')) + '"]');
    if (sidebarItem) sidebarItem.classList.add('active');
    var tabBtn = sidebarItem ? sidebarItem.querySelector('.foi-sidebar-btn[role="tab"]') : null;
    if (tabBtn) tabBtn.setAttribute('aria-selected', 'true');
    // If a tab is specified, activate it
    if (tabId) {
      var tabBtnEl = section.querySelector('.foi-tab, .tab-btn[onclick*="' + tabId + '"]');
      var tabContent = section.querySelector('#' + tabId);
      if (tabBtnEl && tabContent) {
        section.querySelectorAll('.foi-tab, .tab-btn').forEach(function(b) { b.classList.remove('active'); });
        section.querySelectorAll('.tab-content').forEach(function(t) { t.style.display = 'none'; });
        tabBtnEl.classList.add('active');
        tabContent.style.display = 'block';
      }
    }
  } else {
    // Show the first file or first zip overview by default
    var first = document.querySelector('.foi-file-section');
    if (first) first.style.display = 'block';
    var firstSidebar = document.querySelector('.foi-sidebar-item');
    if (firstSidebar) firstSidebar.classList.add('active');
    var firstBtn = firstSidebar ? firstSidebar.querySelector('.foi-sidebar-btn[role="tab"]') : null;
    if (firstBtn) firstBtn.setAttribute('aria-selected', 'true');
  }
  // AI summary toggle
  var toggle = document.querySelector('.ai-summary-toggle');
  var summary = document.querySelector('.ai-summary-markdown');
  if (toggle && summary) {
    toggle.addEventListener('click', function() {
      summary.classList.toggle('collapsed');
      toggle.textContent = summary.classList.contains('collapsed') ? 'Show AI Generated Overview' : 'Hide AI Generated Overview';
    });
    // Ensure initial state is collapsed
    summary.classList.add('collapsed');
    toggle.textContent = 'Show AI Generated Overview';
  }
});
