from django.conf import settings


RESERVED_MESSAGES_HANDLE = "messages"
RESERVED_SETTINGS_HANDLE = "settings"


def _first_path_segment(path):
    normalized = str(path or "").strip().strip("/")
    if not normalized:
        return ""
    return normalized.split("/", 1)[0].strip().lower()


def reserved_handles():
    handles = {RESERVED_MESSAGES_HANDLE, RESERVED_SETTINGS_HANDLE}

    admin_segment = _first_path_segment(getattr(settings, "ADMIN_URL", "/admin/"))
    if admin_segment:
        handles.add(admin_segment)

    return handles


def is_reserved_handle(handle):
    normalized = str(handle or "").strip().lower()
    return normalized in reserved_handles()
