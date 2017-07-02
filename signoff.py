#!/usr/bin/python
import os
import sys
import subprocess
import configparser
from http import cookiejar
from itertools import product

import requests
from lxml import etree


HOME = os.path.expanduser("~")
CONFIG_DIR = os.environ.get('XDG_CONFIG_DIR', HOME+'/.config')
CACHE_DIR = os.environ.get('XDG_CACHE_DIR', HOME+"/.cache")

USERNAME = None
PASSWORD = None
CONFIG = configparser.ConfigParser()

if not os.path.isdir(CACHE_DIR+"/archweb"):
    os.mkdir(CACHE_DIR+"/archweb")
if not os.path.isfile(CACHE_DIR+"/archweb/cookies"):
    open(CACHE_DIR+"/archweb/cookies", "a")

if os.path.isfile(CONFIG_DIR+"/archweb/archweb.conf"):
    CONFIG.read(CONFIG_DIR+"/archweb/archweb.conf")
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


class Session:
    def __init__(self):
        self.url = "https://www.archlinux.org/login/"
        self.client = requests.session()
        cj = cookiejar.LWPCookieJar(CACHE_DIR+"/archweb/cookies")
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

        r = self.client.post(self.url, data=login_data,
                             headers={"referer": "https://www.archlinux.org/login",
                                      "origin": "https://www.archlinux.org"})
        if r.status_code != 200:
            print("Login failed")
            sys.exit()
        self.client.cookies.save()

    def get_signoffs(self):
        signoff_page = "https://www.archlinux.org/packages/signoffs/"
        r = self.client.get(signoff_page)
        if r.url != signoff_page:
            self._login()
            return self.get_signoffs()
        return r.text


def get_xpath_rules():
    xpath = ".//tr[contains(@class, '{}') and contains(@class, '{}')]"
    repos = CONFIG["Repositories"].items()
    archs = CONFIG["Architectures"].items()
    return [xpath.format(r[0], a[0]) for r, a in product(repos, archs)]


def parse_signoff(elm):
    return [i.text for i in elm.xpath(".//li[@class='signed-username']")]


def parse_package(elm):
    return elm.xpath(".//a")[0].text


s = Session()
body = s.get_signoffs()
rules = get_xpath_rules()
root = etree.HTML(body)

res = []
for i in rules:
    res.extend(root.xpath(i))

cmd = """pacman -Sl testing | awk '/\[installed\]$/ { print $2 }' |
         xargs expac '%e %n' | awk '{b=( ($1=="(null)") ? $2 : $1); print b}' |
         uniq"""
packages = [i for i in subprocess.getoutput(cmd).split("\n")]
for i in res:
    pkg = parse_package(i)
    if pkg not in packages:
        continue
    if USERNAME in parse_signoff(i):
        continue
    print(pkg)
