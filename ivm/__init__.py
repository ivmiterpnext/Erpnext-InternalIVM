
__version__ = '0.0.1'
try:
  from frappe.email.doctype.email_account.email_account import EmailAccount
  from ivm.api import send_auto_reply


  EmailAccount.send_auto_reply = send_auto_reply
except (ModuleNotFoundError, ImportError):
  pass
