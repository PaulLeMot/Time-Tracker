"""Safety regressions for DNS cleanup and TLS deployment (no live credentials)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'deploy/https' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dns = load('spaceweb_dns_hook')


class CleanupTests(unittest.TestCase):
    def test_cleanup_preserves_foreign_txt_and_uses_current_index(self):
        foreign = {'type': 'TXT', 'name': dns.SUB, 'value': 'other-renewal', 'index': 3}
        own = {'type': 'TXT', 'name': dns.SUB, 'value': 'our-validation', 'index': 7}
        class API:
            def __init__(self): self.rows = [foreign, own]; self.calls = []
            def records(self): return self.rows.copy()
            def edit(self, **params):
                self.calls.append(params)
                self.rows = [foreign]
        api = API()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.json'
            path.write_text(json.dumps(dict(domain=dns.DOMAIN, sub=dns.SUB, value='our-validation', owned=True, index=1)))
            dns.cleanup(api, path)
            self.assertFalse(path.exists())
        self.assertEqual(api.calls, [dict(action='del', type='TXT', index=7)])
        self.assertEqual(api.rows, [foreign])

    def test_preexisting_same_value_is_not_owned(self):
        class API:
            def records(self): return [{'type': 'TXT', 'name': dns.SUB, 'value': 'already-present', 'index': 0}]
            def edit(self, **params): raise AssertionError('Must not delete preexisting value')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.json'
            path.write_text(json.dumps(dict(domain=dns.DOMAIN, sub=dns.SUB, value='already-present', owned=False)))
            dns.cleanup(API(), path)

    def test_ambiguous_duplicate_retains_journal_and_does_not_delete(self):
        class API:
            def records(self): return [{'type': 'TXT', 'name': dns.SUB, 'value': 'duplicate', 'index': i} for i in [0, 1]]
            def edit(self, **params): raise AssertionError('Ambiguous ownership')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'journal.json'
            path.write_text(json.dumps(dict(domain=dns.DOMAIN, sub=dns.SUB, value='duplicate', owned=True)))
            with self.assertRaises(RuntimeError): dns.cleanup(API(), path)
            self.assertTrue(path.exists())

    def test_other_domain_rejected_before_authentication(self):
        with patch.object(dns.sys, 'argv', ['hook', 'auth']), patch.dict(dns.os.environ, {'CERTBOT_DOMAIN': 'fandomir.ru', 'CERTBOT_VALIDATION': 'x'*43}), patch.object(dns, 'API') as api:
            with self.assertRaises(RuntimeError): dns.main()
            api.assert_not_called()


@unittest.skipIf(__import__('os').name == 'nt', 'Linux fcntl deployment module')
class DeployTests(unittest.TestCase):
    def test_nginx_failure_restores_both_files(self):
        renew = load('renew_https')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = root / 'renewal-state'; state.mkdir()
            lineage = root / 'certs/live' / renew.DOMAIN; lineage.mkdir(parents=True)
            tls = root / 'tls'; tls.mkdir()
            for name in ['fullchain.pem', 'privkey.pem']:
                (lineage / name).write_bytes(b'new-' + name.encode()); (tls / name).write_bytes(b'old-' + name.encode())
            (lineage / 'cert.pem').write_text('fake cert; conversion mocked')
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[:4] == ['docker', 'exec', 'operportal-https', 'nginx'] and args[4] == '-t' and sum(c[0] == 'docker' for c in calls) == 1:
                    raise subprocess.CalledProcessError(1, args)
            with patch.object(renew, 'ROOT', root), patch.object(renew, 'STATE', state), patch.object(renew, 'command', command), patch.object(renew.ssl, 'SSLContext'), patch.object(renew.ssl, 'PEM_cert_to_DER_cert', return_value=b'new'), patch.object(renew, 'served_fingerprint', return_value='old'):
                with self.assertRaises(subprocess.CalledProcessError): renew.deploy(force=True)
            for name in ['fullchain.pem', 'privkey.pem']:
                self.assertEqual((tls / name).read_bytes(), b'old-' + name.encode())
            self.assertTrue(any('-s' in c and 'reload' in c for c in calls))

    def test_untrusted_certificate_rejected_before_live_files(self):
        renew = load('renew_https')
        with patch.object(renew, 'command', side_effect=subprocess.CalledProcessError(1, ['openssl', 'verify'])), patch.object(renew, 'atomic') as atomic:
            with self.assertRaises(subprocess.CalledProcessError): renew.deploy(force=True)
            atomic.assert_not_called()


if __name__ == '__main__': unittest.main()
