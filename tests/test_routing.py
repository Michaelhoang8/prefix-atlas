import ipaddress
import random
import unittest
from routing import network, address, parse_routes, PrefixTrie, lookup, subnet_plan, EXAMPLES


class RoutingTests(unittest.TestCase):
    def test_longest_prefix_beats_metric_and_metrics_break_only_equal_prefixes(self):
        result = lookup(EXAMPLES['office']['routes'], '10.20.30.42')
        self.assertEqual(result['winner']['hop'], 'service-host')
        self.assertEqual(result['winner']['metric'], 900)
        self.assertEqual([r['prefix'] for r in result['matches']], [32, 24, 24, 16, 8, 0])
        self.assertEqual(lookup(EXAMPLES['office']['routes'], '10.20.30.43')['winner']['hop'], 'office-b')

    def test_exact_ties_are_stable_and_default_routes_work(self):
        table = '0.0.0.0/0 first 10\n0.0.0.0/0 second 10'
        self.assertEqual(lookup(table, '255.255.255.255')['winner']['hop'], 'first')
        self.assertEqual(lookup(table, '0.0.0.0')['winner']['prefix'], 0)

    def test_ipv6_uses_all_128_bits_and_never_matches_ipv4(self):
        result = lookup(EXAMPLES['ipv6']['routes'], EXAMPLES['ipv6']['destination'])
        self.assertEqual(result['winner']['prefix'], 64)
        self.assertEqual(len(result['bits']), 128)
        table = '::/0 v6 0\n2001:db8::1/128 host 99\n0.0.0.0/0 v4 0'
        self.assertEqual(lookup(table, '2001:db8::1')['winner']['prefix'], 128)
        self.assertEqual(lookup('::/0 v6 0', '192.0.2.1')['winner'], None)

    def test_no_route_and_empty_tables_return_explicit_no_match(self):
        self.assertIsNone(lookup(EXAMPLES['gap']['routes'], EXAMPLES['gap']['destination'])['winner'])
        self.assertEqual(lookup('# empty', '127.0.0.1')['matches'], [])

    def test_validation_rejects_host_bits_scopes_and_ambiguous_formats(self):
        with self.assertRaisesRegex(ValueError, '192.0.2.0/24'):
            network('192.0.2.8/24')
        for cidr in ['192.0.2.0/255.255.255.0', '192.0.2.0/024', '2001:db8::1/64', '::%eth0/0', '10.0.0.1']:
            with self.assertRaises(ValueError):
                network(cidr)
        for ip in ['1.2.3', '01.2.3.4', 'fe80::1%eth0', '256.1.1.1']:
            with self.assertRaises(ValueError):
                address(ip)
        for text in ['0.0.0.0/0 hop -1', '0.0.0.0/0 hop 65536', '0.0.0.0/0 <script> 1', '0.0.0.0/0 hop 01', '0.0.0.0/0 hop', '0.0.0.0/0 hop 1\n' * 129]:
            with self.assertRaises(ValueError):
                parse_routes(text)

    def test_subnet_preview_is_bounded_even_for_the_entire_ipv6_space(self):
        plan = subnet_plan('::/0', 128)
        self.assertEqual(plan['subnet_count'], str(2**128))
        self.assertEqual(plan['address_count'], str(2**128))
        self.assertEqual(len(plan['subnets']), 64)
        self.assertTrue(plan['truncated'])
        self.assertEqual(plan['subnets'][-1], '::3f/128')

    def test_subnet_boundaries_and_single_address_prefixes(self):
        plan = subnet_plan('192.0.2.0/24', 26)
        self.assertEqual(plan['subnets'], ['192.0.2.0/26', '192.0.2.64/26', '192.0.2.128/26', '192.0.2.192/26'])
        self.assertEqual(plan['addresses_per_subnet'], '64')
        self.assertEqual(plan['last_address'], '192.0.2.255')
        self.assertFalse(plan['truncated'])
        self.assertEqual(subnet_plan('192.0.2.1/32', 32)['subnet_count'], '1')
        self.assertEqual(subnet_plan('192.0.2.0/31', 32)['subnet_count'], '2')
        for prefix in [23, 33, True, 25.5]:
            with self.assertRaises(ValueError):
                subnet_plan('192.0.2.0/24', prefix)

    def test_trie_agrees_with_independent_ipaddress_scan_for_generated_routes(self):
        rng = random.Random(2026)
        for version, width, cls, address_cls in [(4, 32, ipaddress.IPv4Network, ipaddress.IPv4Address), (6, 128, ipaddress.IPv6Network, ipaddress.IPv6Address)]:
            routes_text = '\n'.join(f'{cls((rng.getrandbits(width), rng.randint(0,width)), strict=False)} hop{i} {rng.randint(0,100)}' for i in range(100))
            routes = parse_routes(routes_text)
            trie = PrefixTrie(routes)
            destinations = [address_cls(rng.getrandbits(width)) for _ in range(300)]
            destinations += [route['network'].network_address for route in routes]
            for destination in destinations:
                expected = sorted([r for r in routes if destination in r['network']], key=lambda r: (-r['prefix'],r['metric'],r['id']))
                actual = trie.lookup(destination)
                self.assertEqual([r['id'] for r in actual['matches']], [r['id'] for r in expected])
                self.assertEqual(actual['winner']['id'] if actual['winner'] else None, expected[0]['id'] if expected else None)


if __name__ == '__main__':
    unittest.main()
