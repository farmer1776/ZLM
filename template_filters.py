from datetime import datetime

from markupsafe import Markup


STATUS_BADGE_CLASSES = {
    'active': 'bg-success',
    'locked': 'bg-warning text-dark',
    'closed': 'bg-danger',
    'pending_purge': 'bg-info',
    'purged': 'bg-secondary',
}


def status_badge(status):
    """Render status as a colored Bootstrap badge."""
    if not status:
        return ''
    css_class = STATUS_BADGE_CLASSES.get(status, 'bg-secondary')
    label = status.replace('_', ' ').title()
    return Markup(f'<span class="badge {css_class}">{label}</span>')


def filesizeformat_binary(value):
    """Format bytes to human-readable size."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def timesince(value):
    """Return a human-readable time difference from now."""
    if value is None:
        return ''
    now = datetime.utcnow()
    if hasattr(value, 'replace'):
        # Make naive for comparison
        try:
            value = value.replace(tzinfo=None)
        except (TypeError, AttributeError):
            pass
    diff = now - value
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return f"{seconds} seconds"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''}"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''}"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''}"


def timeuntil(value):
    """Return a human-readable time until a future datetime (e.g., 'in 3 hours')."""
    if value is None:
        return ''
    now = datetime.utcnow()
    if hasattr(value, 'replace'):
        try:
            value = value.replace(tzinfo=None)
        except (TypeError, AttributeError):
            pass
    diff = value - now
    seconds = int(diff.total_seconds())

    if seconds <= 0:
        return 'now'
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def dateformat(value, fmt='%m-%d-%Y'):
    """Format a datetime using strftime."""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(fmt)
    return str(value)
