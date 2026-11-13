"""Bounded IPv4/IPv6 forwarding-table analysis; no network traffic is sent."""
import ipaddress
import re


def network(text):
    if not isinstance(text, str) or len(text) > 100 or '/' not in text or '%' in text:
        raise ValueError('Enter an unscoped CIDR network, such as 192.0.2.0/24 or 2001:db8::/32.')
    try:
        result = ipaddress.ip_network(text, strict=True)
    except ValueError:
        try:
            normalized = ipaddress.ip_network(text, strict=False)
        except ValueError:
            raise ValueError('Invalid CIDR network.') from None
        raise ValueError(f'Host bits are set. Use the network boundary {normalized}.') from None
    # Require an explicit decimal prefix rather than IPv4 netmask syntax.
    suffix = text.rsplit('/', 1)[1]
    if not re.fullmatch(r'0|[1-9][0-9]{0,2}', suffix):
        raise ValueError('Use a decimal prefix length after the slash.')
    return result


def address(text):
    if not isinstance(text, str) or len(text) > 64 or '%' in text:
        raise ValueError('Enter an unscoped IPv4 or IPv6 destination address.')
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        raise ValueError('Invalid destination IP address.') from None


def parse_routes(text):
    if not isinstance(text, str) or len(text) > 32000:
        raise ValueError('Route text is limited to 32,000 characters.')
    routes = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f'Line {line_number}: use CIDR next-hop-label metric.')
        cidr, hop, metric = fields
        try:
            prefix = network(cidr)
        except ValueError as error:
            raise ValueError(f'Line {line_number}: {error}') from None
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}', hop):
            raise ValueError(f'Line {line_number}: next-hop labels must be 1–40 letters, digits, dots, underscores, colons, or hyphens.')
        if not re.fullmatch(r'0|[1-9][0-9]{0,4}', metric) or int(metric) > 65535:
            raise ValueError(f'Line {line_number}: metric must be an integer from 0 to 65535.')
        routes.append({'id': len(routes) + 1, 'line': line_number, 'cidr': str(prefix), 'version': prefix.version,
                       'prefix': prefix.prefixlen, 'hop': hop, 'metric': int(metric), 'network': prefix})
        if len(routes) > 128:
            raise ValueError('Use at most 128 routes.')
    return routes


def public_route(route):
    return {k: v for k, v in route.items() if k != 'network'}


class PrefixTrie:
    def __init__(self, routes):
        self.roots = {4: {'routes': [], 'children': {}}, 6: {'routes': [], 'children': {}}}
        for route in routes:
            node = self.roots[route['version']]
            value, width = int(route['network'].network_address), route['network'].max_prefixlen
            for depth in range(route['prefix']):
                bit = (value >> (width - depth - 1)) & 1
                node = node['children'].setdefault(bit, {'routes': [], 'children': {}})
            node['routes'].append(route)

    def lookup(self, destination):
        node = self.roots[destination.version]
        matches, checkpoints = list(node['routes']), []
        if node['routes']:
            checkpoints.append({'depth': 0, 'routes': [r['id'] for r in node['routes']]})
        value, width, traversed = int(destination), destination.max_prefixlen, 0
        for depth in range(width):
            bit = (value >> (width - depth - 1)) & 1
            if bit not in node['children']:
                break
            node = node['children'][bit]
            traversed = depth + 1
            if node['routes']:
                matches.extend(node['routes'])
                checkpoints.append({'depth': traversed, 'routes': [r['id'] for r in node['routes']]})
        matches.sort(key=lambda r: (-r['prefix'], r['metric'], r['id']))
        return {'matches': [public_route(r) for r in matches], 'winner': public_route(matches[0]) if matches else None,
                'checkpoints': checkpoints, 'traversed_bits': traversed}


def lookup(routes_text, destination_text):
    routes, destination = parse_routes(routes_text), address(destination_text)
    result = PrefixTrie(routes).lookup(destination)
    winner = result['winner']
    if winner:
        reason = f"Route #{winner['id']} has the longest matching /{winner['prefix']} prefix."
        tied = [r for r in result['matches'] if r['prefix'] == winner['prefix']]
        if len(tied) > 1:
            reason += f" Among {len(tied)} equally specific routes, lower metric wins; exact ties use input order."
    else:
        reason = 'No matching route exists in this address family; the model drops this destination.'
    return {'destination': str(destination), 'version': destination.version, 'width': destination.max_prefixlen,
            'bits': f'{int(destination):0{destination.max_prefixlen}b}', 'routes': [public_route(r) for r in routes],
            'reason': reason, **result}


def subnet_plan(cidr, new_prefix):
    parent = network(cidr)
    if type(new_prefix) is not int or not parent.prefixlen <= new_prefix <= parent.max_prefixlen:
        raise ValueError(f'New prefix must be an integer from {parent.prefixlen} to {parent.max_prefixlen}.')
    total, size = 2 ** (new_prefix - parent.prefixlen), 2 ** (parent.max_prefixlen - new_prefix)
    # Construct only the bounded preview. Never enumerate the full address space.
    cls = ipaddress.IPv4Network if parent.version == 4 else ipaddress.IPv6Network
    subnets = [str(cls((int(parent.network_address) + i * size, new_prefix))) for i in range(min(total, 64))]
    return {'cidr': str(parent), 'version': parent.version, 'prefix': parent.prefixlen, 'new_prefix': new_prefix,
            'first_address': str(parent.network_address), 'last_address': str(parent.broadcast_address),
            'address_count': str(parent.num_addresses), 'subnet_count': str(total), 'addresses_per_subnet': str(size),
            'subnets': subnets, 'truncated': total > 64}


EXAMPLES = {
    'office': {'destination': '10.20.30.42', 'routes': '# Office forwarding table\n0.0.0.0/0 upstream 1\n10.0.0.0/8 core 10\n10.20.0.0/16 regional 20\n10.20.30.0/24 office-a 50\n10.20.30.0/24 office-b 20\n10.20.30.42/32 service-host 900'},
    'ipv6': {'destination': '2001:db8:1200:42::7', 'routes': '::/0 upstream-v6 1\n2001:db8::/32 campus 10\n2001:db8:1200::/40 region-v6 30\n2001:db8:1200:42::/64 lab-v6 50'},
    'gap': {'destination': '198.51.100.8', 'routes': '192.0.2.0/24 documentation-a 10\n203.0.113.0/24 documentation-c 10\n2001:db8::/32 ipv6-only 10'},
}
