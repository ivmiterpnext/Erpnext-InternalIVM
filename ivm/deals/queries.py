"""
Server-side query helpers for CRM Deal customizations.
"""

import frappe


@frappe.whitelist()
def get_statuses_for_pipeline(doctype, txt, searchfield, start, page_len, filters):
    """
    Return CRM Deal Status records that belong to the given pipeline
    or have no pipeline assigned (shared statuses like Won / Lost).

    Used as a ``set_query`` callback on the CRM Deal status Link field.
    """
    start = int(start)
    page_len = int(page_len)
    pipeline = filters.get("pipeline")

    if not pipeline:
        # No pipeline filter — return all statuses (standard search)
        return frappe.db.sql(
            """
            SELECT name
            FROM `tabCRM Deal Status`
            WHERE name LIKE %(txt)s
            ORDER BY name
            LIMIT %(page_len)s OFFSET %(start)s
            """,
            {"txt": f"%{txt}%", "page_len": page_len, "start": start},
        )

    return frappe.db.sql(
        """
        SELECT ds.name
        FROM `tabCRM Deal Status` ds
        WHERE ds.name LIKE %(txt)s
          AND (
            EXISTS (
              SELECT 1 FROM `tabAssigned CRM Deal Status Pipeline` dsp
              WHERE dsp.parent = ds.name
                AND dsp.parenttype = 'CRM Deal Status'
                AND dsp.pipeline = %(pipeline)s
            )
            OR NOT EXISTS (
              SELECT 1 FROM `tabAssigned CRM Deal Status Pipeline` dsp
              WHERE dsp.parent = ds.name
                AND dsp.parenttype = 'CRM Deal Status'
            )
          )
        ORDER BY ds.name
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        {"txt": f"%{txt}%", "pipeline": pipeline, "page_len": page_len, "start": start},
    )
