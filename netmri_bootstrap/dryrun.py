import functools
import logging
logger = logging.getLogger(__name__)

_dryrun = False


def set_dryrun(dryrun):
    global _dryrun
    _dryrun = dryrun


def get_dryrun():
    return _dryrun


def check_dryrun(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if get_dryrun():
            logger.debug(f"NOT calling {func.__name__} because dryrun is enabled")
            return None
        else:
            return func(*args, **kwargs)
    return wrapper
