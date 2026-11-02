"""Bounded raw-image protocol: no multipart spool, URL fetch, paths or query logging."""
import asyncio
import hashlib
import hmac
import re
import secrets
import time
from fastapi import HTTPException

MAX_BODY = 2 * 1024 * 1024


async def read_body(request):
    size = request.headers.get('content-length')
    if size and (not size.isdigit() or int(size) > MAX_BODY):
        raise HTTPException(413, 'image_size')
    data = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_BODY:
                    raise HTTPException(413, 'image_size')
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, 'upload_timeout') from None
    return bytes(data)


def proof(secret, method, path, stamp, nonce, subject, body):
    prefix = f'VS1\n{method}\n{path}\n{stamp}\n{nonce}\n{subject}\n'.encode()
    return hmac.new(secret, prefix + hashlib.sha256(body).digest(), hashlib.sha256).hexdigest()


def signed(secret, method, path, subject, body=b''):
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    return {'X-VS-Time': stamp, 'X-VS-Nonce': nonce, 'X-VS-Subject': subject,
            'X-VS-Proof': proof(secret, method, path, stamp, nonce, subject, body)}


class Authentication:
    def __init__(self, secret, *, allow_uuid=False):
        if len(secret) < 32:
            raise ValueError('secret_too_short')
        self.secret, self.used = secret, {}
        self.allow_uuid = allow_uuid

    def check(self, request, body):
        headers = request.headers
        stamp, nonce, subject, signature = [headers.get(n, '') for n in ('x-vs-time', 'x-vs-nonce', 'x-vs-subject', 'x-vs-proof')]
        valid_subject=re.fullmatch('[0-9]{1,12}',subject) or self.allow_uuid and re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',subject)
        if not re.fullmatch('[0-9]{10}', stamp) or abs(time.time() - int(stamp)) > 30 or not re.fullmatch('[a-f0-9]{32}', nonce) or not valid_subject:
            raise HTTPException(401, 'service_auth')
        path = request.url.path + ('?' + request.url.query if request.url.query else '')
        expected = proof(self.secret, request.method, path, stamp, nonce, subject, body)
        if not hmac.compare_digest(signature, expected) or nonce in self.used:
            raise HTTPException(401, 'service_auth')
        now = time.time()
        self.used = {k: v for k, v in self.used.items() if now - v < 65}
        if len(self.used) >= 2048:
            raise HTTPException(429, 'service_rate_limit')
        self.used[nonce] = now
        return subject


class Capacity:
    def __init__(self, maximum=3):
        self.maximum, self.active = maximum, 0

    def enter(self):
        if self.active >= self.maximum:
            raise HTTPException(429, 'busy_retry')
        self.active += 1

    def leave(self):
        self.active -= 1
