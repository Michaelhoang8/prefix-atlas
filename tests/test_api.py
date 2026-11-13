import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from run import Handler


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, data=None, headers=None, raw=None, method=None):
        conn = HTTPConnection(*self.server.server_address, timeout=3)
        conn.request(method or ('POST' if data is not None or raw is not None else 'GET'), path,
                     body=raw if raw is not None else json.dumps(data) if data is not None else None,
                     headers={'Content-Type': 'application/json', **(headers or {})})
        response = conn.getresponse()
        body = response.read()
        result = response.status, json.loads(body) if body else None, response.headers
        conn.close()
        return result

    def test_lookup_and_large_integer_subnet_contracts(self):
        status, result, _ = self.request('/api/lookup', {'routes': '0.0.0.0/0 default 1', 'destination': '192.0.2.1'})
        self.assertEqual(status, 200)
        self.assertEqual(result['winner']['hop'], 'default')
        status, result, _ = self.request('/api/subnets', {'cidr': '::/0', 'new_prefix': 128})
        self.assertEqual(status, 200)
        self.assertEqual(result['subnet_count'], str(2**128))
        self.assertEqual(len(result['subnets']), 64)

    def test_rejects_unknown_fields_invalid_types_and_malformed_json(self):
        for payload in [{'routes': [], 'destination': '1.2.3.4'}, {'routes': '', 'destination': True}, {'routes': '', 'destination': '1.2.3.4', 'extra': 1}]:
            self.assertEqual(self.request('/api/lookup', payload)[0], 400)
        self.assertEqual(self.request('/api/subnets', {'cidr': '::/0', 'new_prefix': True})[0], 400)
        for raw in ['[]', '{"x":1,"x":2}', '{"x":NaN}', '['*1500, '{']:
            self.assertEqual(self.request('/api/lookup', raw=raw)[0], 400)

    def test_browser_boundaries_and_no_filesystem_routes(self):
        self.assertEqual(self.request('/api/examples', headers={'Host': 'evil.invalid'})[0], 400)
        self.assertEqual(self.request('/api/examples', headers={'Origin': 'https://evil.invalid'})[0], 403)
        self.assertEqual(self.request('/api/examples', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        for path in ['/.git/config', '/routing.py', '/../run.py']:
            self.assertEqual(self.request(path)[0], 404)
        status, body, headers = self.request('/api/examples', method='HEAD')
        self.assertEqual(status, 200)
        self.assertIsNone(body)
        self.assertIn("object-src 'none'", headers['Content-Security-Policy'])


if __name__ == '__main__':
    unittest.main()
