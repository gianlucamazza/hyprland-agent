# AUR packaging

## Files

- `PKGBUILD` — stable release, source from GitHub tarball.
- `.SRCINFO` — generated with `makepkg --printsrcinfo > .SRCINFO`.

## Publishing to AUR

1. Create AUR account and add your SSH key at https://aur.archlinux.org/account
2. Clone the AUR package repo (first time, after the package is created via the web UI):
   ```bash
   git clone ssh://aur@aur.archlinux.org/hyprland-agent.git aur-hyprland-agent
   ```
3. Copy PKGBUILD and generate .SRCINFO:
   ```bash
   cp packaging/aur/PKGBUILD aur-hyprland-agent/
   cd aur-hyprland-agent
   makepkg --printsrcinfo > .SRCINFO
   ```
4. Update `sha256sums` in PKGBUILD with the real hash of the release tarball:
   ```bash
   curl -sL https://github.com/gianlucamazza/hyprland-agent/archive/refs/tags/v1.0.0.tar.gz | sha256sum
   ```
   Replace `SKIP` in PKGBUILD with the hash, regenerate `.SRCINFO`.
5. Commit and push:
   ```bash
   git add PKGBUILD .SRCINFO
   git commit -m "Update to v1.0.0"
   git push
   ```

## Testing locally

```bash
cd packaging/aur
makepkg -si --cleanbuild
```

Requires `base-devel` and all `makedepends` installed.
