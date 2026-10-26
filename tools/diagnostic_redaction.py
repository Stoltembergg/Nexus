"""Best-effort redaction for explicitly selected diagnostic text, not credentials storage.

Never treat automated redaction as permission to publish a report without review.
"""
import re
from pathlib import Path

REDACTED = '<redacted>'
SENSITIVE = re.compile(
    r'(?:^|[-_.])(?:auth|authorization|authentication|token|secret|password|passwd|'
    r'credential|credentials|cookie|bearer|api[-_]?key|puuid|riot[-_]?id|'
    r'account[-_]?id|session[-_]?id)(?:$|[-_.])', re.I)
FIELD = re.compile(
    r'(?P<prefix>(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)["\']?\s*[:=]\s*)'
    r'(?P<value>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s,;&}\]]+)')
ARGUMENT = re.compile(r'(?P<flag>--[A-Za-z0-9_.-]+)(?P<space>[ \t]+)'
                      r'(?P<value>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s]+)')
HEADER = re.compile(r'^(\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)[^\r\n]*',
                    re.I | re.M)
PRIVATE_KEY = re.compile(r'-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----.*?-----END \1-----', re.S)
URL_SECRET = re.compile(
    r'([?&](?:access_token|refresh_token|id_token|token|code|state|session_id|api_key)=)'
    r'[^&#\s"\']*', re.I)
EMAIL = re.compile(r'\b[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b')


def sensitive_key(key):
    separated = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', key)
    return SENSITIVE.search(separated.lstrip('-')) is not None


def replacement(value):
    if value.startswith(('"', "'")):
        return value[0] + REDACTED + value[0]
    return REDACTED


def redact_text(text, private_paths=()):
    """Remove common auth fields, URL credentials, email addresses and local paths.

    No function can recognize every arbitrary identifier or secret in free text.
    Unknown identifiers and unlabelled strings require manual review.
    """
    text = PRIVATE_KEY.sub(REDACTED, text)
    text = HEADER.sub(lambda m: m[1] + REDACTED, text)
    text = re.sub(r'\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]+',
                  lambda m: m[1] + ' ' + REDACTED, text, flags=re.I)
    text = re.sub(r'(https?://)[^\s/@]+@', r'\1' + REDACTED + '@', text, flags=re.I)
    text = URL_SECRET.sub(lambda m: m[1] + REDACTED, text)
    text = FIELD.sub(lambda m: m['prefix'] + replacement(m['value'])
                    if sensitive_key(m['key']) else m[0], text)
    text = ARGUMENT.sub(lambda m: m['flag'] + m['space'] + replacement(m['value'])
                       if sensitive_key(m['flag']) else m[0], text)
    text = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', REDACTED, text)
    text = re.sub(r'\bgh[pousr]_[A-Za-z0-9_]{20,}\b', REDACTED, text)
    text = EMAIL.sub('<email>', text)
    paths = {str(Path.home()): '~'}
    paths.update({str(path): '<path>' for path in private_paths if path})
    for path, label in sorted(paths.items(), key=lambda item: len(item[0]), reverse=True):
        if path not in ('', '.', '/'):
            text = text.replace(path, label)
    # Also mask other machines' Unix home paths when a log was copied here.
    return re.sub(r'/(?:home|Users)/[^/\s"\']+', '/<home>', text)
