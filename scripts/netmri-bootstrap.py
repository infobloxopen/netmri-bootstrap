#!/usr/bin/python3
import os
import sys
import argparse
import logging

from netmri_bootstrap.bootstrapper import Bootstrapper

def initialize_logging(args):
    loglevel = logging.INFO
    # Every -q will increase loglevel by 10.
    # Every -v will decrease loglevel by 10.
    # -v -v -v -q -q will decrease loglevel by 10 (-30 + 20)
    loglevel += (args.q - args.v) * 10
    # Set upper and lower limits on loglevel
    if loglevel < logging.NOTSET:
        loglevel = logging.NOTSET
    if loglevel > logging.CRITICAL:
        loglevel = logging.CRITICAL

    # Hide debug info from external libs on DEBUG level
    # This output will be shown at lower loglevel
    if loglevel == logging.DEBUG:
        for lib in ["urllib3", "git", "requests"]:
            logging.getLogger(lib).setLevel(logging.INFO)

    log_format = logging.BASIC_FORMAT
    # Remove extra info from log messages when loglevel is INFO or above
    if loglevel >= logging.INFO:
        log_format = "%(message)s"
    logging.basicConfig(stream=sys.stdout, level=loglevel, format=log_format)

def parse_cmdline_args():
    parser = argparse.ArgumentParser(description="netmri-bootstrap")
    commands = ["init", "push", "check"]
    commands_help = """
    Can be one of three operations:
    init: create empty repository and fill it with data from server
    push: update scripts in the repo from server
    check: verify that repo and the server are in sync
    """
    parser.add_argument("command", help=commands_help, choices=commands)

    parser.add_argument("-q", help="Quiet logging. Can be repeated to suppress more messages", action='count', default=0)
    parser.add_argument("-v", help="Verbose logging. Can be repeated to increase verbosity", action='count', default=0)
    parser.add_argument("-n", help="Dry run", action='store_true')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cmdline_args()
    initialize_logging(args)

    if args.command == "init":
        bs = Bootstrapper.init_empty_repo()
        bs.export_from_netmri()
    elif args.command == "push":
        bs = Bootstrapper()
        bs.update_netmri()
    elif args.command == "check":
        bs = Bootstrapper()
        bs.check_netmri()
    else:
        # We don't expect to get here because of argparse
        pass
