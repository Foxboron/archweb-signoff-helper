archweb-signoff-helper
======================

This script lists packages installed from `[testing]` that you havent signed off inn the interface. It handles login
details either from the config file, or from the env variables `ARCHWEB_USER` or `ARCHWEB_PASSWORD`


Usage:
```
usage: signoff [-h] <command> ...

signoff - Archweb signoff helper

optional arguments:
  -h, --help  show this help message and exit

subcommands:
  <command>
    note      list package notes
    approvals
              list package approvals
    signoffs  list package signoffs
```


`~/.config/archweb/archweb.conf`
```
[User]
Username=
Password=

[Repositories]
core=yes
extra=yes
;community=yes
;multilib=yes

[Architectures]
any=yes
x86_64=yes
;i686=yes
```
