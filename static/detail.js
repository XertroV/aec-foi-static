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
  sections.forEach(function(sec) { sec.style.display = 'none'; });
  sidebarItems.forEach(function(item) { item.classList.remove('active'); });
  var section = document.getElementById('foi-file-' + idx);
  var sidebarItem = document.querySelector('.foi-sidebar-item[data-file-idx="' + idx + '"]');
  if (section) section.style.display = 'block';
  if (sidebarItem) sidebarItem.classList.add('active');
}
document.addEventListener('DOMContentLoaded', function() {
  // Show the first file or first zip overview by default
  var first = document.querySelector('.foi-file-section');
  if (first) first.style.display = 'block';
  var firstSidebar = document.querySelector('.foi-sidebar-item');
  if (firstSidebar) firstSidebar.classList.add('active');
});
