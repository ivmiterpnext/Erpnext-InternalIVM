
__version__ = '0.0.1'

def setup_monkey_patches():
	from frappe.email.doctype.email_account.email_account import EmailAccount
	from ivm.api import send_auto_reply
	
	EmailAccount.send_auto_reply = send_auto_reply

try:
	setup_monkey_patches()
except ImportError:
	# During installation, frappe might not be available yet
	pass