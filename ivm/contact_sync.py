"""
Contact Sync - Ongoing sync between Frappe Contacts and MSSQL
Triggered by doc events on Contact creation/update
"""

import frappe
import pyodbc

# TODO: Replace this with API calls using MSSQL_FRAPPE module, probably time to merge it with IVM project
def _get_conn():
    """Get MSSQL connection using site config."""
    cfg = frappe.get_site_config()
    host = cfg.get("mssql_host")
    db = cfg.get("mssql_db")
    user = cfg.get("mssql_user")
    pw = cfg.get("mssql_password")
    encrypt = "yes" if int(cfg.get("mssql_encrypt", 1)) else "no"
    trust = "yes" if int(cfg.get("mssql_trust_cert", 0)) else "no"

    if not all([host, db, user, pw]):
        frappe.log_error("Missing MSSQL config in site_config.json", "Contact Sync")
        return None

    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={host};"
        f"Database={db};"
        f"UID={user};PWD={pw};"
        f"Encrypt={encrypt};TrustServerCertificate={trust};"
        "Connection Timeout=30;"
    )
    
    try:
        return pyodbc.connect(conn_str)
    except Exception as e:
        frappe.log_error(f"MSSQL connection failed: {str(e)}", "Contact Sync")
        return None


def sync_contact_to_mssql(doc, method=None):
    """
    Triggered after Contact insert.
    Creates contact in MSSQL and updates custom_css_contact_id.
    """
    # Skip if already has MSSQL ID
    if doc.custom_css_contact_id:
        return
    
    # Skip if sync is disabled
    if not frappe.get_site_config().get("enable_mssql_contact_sync", True):
        return

    conn = _get_conn()
    if not conn:
        return

    try:
        cur = conn.cursor()
        
        # Insert into base Contact table - will auto-appear in canonical view
        sql = """
        INSERT INTO dbo.tbl_PTL_Contact (EmailAddress, Phone1, FirstName, LastName)
        OUTPUT INSERTED.RID
        VALUES (?, ?, ?, ?)
        """
        
        cur.execute(sql, (
            doc.email_id,
            doc.phone or doc.mobile_no,
            doc.first_name or "Unknown",
            doc.last_name or ""
        ))
        
        # Get the new CanonicalRID
        row = cur.fetchone()
        new_canonical_rid = row[0] if row else None
        
        conn.commit()
        
        # Update Frappe doc with the new ID
        if new_canonical_rid:
            frappe.db.set_value("Contact", doc.name, "custom_css_contact_id", new_canonical_rid)
            frappe.logger().info(f"Contact {doc.name} synced to MSSQL with CanonicalRID={new_canonical_rid}")
            
    except Exception as e:
        frappe.log_error(f"Failed to sync Contact {doc.name} to MSSQL: {str(e)}", "Contact Sync")
    finally:
        conn.close()


def update_contact_in_mssql(doc, method=None):
    """
    Triggered on Contact update.
    Updates contact in MSSQL if custom_css_contact_id is set.
    """
    # Skip if no MSSQL ID
    if not doc.custom_css_contact_id:
        return
    
    # Skip if sync is disabled
    if not frappe.get_site_config().get("enable_mssql_contact_sync", True):
        return

    # Only update if certain fields changed
    if not doc.has_value_changed("email_id") and \
       not doc.has_value_changed("phone") and \
       not doc.has_value_changed("mobile_no") and \
       not doc.has_value_changed("first_name") and \
       not doc.has_value_changed("last_name"):
        return

    conn = _get_conn()
    if not conn:
        return

    try:
        cur = conn.cursor()
        
        # Update base Contact table using the RID stored in custom_css_contact_id
        sql = """
        UPDATE dbo.tbl_PTL_Contact
        SET EmailAddress = ?,
            Phone1 = ?,
            FirstName = ?,
            LastName = ?
        WHERE RID = ?
        """
        
        cur.execute(sql, (
            doc.email_id,
            doc.phone or doc.mobile_no,
            doc.first_name or "Unknown",
            doc.last_name or "",
            doc.custom_css_contact_id
        ))
        
        conn.commit()
        frappe.logger().info(f"Contact {doc.name} updated in MSSQL (CanonicalRID={doc.custom_css_contact_id})")
        
    except Exception as e:
        frappe.log_error(f"Failed to update Contact {doc.name} in MSSQL: {str(e)}", "Contact Sync")
    finally:
        conn.close()
