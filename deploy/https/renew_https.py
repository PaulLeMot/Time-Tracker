#!/usr/bin/env python3
"""Locked unattended DNS-01 renewal and checked nginx certificate deployment.

Run as the existing mint Docker owner. No app/database/container restart.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

ROOT = Path('/home/mint/.local/share/operportal-https')
DOMAIN = 'operportal.fandocraft.ru'
IMAGE = 'certbot/certbot@sha256:91808b1b417f72daa57763337e6080c6b90c49b409d06778924f9a9d4affde02'
STATE = ROOT / 'renewal-state'


def command(args, **kwargs):
    return subprocess.run(args, check=True, timeout=1800, **kwargs)


def docker(args, *, entrypoint=None):
    cmd = ['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges']
    for host, target, readonly in [('certs', '/etc/letsencrypt', False), ('certbot-work', '/var/lib/letsencrypt', False), ('certbot-logs', '/var/log/letsencrypt', False), (str(Path(__file__).resolve().parent), '/hooks', True), ('private', '/private', True), ('renewal-state', '/dns-state', False)]:
        cmd += ['-v', f'{ROOT / host}:{target}' + (':ro' if readonly else '')]
    if entrypoint:
        cmd += ['--entrypoint', entrypoint]
    return command(cmd + [IMAGE] + args)


def atomic(path, data, permissions=0o600):
    tmp = path.with_name(path.name + '.new')
    with tmp.open('wb') as stream:
        os.fchmod(stream.fileno(), permissions)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def served_fingerprint():
    context = ssl.create_default_context()
    with socket.create_connection(('127.0.0.1', 8443), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=DOMAIN) as connection:
            return hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest()


def deploy(force=False):
    lineage = ROOT / 'certs/live' / DOMAIN
    # A staging certificate must never reach nginx. Verify production trust,
    # SAN, expiration, and public/private key match before touching active TLS.
    command(['openssl', 'verify', '-purpose', 'sslserver', '-verify_hostname', DOMAIN, '-untrusted', str(lineage / 'chain.pem'), str(lineage / 'cert.pem')])
    command(['openssl', 'x509', '-in', str(lineage / 'cert.pem'), '-noout', '-checkend', str(30 * 86400)])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(lineage / 'fullchain.pem', lineage / 'privkey.pem')
    expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert((lineage / 'cert.pem').read_text())).hexdigest()
    if not force and served_fingerprint() == expected:
        return {'changed': False, 'fingerprint': expected}
    target = ROOT / 'tls'
    backups = {name: (target / name).read_bytes() for name in ('fullchain.pem', 'privkey.pem')}
    backup = STATE / ('tls-before-' + str(time.time_ns()))
    backup.mkdir(mode=0o700)
    for name, value in backups.items():
        atomic(backup / name, value)
    try:
        for name in backups:
            atomic(target / name, (lineage / name).read_bytes(), 0o644 if name == 'fullchain.pem' else 0o600)
        command(['docker', 'exec', 'operportal-https', 'nginx', '-t', '-c', '/config/nginx.conf'])
        command(['docker', 'exec', 'operportal-https', 'nginx', '-s', 'reload', '-c', '/config/nginx.conf'])
        for _ in range(20):
            if served_fingerprint() == expected:
                return {'changed': True, 'fingerprint': expected, 'rollback_copy': backup.name}
            time.sleep(1)
        raise RuntimeError('Served certificate did not converge')
    except Exception:
        for name, value in backups.items():
            atomic(target / name, value, 0o644 if name == 'fullchain.pem' else 0o600)
        command(['docker', 'exec', 'operportal-https', 'nginx', '-t', '-c', '/config/nginx.conf'])
        command(['docker', 'exec', 'operportal-https', 'nginx', '-s', 'reload', '-c', '/config/nginx.conf'])
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reconfigure', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--deploy-check', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / 'renew.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another renewal is active; skipped')
            return
        receipt = {'started': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': vars(args), 'pass': False}
        try:
            if not args.deploy_check:
                docker(['/hooks/spaceweb_dns_hook.py', 'recover'], entrypoint='python')
                if args.reconfigure:
                    docker(['reconfigure', '--non-interactive', '--cert-name', DOMAIN, '--manual-auth-hook', 'python /hooks/spaceweb_dns_hook.py auth', '--manual-cleanup-hook', 'python /hooks/spaceweb_dns_hook.py cleanup'])
                else:
                    extra = ['--dry-run'] if args.dry_run else []
                    docker(['renew', '--non-interactive', '--cert-name', DOMAIN] + extra)
            receipt['deployment'] = deploy(force=args.deploy_check)
            receipt['pass'] = True
        finally:
            receipt['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            data = json.dumps(receipt, indent=2).encode()
            atomic(STATE / 'last-attempt.json', data)
            if receipt['pass']:
                atomic(STATE / 'last-success.json', data)
            print(json.dumps(receipt))


if __name__ == '__main__':
    main()
