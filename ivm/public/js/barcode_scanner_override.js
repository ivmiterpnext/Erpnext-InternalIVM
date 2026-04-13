frappe.provide("frappe.ui");

// Store the original Scanner class
const OriginalScanner = frappe.ui.Scanner;

// Override the Scanner class
frappe.ui.Scanner = class extends OriginalScanner {
    make_dialog() {
        let dialog = new frappe.ui.Dialog({
            title: __("Scan Barcode"),  // Changed from "Scan QRCode"
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "scan_area",
                },
            ],
            on_page_show: () => {
                this.$scan_area = dialog.get_field("scan_area").$wrapper;
                this.$scan_area.addClass("barcode-scanner");
                this.scan_area_id = frappe.dom.set_unique_id(this.$scan_area);
                this.scan();
            },
            on_hide: () => {
                this.stop_scan();
            },
            minimizable: this.options.minimizable,
            primary_action_label: this.options.primary_action_label,
            primary_action: this.options.primary_action,
        });
        return dialog;
    }
    
    start_scan() {
        if (!this.handler) {
            this.handler = new Html5Qrcode(this.scan_area_id);
        }
        
        const config = {
            fps: 10,
            qrbox: { width: 500, height: 150 }  // Wide rectangle instead of square
        };
        
        this.handler
            .start(
                { facingMode: "environment" },
                config,
                (decodedText, decodedResult) => {
                    if (this.options.on_scan) {
                        try {
                            this.options.on_scan(decodedResult);
                        } catch (error) {
                            console.error(error);
                        }
                    }
                    if (!this.options.multiple) {
                        this.stop_scan();
                        this.hide_dialog();
                    }
                },
                (errorMessage) => {
                    // parse error, ignore it.
                }
            )
            .catch((err) => {
                this.is_alive = false;
                this.hide_dialog();
                console.error(err);
            });
        this.is_alive = true;
    }
};
