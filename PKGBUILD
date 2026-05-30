# Maintainer: hexman1999@github
pkgname=bootanimation-previewer
pkgver=1.0.0
pkgrel=1
pkgdesc="Preview and export Android bootanimation.zip files"
arch=('any')
url="https://github.com/hexman1999/bootanimation-previewer-gtk4"
license=('GPL3')
depends=(
    'python'
    'python-gobject'
    'python-cairo'
    'opencv'
    'python-numpy'
    'gtk4'
    'libadwaita'
)
optdepends=(
    'ffmpeg: GIF export support'
)
makedepends=('git')
source=("$pkgname::git+$url.git")
sha256sums=('SKIP')

prepare() {
    cd "$srcdir/$pkgname"
    rm -rf .git .gitignore __pycache__ *.zip *.gif install.sh
}

package() {
    cd "$srcdir/$pkgname"

    install -Dm755 previewer.py "$pkgdir/usr/bin/bootanimation-previewer"

    install -Dm644 Resources/bootanimation-previewer.svg \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/bootanimation-previewer.svg"

    install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/org.antigravity.bootanimation_previewer.desktop" << EOF
[Desktop Entry]
Name=Boot Animation Previewer
Comment=Preview and export Android bootanimation.zip files
Exec=bootanimation-previewer
Icon=bootanimation-previewer
Terminal=false
Type=Application
Categories=Graphics;Utility;
StartupWMClass=org.antigravity.bootanimation_previewer
EOF

    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
