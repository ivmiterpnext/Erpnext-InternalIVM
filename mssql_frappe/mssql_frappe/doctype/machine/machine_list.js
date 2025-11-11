frappe.listview_settings["Machine"] = {
	hide_name_column: true,
	hide_name_filter: true,

    // There may be a better way to do this for all list views globally, 
    // but the number of columns and their widths are subject to change.
    refresh: function(listview){
        document.querySelectorAll('.list-row-col').forEach(function(col){
            col.style.minWidth = '225px';
            col.style.maxWidth = '225px';
        })
        document.querySelectorAll('.list-subject').forEach(function(col){
            col.style.minWidth = '150px';
            col.style.maxWidth = '150px';
        })
        let main_container = document.querySelector(".frappe-list")
        if (main_container){
            main_container.style.overflowX= "auto"
        }
        document.querySelectorAll('.list-row-head, .list-row-container').forEach(function(col){
            col.style.width = 'max-content';
        })
        document.querySelectorAll('.list-row .level-right').forEach(function(col){
            col.style.minWidth = '100px';
            col.style.maxWidth = '100px';
        })

        let sidebar = document.querySelector('.layout-side-section');
        if (sidebar && sidebar.classList.contains('opened')) {
            sidebar.classList.remove('opened');
        }
    }
}