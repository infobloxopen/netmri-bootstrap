#!/usr/bin/python3
import os
import argparse

from netmri_bootstrap.bootstrapper import Bootstrapper

def parse_cmdline_args():
    parser = argparse.ArgumentParser(description="netmri-bootstrap")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--init_repo", help="Create empty repository and fetch scripts", action='store_true')
    operation.add_argument("--update_netmri", help="update scripts on NetMRI from git repo", action='store_true')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cmdline_args()

    if args.init_repo:
        bs = Bootstrapper.init_empty_repo()
        bs.export_from_netmri()
    else:
        bs = Bootstrapper()
        bs.update_netmri()
