#!/usr/bin/python3
import os
import sys
import argparse
import logging

from netmri_bootstrap import Bootstrapper
from netmri_bootstrap import dryrun

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

    # Global arguments
    parser.add_argument("-q", help="Quiet logging. Can be repeated to suppress more messages", action='count', default=0)
    parser.add_argument("-v", help="Verbose logging. Can be repeated to increase verbosity", action='count', default=0)

    # arguments for subcommands
    subparsers = parser.add_subparsers(help="Possible subcommands", dest="command")

    parser_init = subparsers.add_parser("init", help="Create empty repository and fill it with data from server")

    parser_check = subparsers.add_parser("check", help="Verify that repo and the server are in sync")

    parser_push = subparsers.add_parser("push", help="update objects on server from the repo ")
    parser_push.add_argument("--retry-errors", help="Attempt to sync previously failed objects", action='store_true')
    parser_push.add_argument("--dry-run", dest="dryrun", help="Preview changes that will be made to server", action='store_true')
    parser_push.add_argument("paths", type=str, help="Paths to sync", nargs='*')

    parser_cat = subparsers.add_parser("cat", help="Show object contents in repo or on server")
    parser_cat.add_argument("--api", dest="api", help="Get object content from server", action='store_true')
    parser_cat.add_argument("path", type=str, help="Path to the object")

    parser_relink = subparsers.add_parser("sync_id", help="Get id from server based on secondary key (usually name)")
    parser_relink.add_argument("--dry-run", dest="dryrun", help="Don't make changes in the repo", action='store_true')
    parser_relink.add_argument("path", type=str, help="Path to the object")

    parser_show = subparsers.add_parser("show_metadata", help="show metadata for the object")
    parser_show.add_argument("path", type=str, help="Path to the object")

    parser_show = subparsers.add_parser("fetch", help="Get file from server and store it in the repository")
    parser_show.add_argument("path", type=str, help="Path to the object. Every object must be in its class subdir (e.g. all scripts must be in scrpts/ directory)")
    parser_show.add_argument("--id", type=int, help="Id. Optional for objects already in repo", default=None)
    parser_show.add_argument("--overwrite", help="Allow overwriting of existing file, if file in repo has different id", action="store_true")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cmdline_args()
    initialize_logging(args)

    if args.command == "init":
        bs = Bootstrapper.init_empty_repo()
        bs.export_from_netmri()
    elif args.command == "push":
        dryrun.set_dryrun(args.dryrun)
        bs = Bootstrapper()
        if len(args.paths) == 0:
            bs.update_netmri(retry_errors=args.retry_errors)
        else:
            bs.force_push(args.paths)
    elif args.command == "check":
        dryrun.set_dryrun(args.dryrun)
        bs = Bootstrapper()
        bs.check_netmri()
    elif args.command == "check":
        dryrun.set_dryrun(args.dryrun)
        bs = Bootstrapper()
        bs.check_netmri()
    elif args.command == "cat":
        bs = Bootstrapper()
        bs.cat_file(args.path, from_api=args.api)
    elif args.command == "show_metadata":
        bs = Bootstrapper()
        bs.show_metadata(args.path)
    elif args.command == "sync_id":
        dryrun.set_dryrun(args.dryrun)
        bs = Bootstrapper()
        bs.relink(args.path)
    elif args.command == "fetch":
        bs = Bootstrapper()
        bs.fetch(args.path, id=args.id, overwrite=args.overwrite)
    else:
        # We don't expect to get here because of argparse
        pass
