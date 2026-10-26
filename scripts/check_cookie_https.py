"""Verify browser cookie contracts over real, certificate-validated TLS in a disposable stack."""

import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = 'cookie-https-' + secrets.token_hex(5)
    env = dict(os.environ)
    for key in ('DB_PASSWORD', 'APP_PASSWORD', 'MIGRATOR_PASSWORD', 'DEMO_PASSWORD'):
        env['SESSION_TEST_' + key] = secrets.token_hex(24)
    output = ROOT / 'work' / 'cookie-https'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tls-', dir=output) as directory:
        tls = Path(directory)
        tls.chmod(0o755)
        env['SESSION_TEST_TLS_DIR'] = str(tls)
        def openssl(*args):
            subprocess.run(['openssl', *args], cwd=tls, check=True, capture_output=True)
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=Disposable Cookie Test CA', '-keyout', 'ca.key', '-out', 'ca.crt',
                '-addext', 'basicConstraints=critical,CA:TRUE',
                '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        openssl('req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
                '-keyout', 'server.key', '-out', 'server.csr')
        (tls / 'server.ext').write_text('subjectAltName=DNS:localhost,IP:127.0.0.1\n'
                                      'extendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\n'
                                      'keyUsage=critical,digitalSignature,keyEncipherment\n'
                                      'subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        openssl('x509', '-req', '-in', 'server.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key',
                '-CAcreateserial', '-days', '1', '-extfile', 'server.ext', '-out', 'server.crt')
        # This key authenticates only the disposable loopback test server and is removed at exit.
        for name in ('server.key', 'server.crt', 'ca.crt'):
            (tls / name).chmod(0o644)
        base = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'compose.session-test.yaml')]
        def compose(*args, check=True):
            result = subprocess.run([*base, *args], cwd=ROOT, env=env, capture_output=True, text=True)
            if check and result.returncode:
                raise RuntimeError('Compose ' + args[0] + ' failed: ' + result.stderr[-2000:])
            return result
        try:
            compose('up', '-d', '--no-build')
            def address(port, scheme):
                container = compose('ps', '-q', '--all', 'frontend').stdout.strip()
                details = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
                bindings = details['NetworkSettings']['Ports'].get(str(port) + '/tcp')
                if not bindings:
                    logs = compose('logs', '--tail', '20', 'frontend', check=False).stdout
                    raise RuntimeError('Frontend did not publish its test port: ' + logs[-2500:])
                binding = bindings[0]
                assert binding['HostIp'] == '127.0.0.1' and binding['HostPort'].isdigit()
                return scheme + '://127.0.0.1:' + binding['HostPort']
            https = address(8443, 'https')
            plain = address(8080, 'http')
            context = ssl.create_default_context(cafile=str(tls / 'ca.crt'))
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            jar = http.cookiejar.CookieJar()
            client = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(jar))
            def call(path, body=None, csrf=None, origin=https, method=None):
                headers = {'Content-Type': 'application/json'}
                if csrf:
                    headers['X-XSRF-TOKEN'] = csrf
                request = Request(origin + '/api' + path, headers=headers, method=method,
                                  data=None if body is None else json.dumps(body).encode())
                try:
                    response = client.open(request, timeout=2)
                except HTTPError as error:
                    response = error
                with response:
                    data = response.read()
                    try:
                        result = json.loads(data)
                    except json.JSONDecodeError:
                        result = {}
                    return response.status, result, response.headers
            last_health = None
            for _ in range(30):
                try:
                    health_status = call('/health')[0]
                    last_health = health_status
                    if health_status == 200:
                        break
                except (URLError, TimeoutError) as error:
                    if isinstance(error, URLError) and isinstance(error.reason, ssl.SSLCertVerificationError):
                        raise
                    last_health = type(error).__name__ + ': ' + str(error.reason if isinstance(error, URLError) else error)
                time.sleep(1)
            else:
                logs = compose('logs', '--tail', '35', 'frontend', 'backend', check=False).stdout
                raise RuntimeError('HTTPS backend health did not become ready: ' + str(last_health) + '\n' + logs[-7000:])
            result = {'tls_certificate_validated': True}
            try:
                build_opener(HTTPSHandler(context=ssl.create_default_context())).open(https, timeout=10)
                raise AssertionError('Untrusted test CA unexpectedly accepted')
            except URLError as error:
                assert isinstance(error.reason, ssl.SSLCertVerificationError)
            result['untrusted_certificate_rejected'] = True
            assert call('/me')[0] == 401
            status, csrf, _ = call('/auth/csrf')
            assert status == 200
            credentials = {'login': 'demo-owner', 'password': env['SESSION_TEST_DEMO_PASSWORD']}
            assert call('/auth/session', credentials)[0] == 403
            status, login, headers = call('/auth/session', credentials, csrf['token'])
            assert status == 200 and 'accessToken' not in login
            session = next(c for c in headers.get_all('Set-Cookie') if c.startswith('__Host-ALPHA_SESSION='))
            assert all(flag in session for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/', 'Max-Age=43200'))
            assert 'Domain=' not in session
            result['secure_host_cookie_policy'] = True
            status, me, _ = call('/me')
            assert status == 200 and call('/me')[0] == 200
            assert call('/me', origin=plain)[0] == 401
            result['secure_cookie_not_sent_over_http'] = True
            status, csrf, headers = call('/auth/csrf')
            assert status == 200
            csrf_cookie = next(c for c in headers.get_all('Set-Cookie') if c.startswith('__Host-ALPHA_CSRF='))
            assert all(flag in csrf_cookie for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'))
            company = next(p for p in me['parties'] if p['access_role'] == 'OWNER')
            create = {'partyId': company['id'], 'answers': {}}
            assert call('/selection-profiles', create)[0] == 403
            status, profile, _ = call('/selection-profiles', create, csrf['token'])
            assert status == 200
            assert call('/selection-profiles/' + profile['id'],
                        {'expectedVersion': profile['rowVersion'], 'answers': {}},
                        csrf['token'], method='PATCH')[0] == 200
            result['csrf_and_consecutive_cookie_writes'] = True
            status, _, headers = call('/auth/logout', {}, csrf['token'])
            assert status == 200
            deletion = next(c for c in headers.get_all('Set-Cookie') if c.startswith('__Host-ALPHA_SESSION='))
            assert 'Secure' in deletion and 'Max-Age=0' in deletion
            assert call('/me')[0] == 401
            result['logout_deletes_secure_cookie'] = True
            (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result, indent=2))
        finally:
            cleanup = compose('down', '-v', '--remove-orphans', check=False)
            if cleanup.returncode:
                raise RuntimeError('Could not remove disposable test stack ' + project)


if __name__ == '__main__':
    main()
