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

    logging.basicConfig(stream=sys.stdout, level=loglevel)

def parse_cmdline_args():
    parser = argparse.ArgumentParser(description="netmri-bootstrap")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--init_repo", help="Create empty repository and fetch scripts", action='store_true')
    operation.add_argument("--update_netmri", help="update scripts on NetMRI from git repo", action='store_true')

    parser.add_argument("-q", help="Quiet logging. Can be repeated to suppress more messages", action='count', default=0)
    parser.add_argument("-v", help="Verbose logging. Can be repeated to increase verbosity", action='count', default=0)
    parser.add_argument("-n", help="Dry run", action='store_true')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cmdline_args()
    initialize_logging(args)

    if args.init_repo:
        bs = Bootstrapper.init_empty_repo()
        bs.export_from_netmri()
    else:
        bs = Bootstrapper()
        bs.update_netmri()
