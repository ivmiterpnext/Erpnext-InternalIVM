frappe.search.AwesomeBar.prototype.make_global_search = function (txt) {
    // let search_text = $(this.awesomplete.ul).find('.search-text');
  
    // if (txt.charAt(0) === "#" || !txt) {
    // 	search_text && search_text.remove();
    // 	return;
    // }
  
    // if (!search_text.length) {
    // 	search_text = $(this.awesomplete.ul).prepend(`
    // 		<div class="search-text">
    // 			<span class="search-text"></span>
    // 		<div>`
    // 	).find(".search-text");
    // }
  
    // search_text.html(`
    // 	<span class="flex justify-between">
    // 		<span class="ellipsis">Search for ${frappe.utils.xss_sanitise(txt).bold()}</span>
    // 		<kbd>↵</kbd>
    // 	</span>
    // `);
  
    // search_text.click(() => {
    // 	frappe.searchdialog.search.init_search(txt, "global_search");
    // });
  
    // REDESIGN TODO: Remove this as a selectable option
    if (txt.charAt(0) === "#") {
      return;
    }
  
    this.options.push({
      label: `
                  <span class="flex justify-between text-medium">
                      <span class="ellipsis">${__("Search for {0}", [
              frappe.utils.xss_sanitise(txt).bold(),
            ])}</span>
                      <kbd>↵</kbd>
                  </span>
              `,
      value: __("Search for {0}", [txt]),
      match: txt,
      index: 100,
      default: "Search",
      onclick: function () {
        frappe.searchdialog.search.init_search(txt, "global_search");
      },
    });
    
    this.options.push({
      label: `
                  <span class="flex justify-between text-medium">
                      <span class="ellipsis">${__("Search machine number {0}", [
              frappe.utils.xss_sanitise(txt).bold(),
            ])}</span>
                      <kbd>↵</kbd>
                  </span>
              `,
      value: __("Search Search machine number {0}", [txt]),
      match: txt,
      index: 100,
      default: "Search",
      onclick: function () {
        frappe.call({
          method: "ivm.api.search_machine_numbers",
          args: { machine_no: txt },
          callback: function (r) {
            if (r.message) {
              var content = '<div class="record-list">';
              for (var key in r.message) {
                if (r.message.hasOwnProperty(key)) {
                  content += `<h4>${key[0].toUpperCase() + key.slice(1)}</h4>`;
                  content += "<ul>";
                  r.message[key].forEach(function (record) {
                    var url = `/app/${key}/${record.name}`;
                    content += `<li><a href="${url}" class="record-link">${record.name}</a></li>`;
                  });
                  content += "</ul>";
                }
              }
              content += "</div>";
              frappe.msgprint(content, __("Search Results"));
            }
          },
        });
      },
    });
  };
  