"""
IT Inventory Setup Script

Builds out the IT department warehouse structure, items, suppliers, and
manufacturers based on the Sortly export, then reconciles stock quantities
and per-unit valuation rates to match the Sortly count.

Portable between dev.local and ivmportal.frappe.cloud (prod). Every Item is
keyed by an explicit item_code (Sortly-derived where available, matching the
existing SCX4IT naming series), so the script performs a create-or-update
(upsert) per item rather than assuming it already exists.

USAGE
-----
Dev:
    bench --site dev.local execute "exec(open('/home/lhammond/frappe-bench/apps/ivm/ivm/warehouse/recon_scripts/it_inventory_setup.py').read(), globals())"

Prod (from inside the bench container):
    bench --site ivmportal.frappe.cloud execute "exec(open('/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/it_inventory_setup.py').read(), globals())"

Set DRY_RUN = True (default) to preview every action without writing
anything. Set DRY_RUN = False to actually execute. Re-running this script
after a partial or full run is safe — every phase checks for existing
records before creating anything.
"""

import frappe

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DRY_RUN = False
COMPANY = "IVM"

STOCK_ADJUSTMENT_ACCOUNT = "5119 - Stock Adjustment - I"
COST_CENTER = "Main - I"

MAX_RECON_ROWS_PER_BATCH = 90  # stay comfortably under the 100-row sync limit


def log(msg):
    print(f"[IT-SETUP] {msg}")


# ---------------------------------------------------------------------------
# DATA — SUPPLIERS
# ---------------------------------------------------------------------------

SUPPLIERS = [
    "Amazon",
    "Antaira",
    "ASAPIdent",
    "Clary Business Machines",
    "EMP Technical Group",
    "Farpointe Data",
    "Gammons",
    "KVM Switches Online",
    "Mirac",
    "Monoprice",
    "OptConnect",
    "Raritan Solutions",
    "Seeed Studio",
    "SimplyNUC",
    "VidaBox",
    "Vendnovation",
]

# Sortly's "Sergeant" supplier maps to the pre-existing "Sargent Metal" supplier.
SUPPLIER_ALIASES = {
    "Sergeant": "Sargent Metal",
}


# ---------------------------------------------------------------------------
# DATA — MANUFACTURERS
# ---------------------------------------------------------------------------

MANUFACTURERS = [
    "Amazon",
    "Amazon Basics",
    "ANMBEST",
    "Anker",
    "Antaira",
    "Apple",
    "AuviPal",
    "Cable Matters",
    "Ceptics",
    "Datalogic",
    "DongGuan Simer Electronics Co. LTD",
    "DTech",
    "Farpointe Data",
    "FTDI",
    "Gammons",
    "HID",
    "iMBAPrice",
    "KMC",
    "LinkStar",
    "Mirac",
    "Monoprice",
    "OptConnect",
    "Phillips",
    "Planar",
    "Raritan",
    "RFIDeas",
    "Sergeant",
    "SimplyNUC",
    "Stouchi",
    "VCT",
    "Vendnovation",
    "VidaMount",
]


# ---------------------------------------------------------------------------
# DATA — WAREHOUSES (order matters: parents before children)
# ---------------------------------------------------------------------------

WAREHOUSES = [
    {"name": "Cage - I", "parent": "IT - I"},
    {"name": "Badge Readers - I", "parent": "Cage - I"},
    {"name": "Connectivity - I", "parent": "Cage - I"},
    {"name": "KVM - I", "parent": "Cage - I"},
    {"name": "Motherboards - I", "parent": "Cage - I"},
    {"name": "Returned Equipment - I", "parent": "Cage - I"},
    {"name": "SmartScreen - I", "parent": "Cage - I"},
    {"name": "iPad Components - I", "parent": "Cage - I"},
    {"name": "Studio - I", "parent": "IT - I"},
    {"name": "Lobby - I", "parent": "IT - I"},
    {"name": "Cubicles - I", "parent": "IT - I"},
]

GROUP_WAREHOUSES_TO_FLIP = ["IT - I", "Cage - I"]


# ---------------------------------------------------------------------------
# DATA — ALL ITEMS (existing + new), every entry carries an explicit item_code
# ---------------------------------------------------------------------------

ALL_ITEMS = [
    # -- Badge Readers --
    {"item_code": "SCX4IT1149", "item_name": "Datalogic 900i", "manufacturer": "Datalogic", "part_no": "900i", "supplier": "EMP Technical Group", "valuation_rate": 225},
    {"item_code": "SCX4IT0028", "item_name": "Delta3", "manufacturer": "Farpointe Data", "part_no": "Delta3", "supplier": "Farpointe Data", "valuation_rate": 124},
    {"item_code": "SCX4IT1957", "item_name": "HID Omnikey Reader", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 139.32},
    {"item_code": "SCX4IT0056", "item_name": "HID Signo 20", "manufacturer": "HID", "part_no": "20NKS-00-000000", "supplier": "ASAPIdent", "valuation_rate": 244},
    {"item_code": "SCX4IT0057", "item_name": "HID Signo 40", "manufacturer": "HID", "part_no": "40NKS-00-000000", "supplier": "ASAPIdent", "valuation_rate": 249},
    {"item_code": "SCX4IT0051", "item_name": "MCR-30-H (ASP)", "manufacturer": "Farpointe Data", "part_no": "MCR-30-H REV D", "supplier": "Farpointe Data", "valuation_rate": 89},
    {"item_code": "SCX4IT0011", "item_name": "MultiCLASS R10", "manufacturer": "HID", "part_no": "910PTNNEK00000", "supplier": "ASAPIdent", "valuation_rate": 164},
    {"item_code": "SCX4IT0010", "item_name": "MultiCLASS R40", "manufacturer": "HID", "part_no": "920PTNNEK00000", "supplier": "ASAPIdent", "valuation_rate": 249},
    {"item_code": "SCX4IT0008", "item_name": "P300-H-A", "manufacturer": "Farpointe Data", "part_no": "05273-333S", "supplier": "Farpointe Data", "valuation_rate": 49},
    {"item_code": "SCX4IT0015", "item_name": "Wave", "manufacturer": "RFIDeas", "part_no": "RDR-80581AK2", "supplier": "Amazon", "valuation_rate": 170},

    # -- Connectivity --
    {"item_code": "SCX4IT0050", "item_name": "Antaira WiFi Device", "manufacturer": "Antaira", "part_no": "AMS-7131", "supplier": "Antaira", "valuation_rate": 319},
    {"item_code": "SCX4IT0025", "item_name": "Cell Device", "manufacturer": "OptConnect", "part_no": "OC-4400", "supplier": "OptConnect", "valuation_rate": 774},
    {"item_code": "SCX4IT0039", "item_name": "Ethernet Cable - 2 Foot", "manufacturer": "iMBAPrice", "part_no": "6.09133E+11", "supplier": "Amazon", "valuation_rate": 1.50},
    {"item_code": "SCX4IT0026", "item_name": "WiFi Device (Link Star)", "manufacturer": "LinkStar", "part_no": "LinkStar-H68K-1432", "supplier": "Seeed Studio", "valuation_rate": 119},
    {"item_code": "SCX4IT0027", "item_name": "WiFi Power Cable", "manufacturer": "Amazon", "part_no": "LY-1658", "supplier": "Amazon", "valuation_rate": 7.19},

    # -- KVM --
    {"item_code": "SCX4IT0032", "item_name": "27\" VESA Mount", "manufacturer": "Sergeant", "part_no": "22687-01A", "supplier": "Sargent Metal", "valuation_rate": 73.70},
    {"item_code": "SCX4IT1965", "item_name": "3M Velcro", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 20.26},
    {"item_code": "SCX4IT0035", "item_name": "Asia/Europe Power Adapter (Type C)", "manufacturer": "Ceptics", "part_no": "CT-9C", "supplier": "Amazon", "valuation_rate": 9.99},
    {"item_code": "SCX4IT0034", "item_name": "China/Australia Power Adapter (Type I)", "manufacturer": "Ceptics", "part_no": "CT-16", "supplier": "Amazon", "valuation_rate": 8.99},
    {"item_code": "SCX4IT0042", "item_name": "DisplayPort CIM Adapter", "manufacturer": "Raritan", "part_no": "D2CIM-DVUSB-DP", "supplier": "KVM Switches Online", "valuation_rate": 134},
    {"item_code": "SCX4IT0047", "item_name": "DisplayPort Extension - 6 Foot", "manufacturer": "Cable Matters", "part_no": "102015-6", "supplier": "Amazon", "valuation_rate": 10.88},
    {"item_code": "SCX4IT0038", "item_name": "Ethernet Cable - 1 Foot", "manufacturer": "Monoprice", "part_no": "9795", "supplier": "Monoprice", "valuation_rate": 1.19},
    {"item_code": "SCX4IT0037", "item_name": "Ethernet Cable - 10 Foot", "manufacturer": "Monoprice", "part_no": "9811", "supplier": "Monoprice", "valuation_rate": 2.87},
    {"item_code": "SCX4IT0041", "item_name": "HDMI CIM Adapter", "manufacturer": "Raritan", "part_no": "D2CIM-DVUSB-HDMI", "supplier": "KVM Switches Online", "valuation_rate": 134},
    {"item_code": "SCX4IT0045", "item_name": "HDMI Extension - 6 Foot", "manufacturer": "Cable Matters", "part_no": "300017-6X2", "supplier": "Amazon", "valuation_rate": 6.43},
    {"item_code": "SCX4IT1973", "item_name": "HDMI to DVI Adapter", "manufacturer": "Amazon Basics", "part_no": "HL-007348", "supplier": "Amazon", "valuation_rate": 7.44},
    {"item_code": "SCX4IT0054", "item_name": "Israel/Palestine Power Adapter (Type H)", "manufacturer": "Ceptics", "part_no": "CT-14", "supplier": "Amazon", "valuation_rate": 3.90},
    {"item_code": "SCX4IT0040", "item_name": "KVM Switch", "manufacturer": "Raritan", "part_no": "DKX3-108", "supplier": "Raritan Solutions", "valuation_rate": 1974.75},
    {"item_code": "SCX4IT0060", "item_name": "Keyboard/Mouse Combo", "manufacturer": None, "part_no": None, "supplier": "Amazon", "valuation_rate": 30},
    {"item_code": "SCX4IT0029", "item_name": "Mini-PC", "manufacturer": "SimplyNUC", "part_no": "CBM1r3RB", "supplier": "SimplyNUC", "valuation_rate": 760.73},
    {"item_code": "SCX4IT0055", "item_name": "Screwdriver", "manufacturer": "Phillips", "part_no": "20209266731", "supplier": "Amazon", "valuation_rate": 4.98},
    {"item_code": "SCX4IT0031", "item_name": "SmartBox", "manufacturer": "Sergeant", "part_no": "22698-01A", "supplier": "Sargent Metal", "valuation_rate": 80.63},
    {"item_code": "SCX4IT0030", "item_name": "Touchscreen Monitor", "manufacturer": "Planar", "part_no": "PCT2785", "supplier": "Clary Business Machines", "valuation_rate": 736},
    {"item_code": "SCX4IT0053", "item_name": "UK Power Adapter (Type G)", "manufacturer": "Ceptics", "part_no": "CTR-7", "supplier": "Amazon", "valuation_rate": 3.40},
    {"item_code": "SCX4IT0033", "item_name": "US Power Strip", "manufacturer": "KMC", "part_no": "X001NF2LBN", "supplier": "Amazon", "valuation_rate": 6},
    {"item_code": "SCX4IT0046", "item_name": "USB-A Extension - 6 Foot", "manufacturer": "Cable Matters", "part_no": "200008-BLACK-6X2", "supplier": "Amazon", "valuation_rate": 5.94},
    {"item_code": "SCX4IT0043", "item_name": "USB-C CIM Adapter", "manufacturer": "Raritan", "part_no": "D2CIM-VUSB-USBC", "supplier": "KVM Switches Online", "valuation_rate": 171.75},
    {"item_code": "SCX4IT0048", "item_name": "USB-C Extension - 6 Foot", "manufacturer": "Stouchi", "part_no": "EC11", "supplier": "Amazon", "valuation_rate": 13.80},
    {"item_code": "SCX4IT0036", "item_name": "Universal Power Strip", "manufacturer": "VCT", "part_no": "USP600", "supplier": "Amazon", "valuation_rate": 34.99},

    # -- Motherboards --
    {"item_code": "SCX4IT0058", "item_name": "100-Pin Controller Board", "manufacturer": "Mirac", "part_no": "00-CONTROLLER-SM 1+", "supplier": "Mirac", "valuation_rate": 67.41},
    {"item_code": "SCX4IT0020", "item_name": "144-Pin Controller Board", "manufacturer": "Mirac", "part_no": "MIRCB-1000001", "supplier": "Mirac", "valuation_rate": 60.96},
    {"item_code": "SCX4IT0021", "item_name": "Base Board", "manufacturer": "Mirac", "part_no": "MIRBB-1000002", "supplier": "Mirac", "valuation_rate": 141},
    {"item_code": "SCX4IT0022", "item_name": "Locker Board", "manufacturer": "Mirac", "part_no": "MIRLB-1000003", "supplier": "Mirac", "valuation_rate": 132.67},
    {"item_code": "SCX4IT0550", "item_name": "Motherboard", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 208.41},
    {"item_code": "SCX4IT0023", "item_name": "Vendnovation Board", "manufacturer": "Vendnovation", "part_no": "VCBBB-1000004", "supplier": "Vendnovation", "valuation_rate": 600},

    # -- SmartScreen --
    {"item_code": "SCX4IT1325", "item_name": "External Antennas", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 11.99},
    {"item_code": "SCX4IT1245", "item_name": "RS-232 Peripheral Cable", "manufacturer": "FTDI", "part_no": "USB-RS232-WE-1800-BT 5.0", "supplier": "Amazon", "valuation_rate": 23},
    {"item_code": "SCX4IT1244", "item_name": "RS-485 Board Cable", "manufacturer": "FTDI", "part_no": "USB-RS485-WE-1800-BT", "supplier": "Amazon", "valuation_rate": 27.99},
    {"item_code": "SCX4IT1939", "item_name": "SmartScreen Back Panels", "manufacturer": "Gammons", "part_no": "22212-01A", "supplier": "Gammons", "valuation_rate": 15.62},
    {"item_code": "SCX4IT1246", "item_name": "SmartScreen Board", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 123.75},
    {"item_code": "SCX4IT1247", "item_name": "SmartScreen Touchscreen", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 126.75},
    {"item_code": "SCX4IT1925", "item_name": "Tuolink Antennas (Black)", "manufacturer": None, "part_no": None, "supplier": None, "valuation_rate": 1.86},

    # -- iPad Components (all new) --
    {"item_code": "SCX4IT1971", "item_name": "65W USB-C AC Adapter Charger", "manufacturer": "DongGuan Simer Electronics Co. LTD", "part_no": "SM65CL-01", "supplier": "Amazon", "valuation_rate": 15.19},
    {"item_code": "SCX4IT1970", "item_name": "Apple 60W USB-C", "manufacturer": "Apple", "part_no": "MW493AM/A", "supplier": "Amazon", "valuation_rate": 14.99},
    {"item_code": "SCX4IT1967", "item_name": "DB9 Female Connector", "manufacturer": "ANMBEST", "part_no": "Anmbest_MD151MAIN", "supplier": "Amazon", "valuation_rate": 3.58},
    {"item_code": "SCX4IT1966", "item_name": "DTECH RS232 to RS485 RS422 Converter", "manufacturer": "DTech", "part_no": "ADT-9003", "supplier": "Amazon", "valuation_rate": 10.72},
    {"item_code": "SCX4IT1968", "item_name": "USB-C Female to Female", "manufacturer": "AuviPal", "part_no": "USBC240FF", "supplier": "Amazon", "valuation_rate": 3.32},
    {"item_code": "SCX4IT1969", "item_name": "USB-C Hub", "manufacturer": "Anker", "part_no": "A83830A1", "supplier": "Amazon", "valuation_rate": 47.97},
    {"item_code": "SCX4IT1972", "item_name": "iPad Mount", "manufacturer": "VidaMount", "part_no": "VB_VESA_IPRO2G110_BLK", "supplier": "VidaBox", "valuation_rate": 161.67},
]


# ---------------------------------------------------------------------------
# DATA — STOCK RECONCILIATION TARGETS (per sub-warehouse)
# ---------------------------------------------------------------------------

STOCK_TARGET = {
    "Badge Readers - I": [
        ("SCX4IT1149", 17, 225),
        ("SCX4IT0028", 1, 124),
        ("SCX4IT1957", 16, 139.32),
        ("SCX4IT0056", 7, 244),
        ("SCX4IT0051", 2, 89),
        ("SCX4IT0011", 8, 164),
        ("SCX4IT0008", 37, 49),
        ("SCX4IT0015", 16, 170),
        # HID Signo 40 (SCX4IT0057) and MultiCLASS R40 (SCX4IT0010) are qty=0 — no row.
    ],
    "Connectivity - I": [
        ("SCX4IT0050", 9, 319),
        ("SCX4IT0039", 5, 1.50),
        ("SCX4IT0026", 11, 119),
        ("SCX4IT0027", 22, 7.19),
        # Cell Device (SCX4IT0025) is qty=0 in Connectivity — no row.
    ],
    "KVM - I": [
        ("SCX4IT0032", 26, 73.70),
        ("SCX4IT1965", 6, 20.26),
        ("SCX4IT0035", 5, 9.99),
        ("SCX4IT0034", 1, 8.99),
        ("SCX4IT0042", 4, 134),
        ("SCX4IT0047", 9, 10.88),
        ("SCX4IT0038", 14, 1.19),
        ("SCX4IT0037", 10, 2.87),
        ("SCX4IT0041", 3, 134),
        ("SCX4IT0045", 3, 6.43),
        ("SCX4IT1973", 5, 7.44),
        ("SCX4IT0054", 2, 3.90),
        ("SCX4IT0040", 12, 1974.75),
        ("SCX4IT0060", 1, 30),
        ("SCX4IT0029", 4, 760.73),
        ("SCX4IT0055", 7, 4.98),
        ("SCX4IT0031", 31, 80.63),
        ("SCX4IT0030", 1, 736),
        ("SCX4IT0053", 9, 3.40),
        ("SCX4IT0033", 7, 6),
        ("SCX4IT0046", 5, 5.94),
        ("SCX4IT0043", 9, 171.75),
        ("SCX4IT0048", 4, 13.80),
        # Universal Power Strip (SCX4IT0036) is qty=0 — no row.
    ],
    "Motherboards - I": [
        ("SCX4IT0058", 771, 67.41),
        ("SCX4IT0020", 31, 60.96),
        ("SCX4IT0021", 306, 141),
        ("SCX4IT0022", 120, 132.67),
        ("SCX4IT0550", 67, 208.41),
        ("SCX4IT0023", 77, 600),
    ],
    "Returned Equipment - I": [
        ("SCX4IT0025", 10, 774),
        ("SCX4IT1149", 9, 225),
        ("SCX4IT0022", 58, 132.67),
        ("SCX4IT0550", 199, 208.41),
        ("SCX4IT0008", 20, 49),
        ("SCX4IT0030", 3, 736),
        ("SCX4IT0023", 189, 600),
    ],
    "SmartScreen - I": [
        ("SCX4IT1325", 43, 11.99),
        ("SCX4IT1245", 36, 23),
        ("SCX4IT1244", 30, 27.99),
        ("SCX4IT1939", 229, 15.62),
        ("SCX4IT1246", 239, 123.75),
        ("SCX4IT1247", 211, 126.75),
        ("SCX4IT1925", 51, 1.86),
    ],
    "iPad Components - I": [
        ("SCX4IT1971", 15, 15.19),
        ("SCX4IT1970", 16, 14.99),
        ("SCX4IT1967", 15, 3.58),
        ("SCX4IT1966", 18, 10.72),
        ("SCX4IT1968", 16, 3.32),
        ("SCX4IT1969", 15, 47.97),
        ("SCX4IT1972", 8, 161.67),
    ],
}


# ---------------------------------------------------------------------------
# DATA — ITEMS TO REMOVE (currently in IT - I, not part of the Sortly list)
# ---------------------------------------------------------------------------

ITEMS_TO_DELETE = ["SCX4IT0024", "SCX4IT1242"]  # SD Card (16GB), USB-A 3 ft Extension


# ---------------------------------------------------------------------------
# PHASE 1 — SUPPLIERS
# ---------------------------------------------------------------------------

def create_suppliers():
    log("=" * 70)
    log("PHASE 1: Suppliers")
    log("=" * 70)
    created, skipped = 0, 0
    for name in SUPPLIERS:
        if frappe.db.exists("Supplier", name):
            log(f"SKIP Supplier (exists): {name}")
            skipped += 1
            continue
        log(f"CREATE Supplier: {name}")
        if not DRY_RUN:
            doc = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": name,
                "supplier_group": "All Supplier Groups",
                "supplier_type": "Company",
            })
            doc.insert(ignore_permissions=True)
            created += 1
        else:
            created += 1
    if not DRY_RUN:
        frappe.db.commit()
    log(f"Phase 1 done. created={created} skipped={skipped}")


# ---------------------------------------------------------------------------
# PHASE 2 — MANUFACTURERS
# ---------------------------------------------------------------------------

def create_manufacturers():
    log("=" * 70)
    log("PHASE 2: Manufacturers")
    log("=" * 70)
    created, skipped = 0, 0
    for name in MANUFACTURERS:
        if frappe.db.exists("Manufacturer", name):
            log(f"SKIP Manufacturer (exists): {name}")
            skipped += 1
            continue
        log(f"CREATE Manufacturer: {name}")
        if not DRY_RUN:
            doc = frappe.get_doc({
                "doctype": "Manufacturer",
                "short_name": name,
            })
            doc.insert(ignore_permissions=True)
            created += 1
        else:
            created += 1
    if not DRY_RUN:
        frappe.db.commit()
    log(f"Phase 2 done. created={created} skipped={skipped}")


# ---------------------------------------------------------------------------
# PHASE 3 — WAREHOUSES
# ---------------------------------------------------------------------------

def create_warehouses():
    log("=" * 70)
    log("PHASE 3: Warehouses")
    log("=" * 70)
    created, skipped = 0, 0
    # Tracks names that exist in the DB OR would exist after this phase completes
    # (needed in DRY_RUN, since nothing is actually written and parent lookups for
    # later entries in WAREHOUSES would otherwise falsely fail).
    known_warehouses = set()

    for entry in WAREHOUSES:
        wh_name = entry["name"]
        parent = entry["parent"]

        parent_known = frappe.db.exists("Warehouse", parent) or parent in known_warehouses
        if not parent_known:
            log(f"ERROR: parent warehouse '{parent}' does not exist yet — cannot create '{wh_name}'. Skipping.")
            continue

        if frappe.db.exists("Warehouse", wh_name):
            log(f"SKIP Warehouse (exists): {wh_name}")
            skipped += 1
            known_warehouses.add(wh_name)
            continue

        display_name = wh_name.rsplit(" - ", 1)[0]
        log(f"CREATE Warehouse: {wh_name} (parent={parent})")
        if not DRY_RUN:
            doc = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": display_name,
                "parent_warehouse": parent,
                "is_group": 0,
                "company": COMPANY,
            })
            doc.insert(ignore_permissions=True)
            if doc.name != wh_name:
                log(f"WARNING: expected warehouse name '{wh_name}' but got '{doc.name}'. "
                    f"Downstream references to '{wh_name}' will fail — investigate naming convention.")
            known_warehouses.add(doc.name)
            created += 1
        else:
            known_warehouses.add(wh_name)
            created += 1
    if not DRY_RUN:
        frappe.db.commit()
    log(f"Phase 3 done. created={created} skipped={skipped}")


# ---------------------------------------------------------------------------
# PHASE 4 — ITEMS (upsert)
# ---------------------------------------------------------------------------

def _ensure_item_manufacturer(doc, manufacturer, part_no):
    # Item has no "item_manufacturers" child table in this ERPNext version —
    # manufacturer info lives on two direct fields instead.
    if not manufacturer:
        return
    doc.default_item_manufacturer = manufacturer
    if part_no:
        doc.default_manufacturer_part_no = part_no


def _ensure_supplier_item(doc, supplier):
    if not supplier:
        return
    for row in doc.get("supplier_items", []):
        if row.supplier == supplier:
            return
    doc.append("supplier_items", {"supplier": supplier})


def upsert_items():
    log("=" * 70)
    log("PHASE 4: Items (create-or-update)")
    log("=" * 70)
    created, updated = 0, 0

    for item in ALL_ITEMS:
        code = item["item_code"]
        manufacturer = item["manufacturer"]
        # SUPPLIER_ALIASES (e.g. "Sergeant" -> "Sargent Metal") applies only to the
        # supplier field. "Sergeant" is a valid Manufacturer in its own right and must
        # NOT be remapped here.
        supplier = SUPPLIER_ALIASES.get(item["supplier"], item["supplier"]) if item["supplier"] else None

        if frappe.db.exists("Item", code):
            log(f"UPDATE Item: {code} ({item['item_name']})")
            if not DRY_RUN:
                doc = frappe.get_doc("Item", code)
                doc.valuation_rate = item["valuation_rate"]
                _ensure_item_manufacturer(doc, manufacturer, item["part_no"])
                _ensure_supplier_item(doc, supplier)
                doc.save(ignore_permissions=True)
            updated += 1
        else:
            log(f"CREATE Item: {code} ({item['item_name']})")
            if not DRY_RUN:
                doc = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": code,
                    "item_name": item["item_name"],
                    "item_group": "Raw Material",
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                    "valuation_rate": item["valuation_rate"],
                })
                # Item.autoname() unconditionally regenerates `name` from the naming
                # series when the site's "item_naming_by" default is "Naming Series",
                # ignoring any item_code we've already set. Force the exact code by
                # bypassing autoname entirely (flags.name_set short-circuits it).
                doc.name = code
                doc.flags.name_set = True
                _ensure_item_manufacturer(doc, manufacturer, item["part_no"])
                _ensure_supplier_item(doc, supplier)
                doc.insert(ignore_permissions=True)
                if doc.name != code:
                    log(f"WARNING: expected item_code '{code}' but got '{doc.name}'.")
            created += 1

    if not DRY_RUN:
        frappe.db.commit()
    log(f"Phase 4 done. created={created} updated={updated}")


# ---------------------------------------------------------------------------
# PHASE 4B — ITEM PRICES (Standard Buying)
# ---------------------------------------------------------------------------

ITEM_PRICE_LIST = "Standard Buying"


def create_item_prices():
    log("=" * 70)
    log("PHASE 4B: Item Prices (Standard Buying)")
    log("=" * 70)
    created, updated = 0, 0

    for item in ALL_ITEMS:
        code = item["item_code"]
        rate = item["valuation_rate"]

        existing_name = frappe.db.get_value(
            "Item Price",
            {"item_code": code, "price_list": ITEM_PRICE_LIST},
            "name",
        )

        if existing_name:
            log(f"UPDATE Item Price: {code} -> {rate}")
            if not DRY_RUN:
                frappe.db.set_value("Item Price", existing_name, "price_list_rate", rate)
            updated += 1
        else:
            log(f"CREATE Item Price: {code} @ {ITEM_PRICE_LIST} = {rate}")
            if not DRY_RUN:
                doc = frappe.get_doc({
                    "doctype": "Item Price",
                    "item_code": code,
                    "price_list": ITEM_PRICE_LIST,
                    "price_list_rate": rate,
                    "uom": "Nos",
                    "buying": 1,
                    "currency": "USD",
                })
                doc.insert(ignore_permissions=True)
            created += 1

    if not DRY_RUN:
        frappe.db.commit()
    log(f"Phase 4B done. created={created} updated={updated}")


# ---------------------------------------------------------------------------
# PHASE 5 — STOCK RECONCILIATION
# ---------------------------------------------------------------------------

def _chunked(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _submit_reconciliation(rows, batch_label):
    log(f"--- Submitting Stock Reconciliation batch: {batch_label} ({len(rows)} rows) ---")
    if DRY_RUN:
        for r in rows:
            log(f"    [DRY] {r['item_code']} @ {r['warehouse']}: qty={r['qty']} rate={r['valuation_rate']}")
        return True

    doc = frappe.get_doc({
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "company": COMPANY,
        "expense_account": STOCK_ADJUSTMENT_ACCOUNT,
        "cost_center": COST_CENTER,
        "items": rows,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    doc.reload()

    if doc.docstatus != 1:
        log(f"ERROR: batch '{batch_label}' did not submit synchronously (docstatus={doc.docstatus}, name={doc.name}). Aborting further batches.")
        return False

    log(f"Batch '{batch_label}' submitted successfully as {doc.name} (docstatus=1).")
    return True


def _current_bin_state(item_code, warehouse):
    row = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "valuation_rate"],
        as_dict=True,
    )
    if not row:
        return (0, 0)
    return (row.actual_qty or 0, row.valuation_rate or 0)


def _already_at_target(item_code, warehouse, qty, rate):
    cur_qty, cur_rate = _current_bin_state(item_code, warehouse)
    return cur_qty == qty and abs(cur_rate - rate) < 0.005


def reconcile_stock():
    log("=" * 70)
    log("PHASE 5: Stock Reconciliation")
    log("=" * 70)

    # --- 5a: zero-out rows for every item currently stocked in IT - I ---
    zero_out_rows = []
    bins = frappe.db.sql(
        """
        SELECT item_code, valuation_rate
        FROM `tabBin`
        WHERE warehouse = %s AND actual_qty != 0
        """,
        ("IT - I",),
        as_dict=True,
    )
    for b in bins:
        zero_out_rows.append({
            "item_code": b.item_code,
            "warehouse": "IT - I",
            "qty": 0,
            "valuation_rate": b.valuation_rate or 0,
        })
    log(f"Found {len(zero_out_rows)} items with stock in IT - I to zero out.")

    # --- 5b: populate rows for each sub-warehouse target ---
    # Skip rows already matching the current Bin state — ERPNext's own
    # remove_items_with_no_change() would strip these anyway, and if a whole
    # batch ends up empty it throws EmptyStockReconciliationItemsError instead
    # of just no-op'ing. Filtering here keeps re-runs safe once already applied.
    populate_rows = []
    already_correct = 0
    for warehouse, items in STOCK_TARGET.items():
        for item_code, qty, rate in items:
            if not DRY_RUN and _already_at_target(item_code, warehouse, qty, rate):
                already_correct += 1
                continue
            populate_rows.append({
                "item_code": item_code,
                "warehouse": warehouse,
                "qty": qty,
                "valuation_rate": rate,
            })
    log(f"Built {len(populate_rows)} populate rows across {len(STOCK_TARGET)} sub-warehouses "
        f"({already_correct} already at target, skipped).")

    all_rows = zero_out_rows + populate_rows

    if not all_rows:
        log("Nothing to reconcile — all items already at target qty/valuation. Phase 5 done (no-op).")
        return True

    log(f"Total reconciliation rows: {len(all_rows)}. Batching at {MAX_RECON_ROWS_PER_BATCH} rows/doc.")

    for idx, chunk in enumerate(_chunked(all_rows, MAX_RECON_ROWS_PER_BATCH), start=1):
        if not chunk:
            continue
        ok = _submit_reconciliation(chunk, f"batch-{idx}")
        if not ok:
            log("Aborting remaining Stock Reconciliation batches due to failure.")
            return False

    log("Phase 5 done.")
    return True


# ---------------------------------------------------------------------------
# PHASE 6 — DELETE ORPHANED ITEMS
# ---------------------------------------------------------------------------

def delete_orphaned_items():
    log("=" * 70)
    log("PHASE 6: Delete orphaned items")
    log("=" * 70)
    for code in ITEMS_TO_DELETE:
        if not frappe.db.exists("Item", code):
            log(f"SKIP delete (does not exist): {code}")
            continue

        remaining_qty = frappe.db.sql(
            "SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code = %s",
            (code,),
        )[0][0] or 0
        if remaining_qty != 0:
            log(f"ERROR: {code} still has {remaining_qty} units of stock somewhere. Not deleting. "
                f"Run Phase 5 (Stock Reconciliation) first.")
            continue

        log(f"DELETE Item: {code}")
        if not DRY_RUN:
            frappe.delete_doc("Item", code, force=True, ignore_permissions=True)
    if not DRY_RUN:
        frappe.db.commit()
    log("Phase 6 done.")


# ---------------------------------------------------------------------------
# PHASE 7 — FLIP GROUP WAREHOUSE FLAGS
# ---------------------------------------------------------------------------

def set_group_flags():
    log("=" * 70)
    log("PHASE 7: Convert IT - I and Cage - I to group warehouses")
    log("=" * 70)
    for wh in GROUP_WAREHOUSES_TO_FLIP:
        qty = frappe.db.sql(
            "SELECT SUM(actual_qty) FROM `tabBin` WHERE warehouse = %s",
            (wh,),
        )[0][0] or 0
        if qty != 0:
            log(f"ERROR: warehouse '{wh}' still holds {qty} units of stock. Not converting to group. "
                f"Run Phase 5 (Stock Reconciliation) first.")
            continue

        log(f"SET is_group=1 on warehouse: {wh}")
        if not DRY_RUN:
            frappe.db.set_value("Warehouse", wh, "is_group", 1)
    if not DRY_RUN:
        frappe.db.commit()
        frappe.clear_cache()
    log("Phase 7 done.")


# ---------------------------------------------------------------------------
# VERIFICATION
# ---------------------------------------------------------------------------

def verify():
    log("=" * 70)
    log("VERIFICATION")
    log("=" * 70)

    for wh in ["IT - I", "Cage - I"]:
        row = frappe.db.get_value("Warehouse", wh, ["is_group"], as_dict=True)
        log(f"Warehouse {wh}: is_group={row.is_group if row else 'MISSING'}")

    for wh in STOCK_TARGET.keys():
        total = frappe.db.sql(
            "SELECT COUNT(*), SUM(actual_qty), SUM(actual_qty * valuation_rate) FROM `tabBin` WHERE warehouse=%s AND actual_qty != 0",
            (wh,),
        )[0]
        log(f"Warehouse {wh}: {total[0]} items, {total[1]} total qty, ${total[2]:.2f} total value" if total[0] else f"Warehouse {wh}: no stock")

    it_qty = frappe.db.sql("SELECT SUM(actual_qty) FROM `tabBin` WHERE warehouse='IT - I'")[0][0] or 0
    log(f"IT - I remaining qty (should be 0): {it_qty}")

    log(f"Supplier count: {frappe.db.count('Supplier')}")
    log(f"Manufacturer count: {frappe.db.count('Manufacturer')}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    log("#" * 70)
    log(f"IT INVENTORY SETUP — DRY_RUN={DRY_RUN}")
    log("#" * 70)

    create_suppliers()
    create_manufacturers()
    create_warehouses()
    upsert_items()
    create_item_prices()
    recon_ok = reconcile_stock()
    if recon_ok:
        delete_orphaned_items()
        set_group_flags()
    else:
        log("Skipping Phase 6/7 because Stock Reconciliation did not complete cleanly.")

    verify()

    log("#" * 70)
    log("COMPLETE" if not DRY_RUN else "DRY RUN COMPLETE — set DRY_RUN = False to execute for real")
    log("#" * 70)


main()
