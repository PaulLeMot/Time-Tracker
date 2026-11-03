#!/usr/bin/env python3
"""Certbot DNS-01 hook. Fixed zone/name; no zone replacement or secret logging.

Uses only Python stdlib in the pinned Certbot image. Additional SpaceWeb user
must have Domains only (provider cannot restrict it to this single TXT name).
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import sys
import time
import urllib.request

ZONE = 'fandocraft.ru'
DOMAIN = 'operportal.' + ZONE
SUB = '_acme-challenge.operportal'
NAME = SUB + '.' + ZONE
NS = ('ns1.spaceweb.ru', 'ns2.spaceweb.ru', 'ns3.spaceweb.pro', 'ns4.spaceweb.pro')
PRIVATE = Path('/private')
STATE = Path('/dns-state')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('API redirect refused')


class API:
    def __init__(self):
        credential = json.loads((PRIVATE / 'spaceweb.json').read_text())
        self.token = self.call('/notAuthorized/', 'getToken', credential)
        if not isinstance(self.token, str) or not self.token:
            raise RuntimeError('API authentication failed')

    def call(self, path, method, params):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if getattr(self, 'token', None):
            headers['Authorization'] = 'Bearer ' + self.token
        data = json.dumps(dict(jsonrpc='2.0', method=method, params=params, id='operportal-acme')).encode()
        req = urllib.request.Request('https://api.sweb.ru' + path, data=data, headers=headers)
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
        if result.get('error'):
            # Do not include provider message/response: could echo credentials.
            raise RuntimeError('API error code ' + str(result['error'].get('code')))
        return result['result']

    def records(self):
        records = self.call('/domains/dns', 'info', {'domain': ZONE})
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise RuntimeError('Unexpected DNS schema')
        return records

    def edit(self, **params):
        result = self.call('/domains/dns', 'editTxt', {'domain': ZONE, **params})
        if result not in (True, 1):
            raise RuntimeError('DNS operation not acknowledged')


def matches(record, value):
    name = str(record.get('name') or record.get('domain') or '').rstrip('.')
    return record.get('type') == 'TXT' and name in (SUB, NAME) and record.get('value') == value


def canonical(records):
    # Provider may renumber indices after an insertion/deletion.
    return sorted(json.dumps({k: v for k, v in r.items() if k != 'index'}, sort_keys=True) for r in records)


def save(path, value):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def skip_name(data, offset):
    for _ in range(128):
        length = data[offset]
        if length & 0xc0 == 0xc0:
            return offset + 2
        if length & 0xc0:
            raise ValueError('DNS label encoding')
        offset += 1
        if not length:
            return offset
        offset += length
    raise ValueError('DNS name length')


def recv_exact(sock, count):
    result = b''
    while len(result) < count:
        chunk = sock.recv(count - len(result))
        if not chunk:
            raise OSError('DNS TCP EOF')
        result += chunk
    return result


def dns_txt(nameserver):
    ident = secrets.randbelow(65536)
    question = b''.join(bytes([len(label)]) + label.encode('ascii') for label in NAME.split('.')) + b'\0\0\x10\0\x01'
    query = struct.pack('!6H', ident, 0, 1, 0, 0, 0) + question
    address = socket.gethostbyname(nameserver)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.connect((address, 53))
            sock.send(query)
            data = sock.recv(16384)
        if struct.unpack_from('!H', data, 2)[0] & 0x200:
            raise TimeoutError('TCP required')
    except (TimeoutError, OSError):
        with socket.create_connection((address, 53), timeout=5) as sock:
            sock.sendall(struct.pack('!H', len(query)) + query)
            data = recv_exact(sock, struct.unpack('!H', recv_exact(sock, 2))[0])
    rid, flags, qd, an, _, _ = struct.unpack_from('!6H', data)
    if rid != ident or not flags & 0x8000 or not flags & 0x400 or flags & 0xf:
        return []
    offset = 12
    for _ in range(qd):
        offset = skip_name(data, offset) + 4
    values = []
    for _ in range(an):
        offset = skip_name(data, offset)
        kind, cls, _, size = struct.unpack_from('!HHIH', data, offset)
        offset += 10
        end = offset + size
        if kind == 16 and cls == 1:
            chunks = []
            while offset < end:
                length = data[offset]
                offset += 1
                chunks.append(data[offset:offset + length])
                offset += length
            values.append(b''.join(chunks).decode('ascii'))
        offset = end
    return values


def cleanup(api, path):
    journal = json.loads(path.read_text())
    if journal.get('domain') != DOMAIN or journal.get('sub') != SUB:
        raise RuntimeError('Unexpected journal scope')
    value = journal['value']
    records = api.records()
    own = [r for r in records if matches(r, value)]
    if journal['owned']:
        if len(own) > 1:
            raise RuntimeError('Ambiguous TXT ownership')
        if own:
            api.edit(action='del', type='TXT', index=int(own[0]['index']))
            after = api.records()
            if any(matches(r, value) for r in after):
                raise RuntimeError('TXT cleanup not confirmed')
            if canonical(after) != canonical([r for r in records if not matches(r, value)]):
                raise RuntimeError('Concurrent DNS change during cleanup; inspect zone')
    path.unlink()


def main():
    command = sys.argv[1]
    if command == 'recover':
        api = API()
        for path in sorted(STATE.glob('challenge-*.json')):
            cleanup(api, path)
        print('DNS cleanup recovery complete', file=sys.stderr)
        return
    domain, value = os.environ.get('CERTBOT_DOMAIN'), os.environ.get('CERTBOT_VALIDATION', '')
    if domain != DOMAIN or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value):
        raise RuntimeError('Unexpected ACME domain or validation')
    path = STATE / ('challenge-' + hashlib.sha256(value.encode()).hexdigest() + '.json')
    api = API()
    if command == 'cleanup':
        if path.exists():
            cleanup(api, path)
        print('Owned TXT cleanup complete', file=sys.stderr)
        return
    if command != 'auth':
        raise RuntimeError('Unexpected command')
    before = api.records()
    existed = any(matches(r, value) for r in before)
    if not path.exists():
        # Persist intent before writing DNS; recover even if killed after add.
        save(path, {'domain': domain, 'sub': SUB, 'value': value, 'owned': not existed, 'created': time.time()})
    if not existed:
        api.edit(action='add', index=0, subDomain=SUB, value=value)
    after = api.records()
    if not any(matches(r, value) for r in after):
        raise RuntimeError('TXT creation not confirmed')
    if canonical([r for r in before if not matches(r, value)]) != canonical([r for r in after if not matches(r, value)]):
        raise RuntimeError('Concurrent DNS change during authorization; inspect zone')
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        ready = 0
        for ns in NS:
            try:
                ready += value in dns_txt(ns)
            except (OSError, ValueError, IndexError, struct.error):
                pass
        if ready == len(NS):
            print('TXT confirmed on all four authoritative servers', file=sys.stderr)
            time.sleep(15)
            return
        time.sleep(15)
    raise RuntimeError('DNS propagation timed out; owned TXT retained for cleanup/recovery')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('SpaceWeb DNS hook failed: ' + type(error).__name__ + ' ' + str(error) if isinstance(error, RuntimeError) else 'SpaceWeb DNS hook failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
