#!/usr/bin/python
import os
import sys
import json
import argparse
import subprocess
import configparser
from http import cookiejar
from itertools import product

import requests
from lxml import etree


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
    print("Missing config file")
    sys.exit()

try:
    USERNAME = os.environ.get("ARCHWEB_USER", CONFIG["User"]["Username"])
except KeyError:
    sys.exit("No username")

try:
    PASSWORD = os.environ.get("ARCHWEB_PASSWORD", CONFIG["User"]["Password"])
except KeyError:
    sys.exit("No password")


def get_xpath_rules():
    xpath = ".//tr[contains(@class, '{}') and contains(@class, '{}')]"
    repos = CONFIG["Repositories"].items()
    archs = CONFIG["Architectures"].items()
    return [xpath.format(r[0], a[0]) for r, a in product(repos, archs)]


def parse_signoff(elm):
    return [i.text for i in elm.xpath(".//li[@class='signed-username']")]


def parse_package(elm):
    tds = elm.xpath(".//td")
    package = {"name": elm.xpath(".//a")[0].text,
               "version": tds[0].xpath("text()")[0].strip(),
               "arch": tds[1].text,
               "repo": tds[2].text,
               "packager": tds[3].text,
               "required_signoffs": tds[4].text,
               "date": tds[5].text,
               "approved": tds[6].text,
               "signoffs": parse_signoff(tds[7]),
               "note": tds[8].text.strip()}
    return package


class Session:
    def __init__(self):
        self.url = "https://www.archlinux.org/login/"
        self.signoff_page = "https://www.archlinux.org/packages/signoffs/"
        self.client = requests.session()
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
            print("Login failed")
            sys.exit()
        self.client.cookies.save()

    def get_signoff_page(self):
        r = self.client.get(self.signoff_page)
        if r.url != self.signoff_page:
            self._login()
            return self.get_signoffs()
        return r.text

    def parse_packages(self):
        body = self.get_signoff_page()
        rules = get_xpath_rules()
        root = etree.HTML(body)

        completed_rules = []
        for i in rules:
            completed_rules.extend(root.xpath(i))

        packages = []
        for i in completed_rules:
            packages.append(parse_package(i))

        with open(CACHE_DIR+"/packages.json", "r+") as f:
                f.seek(0)
                f.write(json.dumps(packages))
                f.truncate()
        return packages

    def get_packages_from_cache(self):
        return json.load(open(CACHE_DIR+"/packages.json"))

    def get_packages(self):
        r = self.client.head(self.signoff_page)
        with open(CACHE_DIR+"/signoff-content-length", "r+") as f:
            length = f.readline()
            if length != str(r.headers['content-length']):
                f.seek(0)
                f.write(r.headers['content-length'])
                f.truncate()
                return self.parse_packages()
        try:
            return self.get_packages_from_cache()
        except json.JSONDecodeError:
            return self.parse_packages()


SESSION = Session()


def approvals(args):
    pkgs = SESSION.get_packages()
    if args.package:
        for pkg in pkgs:
            if pkg["name"] == args.package:
                fmt = "{name} :: {version} -> {approved}"
                return print(fmt.format(**pkg))
        print("Package is not inn testing :)")
    else:
        for pkg in pkgs:
            fmt = "{name} :: {version} -> {approved}"
            print(fmt.format(**pkg))


def signoffs(args):
    pkgs = SESSION.get_packages()
    if args.package:
        for pkg in pkgs:
            if pkg["name"] == args.package:
                fmt = "{name} :: {version} -> {signoffs}"
                pkg["signoffs"] = ",".join(pkg["signoffs"])
                return print(fmt.format(**pkg))
        print("Package is not inn testing :)")
    else:
        for pkg in pkgs:
            fmt = "{name} :: {version} -> {signoffs}"
            pkg["signoffs"] = ", ".join(pkg["signoffs"])
            print(fmt.format(**pkg))


def note(args):
    pkgs = SESSION.get_packages()
    if args.package:
        for pkg in pkgs:
            if pkg["name"] == args.package:
                fmt = "{name} -> {note}"
                return print(fmt.format(**pkg))
        print("Package is not inn testing :)")
    else:
        for pkg in pkgs:
            fmt = "{name} -> {note}"
            print(fmt.format(**pkg))


def approve(args):
    pass


def revoke():
    pass


def main(args):
    packages = SESSION.get_packages()

    cmd = """pacman -Sl testing |
             awk '/\[installed\]$/ { print $2 }' |
             xargs expac '%e %n' |
             awk '{b=( ($1=="(null)") ? $2 : $1); print b}' |
             uniq"""
    installed_packages = [i for i in subprocess.getoutput(cmd).split("\n")]
    for pkg in packages:
        if pkg["name"] not in installed_packages:
            continue
        if USERNAME in pkg["signoffs"]:
            continue
        fmt = "{name} :: {version} :: {date} :: {note}"
        print(fmt.format(**pkg))


if __name__ == "__main__":

    desc = 'signoff - Archweb signoff helper'
    parser = argparse.ArgumentParser(description=desc)
    parser.set_defaults(func=main)
    subparsers = parser.add_subparsers(title="subcommands",
                                       metavar='<command>')

    sub_note = subparsers.add_parser('note',
                                     description=note.__doc__,
                                     help='list package notes')
    sub_note.add_argument("package", metavar="pkg",
                          nargs="?",
                          default="",
                          help="Package from testing")
    sub_note.set_defaults(func=note)

    sub_approve = subparsers.add_parser('approvals',
                                        description=approvals.__doc__,
                                        help='list package approvals')
    sub_approve.add_argument("package", metavar="pkg",
                             nargs="?",
                             default="",
                             help="Package from testing")
    sub_approve.set_defaults(func=approvals)

    sub_signoffs = subparsers.add_parser('signoffs',
                                         description=signoffs.__doc__,
                                         help='list package signoffs')
    sub_signoffs.add_argument("package", metavar="pkg",
                              nargs="?",
                              default="",
                              help="Package from testing")
    sub_signoffs.set_defaults(func=signoffs)

    args = parser.parse_args(sys.argv[1:])
    args.func(args)
