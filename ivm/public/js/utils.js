frappe.provide('ivm.utils');

/**
 * Logger utility that logs only when developer mode is enabled
 */
ivm.utils.debug_log = function(...args) {
    if (frappe.boot.developer_mode) {
        console.log('[IVM]', ...args);
    }
};
