#!/usr/bin/python
import sys
import os
import http
import subprocess
import configparser
from subprocess import call

from http import cookiejar

from itertools import product

import requests
from lxml import etree


HOME = os.path.expanduser("~")
CACHE=HOME+"/.cache/archweb"

USERNAME = None
PASSWORD = None
CONFIG = configparser.ConfigParser()

if not os.path.isdir(CACHE):
    os.mkdir(CACHE)
if not os.path.isdir(CACHE+"/cookies"):
    open(CACHE+"/cookies","a")
    
if os.path.isfile(HOME+"/.config/archweb/archweb.conf"):
    CONFIG.read(HOME+"/.config/archweb/archweb.conf")
    if CONFIG.has_section("User"):
        USERNAME = CONFIG["User"]["Username"] if CONFIG.has_option("User", "Username") else ""
        PASSWORD = CONFIG["User"]["Password"] if CONFIG.has_option("User", "Password") else ""
if not USERNAME and not os.environ.get("ARCHWEB_USER", False):
    print("Missing username")
    sys.exit()
elif os.environ.get("ARCHWEB_USER", False):
    USERNAME = os.environ["ARCHWEB_USER"]
if not PASSWORD and not os.environ.get("ARCHWEB_PASSWORD", False):
    print("Missing password")
    sys.exit()
elif os.environ.get("ARCHWEB_PASSWORD", False):
    PASSWORD = os.environ["ARCHWEB_PASSWORD"]


class Session:
    def __init__(self):
        self.url = "https://www.archlinux.org/login/"
        self.client = requests.session()
        cj = http.cookiejar.LWPCookieJar(CACHE+"/cookies")
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
                      "csrfmiddlewaretoken": csrftoken
                    }

        r = self.client.post(self.url, data=login_data, headers={"referer": "https://www.archlinux.org/login","origin": "https://www.archlinux.org"})
        if r.status_code != 200:
            print("Login failed")
            sys.exit()
        self.client.cookies.save()

    def get_signoffs(self):
        signoff_page = "https://www.archlinux.org/packages/signoffs/"
        r = self.client.get(signoff_page)
        if r.url != signoff_page:
            self._login()
            self.get_signoffs()
            return
        return r.text


def get_xpath_rules():
    ret = []
    xpath = ".//tr[contains(@class, '{}') and contains(@class, '{}')]"
    repos = CONFIG["Repositories"].items()
    archs = CONFIG["Architectures"].items()
    for r,a in product(repos, archs):
        ret.append(xpath.format(r[0],a[0]))
    return ret

def parse_signoff(elm):
    r = elm.xpath(".//li[@class='signed-username']")
    return [i.text for i in r]

def parse_package(elm):
    r = elm.xpath(".//a")[0]
    return r.text


s = Session()
body = s.get_signoffs()
rules = get_xpath_rules()
root = etree.HTML(body)

res = []
for i in rules:
    res.extend(root.xpath(i))

cmd = "pacman -Sl testing | awk '/\[installed\]$/ { print $2 }' | xargs expac '%e %n' | awk '{ b=( ($1==\"(null)\") ? $2 : $1); printf \"%-20s %s %s\\n\",b,$2,$3 }' | sort | awk '{ print $1 }' | uniq"
packages = [i for i in subprocess.getoutput(cmd).split("\n")]
for i in res:
    pkg = parse_package(i)
    if pkg not in packages:
        continue
    if USERNAME in parse_signoff(i):
        continue
    print(pkg)
