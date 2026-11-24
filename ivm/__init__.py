__version__ = "0.0.1"

from ivm.overrides.communication import apply as _apply_communication_get_emails_fix
from ivm.overrides.queue_overload_fix import apply as _apply_queue_overload_fix

_apply_queue_overload_fix()
_apply_communication_get_emails_fix()
