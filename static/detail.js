function showTab(btn, tabId) {
  var container = btn.closest('.tabbed-view');
  var buttons = container.querySelectorAll('.tab-btn');
  var tabs = container.querySelectorAll('.tab-content');
  buttons.forEach(function(b) { b.classList.remove('active'); });
  tabs.forEach(function(t) { t.style.display = 'none'; });
  btn.classList.add('active');
  var tab = container.querySelector('#' + tabId);
  if (tab) tab.style.display = 'block';
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
}
document.addEventListener('DOMContentLoaded', function() {
  // Show the first file or first zip overview by default
  var first = document.querySelector('.foi-file-section');
  if (first) first.style.display = 'block';
  var firstSidebar = document.querySelector('.foi-sidebar-item');
  if (firstSidebar) firstSidebar.classList.add('active');
  var firstBtn = firstSidebar ? firstSidebar.querySelector('.foi-sidebar-btn[role="tab"]') : null;
  if (firstBtn) firstBtn.setAttribute('aria-selected', 'true');
});
