/* Zimbra Lifecycle Manager - JavaScript */
document.addEventListener('DOMContentLoaded', function() {
    // Highlight active sidebar link
    const currentPath = window.location.pathname;
    document.querySelectorAll('.sidebar-nav .nav-link').forEach(function(link) {
        const href = link.getAttribute('href');
        if (href === '/' && currentPath === '/') {
            link.classList.add('active');
        } else if (href !== '/' && currentPath.startsWith(href)) {
            link.classList.add('active');
        }
    });

    // Auto-dismiss alerts after 5 seconds
    document.querySelectorAll('.alert-dismissible').forEach(function(alert) {
        setTimeout(function() {
            var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm status change
    var statusForm = document.getElementById('status-change-form');
    if (statusForm) {
        statusForm.addEventListener('submit', function(e) {
            var select = statusForm.querySelector('select[name="new_status"]');
            var newStatus = select.options[select.selectedIndex].text;
            if (!confirm('Are you sure you want to change status to ' + newStatus + '?')) {
                e.preventDefault();
            }
        });
    }

    // Confirm bulk execute
    var bulkExecuteBtn = document.getElementById('bulk-execute-btn');
    if (bulkExecuteBtn) {
        bulkExecuteBtn.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to execute this bulk operation? This cannot be undone.')) {
                e.preventDefault();
            }
        });
    }

    // Filter form auto-submit on select change
    document.querySelectorAll('.filter-bar select').forEach(function(select) {
        select.addEventListener('change', function() {
            this.closest('form').submit();
        });
    });

    // Export button
    var exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', function(e) {
            e.preventDefault();
            var params = new URLSearchParams(window.location.search);
            window.location.href = '/exports/accounts/?' + params.toString();
        });
    }

    // Select all checkbox for tables
    var selectAll = document.getElementById('select-all');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            var checkboxes = document.querySelectorAll('.row-select');
            checkboxes.forEach(function(cb) {
                cb.checked = selectAll.checked;
            });
        });
    }

    // Search with debounce
    var searchInput = document.querySelector('.filter-bar input[name="q"]');
    if (searchInput) {
        var debounceTimer;
        searchInput.addEventListener('keyup', function(e) {
            if (e.key === 'Enter') {
                this.closest('form').submit();
            }
        });
    }
});

// Format file size
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(1)) + ' ' + sizes[i];
}
