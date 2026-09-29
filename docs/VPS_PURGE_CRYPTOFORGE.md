# VPS CryptoForge Purge

This is the destructive cleanup path for removing CryptoForge from the
VPS after moving runtime to the local Docker host.

Run as root on the VPS:

```bash
cd /opt/cryptoforge/app/cryptoforge_repo
bash deploy/purge_vps_cryptoforge.sh --apply
```

The script stops, disables and masks all `cryptoforge*` systemd units,
removes installed unit files, removes `/etc/logrotate.d/cryptoforge`,
deletes `/opt/cryptoforge`, and removes the `cryptoforge` system user
when possible.

It does not touch Docker, Postgres, Guacamole, VPN, x-ui, xray, firewall
or non-CryptoForge files.

If the repository directory is already unavailable, copy the script body
from `deploy/purge_vps_cryptoforge.sh` to `/root/purge_vps_cryptoforge.sh`
and run:

```bash
bash /root/purge_vps_cryptoforge.sh --apply
```

Verify:

```bash
systemctl list-units 'cryptoforge*' --all --no-pager
systemctl list-unit-files 'cryptoforge*' --no-pager
test ! -e /opt/cryptoforge && echo cryptoforge_dir_removed
id cryptoforge || true
```
