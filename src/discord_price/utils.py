from datetime import datetime, timezone

def get_utc_time():
    """Format current time in UTC"""
    now = datetime.now(timezone.utc)
    return now.strftime("%I:%M %p UTC")

def to_all_strings(d: dict) -> dict:
    """Convert dictionary of strings->ints into strings->decimal-integer-strings"""
    return {k: str(v) for k, v in d.items()}

def to_all_ints(d: dict) -> dict:
    """Convert dictionary of strings->decimal-integer-strings into strings->ints"""
    return {k: int(v) for k, v in d.items()}
