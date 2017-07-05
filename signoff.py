#!/usr/bin/python
import os
import sys
import json
import argparse
import subprocess
import configparser
from http import cookiejar

import requests


HOME = os.path.expanduser("~")
CONFIG_DIR = os.environ.get('XDG_CONFIG_DIR', HOME+'/.config')+"/archweb"
CACHE_DIR = os.environ.get('XDG_CACHE_DIR', HOME+"/.cache")+"/archweb"

USERNAME = None
PASSWORD = None
CONFIG = configparser.ConfigParser()

os.makedirs(CACHE_DIR, exist_ok=True)
for paths in ["/cookies", "/signoff-content-length", "/packages.json"]:
    open(CACHE_DIR+paths, "a")

if os.path.isfile(CONFIG_DIR+"/archweb.conf"):
    CONFIG.read(CONFIG_DIR+"/archweb.conf")
else:
    sys.exit("Missing config file")

try:
    USERNAME = os.environ.get("ARCHWEB_USER", CONFIG["User"]["Username"])
except KeyError:
    sys.exit("No username")

try:
    PASSWORD = os.environ.get("ARCHWEB_PASSWORD", CONFIG["User"]["Password"])
except KeyError:
    sys.exit("No password")


class Session:
    def __init__(self):
        self.url = "https://www.archlinux.org/login/"
        self.signoff_page = "https://www.archlinux.org/packages/signoffs/json/"
        self.client = requests.session()
        self.client.headers.update({"Accept-Encoding": ""})
        cj = cookiejar.LWPCookieJar(CACHE_DIR+"/cookies")
        try:
            cj.load(ignore_discard=True)
        except:
            pass
        self.client.cookies = cj

    def _login(self):
        self.client.get(self.url)
        csrftoken = self.client.cookies._cookies["www.archlinux.org"]["/"]["csrftoken"].value

        login_data = {"username": USERNAME,
                      "password": PASSWORD,
                      "csrfmiddlewaretoken": csrftoken}

        r = self.client.post(self.url, data=login_data, headers={
                                "referer": "https://www.archlinux.org/login",
                                "origin": "https://www.archlinux.org"})
        if r.status_code != 200:
            sys.exit("Login failed")
        self.client.cookies.save()

    def recache_packages(self, packages):
        for pkg in packages[:]:
            if pkg['signoffs']:
                pkg['short_signoffs'] = [i['user']+' (revoked)' if i['revoked'] else i['user'] for i in pkg['signoffs']]
            else:
                pkg['short_signoffs'] = []
            pkg['repo'] = pkg['repo'].lower()
            if not (pkg['arch'] in CONFIG["Architectures"] and pkg['target_repo'].lower() in CONFIG["Repositories"]):
                packages.remove(pkg)
        with open(CACHE_DIR+"/packages.json", "r+") as f:
                f.seek(0)
                f.write(json.dumps(packages))
                f.truncate()
        return packages

    def signoff(self, package):
        url = "https://www.archlinux.org/packages/{repo}/{arch}/{pkgbase}/signoff/"
        r = self.client.get(url.format(**package))
        return r.status_code == 200

    def revoke(self, package):
        url = "https://www.archlinux.org/packages/{repo}/{arch}/{pkgbase}/signoff/revoke/"
        r = self.client.get(url.format(**package))
        return r.status_code == 200

    def get_packages_from_cache(self):
        return json.load(open(CACHE_DIR+"/packages.json"))

    def get_packages(self, tries=0):
        r = 0
        for i in range(2):
            try:
                r = self.client.head(self.signoff_page)
            except:
                sys.exit("Connection error")
            if r.headers['content-length'] == "0":
                self._login()
                continue
            break
        else:
            sys.exit("Could not login")

        # Check content-length before request the whole webpage
        # If its the same lenth, we assume same content and load
        # packages from cache
        # Hopefully this decreases load...
        with open(CACHE_DIR+"/signoff-content-length", "r+") as f:
            length = f.readline()
            if length != str(r.headers['content-length']):
                f.seek(0)
                f.write(r.headers['content-length'])
                f.truncate()
                try:
                    r = self.client.get(self.signoff_page)
                except:
                    sys.exit("Connection error")
                return self.recache_packages(r.json()['signoff_groups'])
        try:
            return self.get_packages_from_cache()
        except json.JSONDecodeError:
            try:
                r = self.client.get(self.signoff_page)
            except:
                sys.exit("Connection error")
            return self.recache_packages(r.json()['signoff_groups'])


SESSION = Session()


def approvals(args, pkg):
    if args.filter and args.filter != pkg["approved"]:
        return
    if args.user and args.user not in pkg["short_signoffs"]:
        return
    fmt = "{pkgbase} :: {version} -> {approved}"
    print(fmt.format(**pkg))


def signoffs(args, pkg):
    fmt = "{pkgbase} :: {version} -> {short_signoffs}"
    pkg["short_signoffs"] = ", ".join(pkg["short_signoffs"])
    print(fmt.format(**pkg))


def note(args, pkg):
    fmt = "{pkgbase} -> {comments}"
    print(fmt.format(**pkg))


def args_func(args):
    pkgs = SESSION.get_packages()
    if args.package:
        for pkg in pkgs:
            if pkg["pkgbase"] == args.package:
                return args.format(args, pkg)
        return print("Package is not in testing :)")
    for pkg in pkgs:
        args.format(args, pkg)


_installed_packages = None
def get_installed_packages():
    global _installed_packages
    if _installed_packages is not None:
        return _installed_packages
    cmd = """pacman -Sl testing community-testing multilib-testing 2>/dev/null |
             awk '/\[installed\]$/ { print $2 }' |
             awk '{b=( ($1=="(null)") ? $2 : $1); print b}' |
             uniq"""
    _installed_packages = subprocess.getoutput(cmd).split("\n")
    return _installed_packages


def approve(pkg):
    packages = SESSION.get_packages()
    installed_packages = get_installed_packages()
    for pkg in packages:
        if pkg["pkgbase"] != args.package:
            continue
        if pkg["pkgbase"] not in installed_packages:
            continue
        if USERNAME in pkg["short_signoffs"]:
            print("Allready signed off on this package!")
            continue
        fmt = "Signoff on {pkgbase} {version}? [y/N]: "
        inn = input(fmt.format(**pkg)).lower()
        if inn == "y":
            SESSION.signoff(pkg)
            print("Signed off")
        else:
            return print("Nothing signed off")


def revoke(args):
    packages = SESSION.get_packages()
    installed_packages = get_installed_packages()
    for pkg in packages:
        if pkg["pkgbase"] != args.package:
            continue
        if pkg["pkgbase"] not in installed_packages:
            continue
        if USERNAME not in pkg["short_signoffs"]:
            print("You haven't signed off on this package!")
            continue
        fmt = "Revoke signoff on {pkgbase} {version}? [y/N]: "
        inn = input(fmt.format(**pkg)).lower()
        if inn == "y":
            SESSION.revoke(pkg)
            print("Revoked signoff")
        else:
            return print("Nothing revoked")


def main(args):
    packages = SESSION.get_packages()
    installed_packages = get_installed_packages()

    for pkg in packages:
        if pkg["pkgbase"] not in installed_packages:
            continue
        if USERNAME in pkg["short_signoffs"]:
            continue
        fmt = "{pkgbase} :: {version} :: {last_update} :: {comments}"
        pkg["comments"] = pkg["comments"].split("\n")[0]
        print(fmt.format(**pkg))


if __name__ == "__main__":

    desc = 'signoff - Archweb signoff helper'
    parser = argparse.ArgumentParser(description=desc)
    parser.set_defaults(func=main)
    subparsers = parser.add_subparsers(title="subcommands",
                                       metavar='<command>')

    # Note
    sub_note = subparsers.add_parser('note',
                                     description=note.__doc__,
                                     help='list package notes')
    sub_note.add_argument("package", metavar="pkg",
                          nargs="?",
                          default="",
                          help="Package from testing")
    sub_note.set_defaults(format=note)

    # Approvals
    sub_approvals = subparsers.add_parser('approvals',
                                        description=approvals.__doc__,
                                        help='list package approvals')
    sub_approvals.add_argument("package", metavar="pkg",
                             nargs="?",
                             default="",
                             help="Package from testing")
    sub_approvals.add_argument("-f", dest="filter",
                             metavar="{Yes, No}",
                             choices=["Yes", "No"],
                             help="Filter approval status")
    sub_approvals.add_argument("-u", dest="user",
                             metavar="USER",
                             help="User that has signed off")
    sub_approvals.set_defaults(format=approvals)


    # Signoffs
    sub_signoffs = subparsers.add_parser('signoffs',
                                         description=signoffs.__doc__,
                                         help='list package signoffs')
    sub_signoffs.add_argument("package", metavar="pkg",
                              nargs="?",
                              default="",
                              help="Package from testing")
    sub_signoffs.set_defaults(format=signoffs)

    # Approve
    sub_approve = subparsers.add_parser('approve',
                                         description=approve.__doc__,
                                         help='signoff package inn testing')
    sub_approve.add_argument("package", metavar="pkg",
                              nargs="?",
                              default="",
                              help="Package from testing")
    sub_approve.set_defaults(func=approve, format=None)

    # Revoke
    sub_revoke = subparsers.add_parser('revoke',
                                         description=revoke.__doc__,
                                         help='revoke package signoff')
    sub_revoke.add_argument("package", metavar="pkg",
                              nargs="?",
                              default="",
                              help="Package from testing")
    sub_revoke.set_defaults(func=revoke, format=None)

    args = parser.parse_args(sys.argv[1:])
    if len(sys.argv) == 1:
        main(args)
    elif args.format:
        args_func(args)
    else:
        args.func(args)
