# Maintainer: Morten Linderud <morten@linderud.pw>

pkgname=signoff-git
_pkgname=signoff
pkgver=r12.ba5c048
pkgrel=1
pkgdesc="Detects packages installed from testing and reports the ones you haven't signed off"
arch=("any")
url="https://github.com/Foxboron/archweb-signoff-helper"
license=('MIT')
depends=('python-requests' 'python-lxml')
source=("git+https://github.com/Foxboron/archweb-signoff-helper.git")
sha256sums=('SKIP')

pkgver() {
  cd "$_pkgname"
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
  install -Dm755 "$srcdir/$_pkgname/signoff.py" "$pkgdir/usr/bin/signoff"
  install -Dm644 "$srcdir/$_pkgname/archweb.conf" "$pkgdir/usr/share/signoff/archweb.conf"
  install -Dm644 "$srcdir/$_pkgname/LICENSE" "$pkgdir/usr/share/licenses/signoff/LICENSE"
}

