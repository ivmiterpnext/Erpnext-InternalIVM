"""
Populate module='IVM' on all unmodule'd customization records.

Tags Custom Fields, Property Setters, Client Scripts, and Server Scripts
with module='IVM', excluding known non-IVM records (UAE Regional fields,
LMS User fields, known singletons).

This patch ensures all IVM-owned customizations are properly attributed
to the IVM module for fixture export and dependency tracking.
"""

import frappe

# UAE Regional fieldnames (authoritative: from erpnext/regional/united_arab_emirates/setup.py)
UAE_FIELDNAMES = [
	"company_trn",
	"vat_emirate",
	"tourist_tax_return",
	"vat_section",
	"permit_no",
	"supplier_name_in_arabic",
	"customer_name_in_arabic",
	"emirate",
	"tax_amount",
	"tax_code",
	"tax_rate",
	"total_amount",
	"is_exempt",
	"is_zero_rated",
	"reverse_charge",
	"recoverable_reverse_charge",
	"recoverable_standard_rated_expenses",
	"delivery_date",
]

# LMS fieldnames on User (authoritative: from lms/fixtures/custom_field.json)
LMS_USER_FIELDNAMES = [
	"country",
	"verify_terms",
	"user_category",
	"cover_image",
	"open_to",
	"linkedin",
	"github",
	"twitter",
	"medium",
	"profession",
	"hide_private",
	"education_details",
	"education",
	"work_experience_details",
	"work_experience",
	"internship",
	"certification_details",
	"certification",
	"skill_details",
	"skill",
	"carrer_preference_details",
	"preferred_functions",
	"preferred_location",
	"career_preference_column",
	"preferred_industries",
	"dream_companies",
	"work_environment",
	"attire",
	"collaboration",
	"role",
	"work_environment_column",
	"location_preference",
	"time",
	"company_type",
	"headline",
	"city",
	"college",
	"branch",
]


def execute():
	# --- Custom Fields ---
	# Tag all Custom Fields as IVM EXCEPT provably-not-ivm records (UAE Regional, LMS, known singletons)
	uae_placeholders = ", ".join(["%s"] * len(UAE_FIELDNAMES))
	lms_placeholders = ", ".join(["%s"] * len(LMS_USER_FIELDNAMES))

	frappe.db.sql(
		"""
		UPDATE `tabCustom Field`
		SET module = 'IVM'
		WHERE (module IS NULL OR module = '')
		  AND fieldname NOT IN ({uae})
		  AND NOT (dt = 'User' AND fieldname IN ({lms}))
		  AND NOT (dt = 'Sales Stage' AND fieldname = 'percentage')
		  AND NOT (dt = 'Warehouse Request' AND fieldname = 'account')
		""".format(uae=uae_placeholders, lms=lms_placeholders),
		UAE_FIELDNAMES + LMS_USER_FIELDNAMES,
	)

	tagged_cf = frappe.db.count("Custom Field", {"module": "IVM"})
	print(f"Custom Fields tagged module=IVM: {tagged_cf}")

	# --- Property Setters ---
	# All 390 are ivm-owned — no other installed app claims any Property Setter
	frappe.db.sql(
		"""
		UPDATE `tabProperty Setter`
		SET module = 'IVM'
		WHERE module IS NULL OR module = ''
		"""
	)

	tagged_ps = frappe.db.count("Property Setter", {"module": "IVM"})
	print(f"Property Setters tagged module=IVM: {tagged_ps}")

	# --- Client Scripts ---
	# All 21 are ivm-owned
	frappe.db.sql(
		"""
		UPDATE `tabClient Script`
		SET module = 'IVM'
		WHERE module IS NULL OR module = ''
		"""
	)

	tagged_cs = frappe.db.count("Client Script", {"module": "IVM"})
	print(f"Client Scripts tagged module=IVM: {tagged_cs}")

	# --- Server Scripts ---
	# All except 'Created Date' (confirmed zombie — broken script body, deleted by a separate patch)
	frappe.db.sql(
		"""
		UPDATE `tabServer Script`
		SET module = 'IVM'
		WHERE (module IS NULL OR module = '')
		  AND name != 'Created Date'
		"""
	)

	tagged_ss = frappe.db.count("Server Script", {"module": "IVM"})
	print(f"Server Scripts tagged module=IVM: {tagged_ss}")

	frappe.db.commit()
