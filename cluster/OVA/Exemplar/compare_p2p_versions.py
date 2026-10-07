#!/usr/bin/env python3
"""Compare endpoint and structured-cabling fields in local P2P workbooks."""
import collections
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('/home/nvidia-ssh/OVA')
OUT = Path('/cluster/OVA/Exemplar')
FILES = {
    'v1.3': (ROOT / 'STN B300 SPX P2P v1.3.xlsx', range(10, 22), (22, 23)),
    'v1.7': (ROOT / 'stn_b300_spx_p2p_v1.7-draft.xlsx', range(9, 21), (21, 22)),
}
M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
TARGET = {'P01-02', 'P01-04', 'P02-02', 'P02-04'}


def read_sheet(z, number, strings):
    with z.open(f'xl/worksheets/sheet{number}.xml') as stream:
        for _, elem in ET.iterparse(stream, events=('end',)):
            if elem.tag != M + 'row':
                continue
            row = {}
            for cell in elem.findall(M + 'c'):
                col = ''.join(ch for ch in cell.attrib['r'] if ch.isalpha())
                value = cell.find(M + 'v')
                if value is None:
                    inline = cell.find(M + 'is')
                    row[col] = ''.join(t.text or '' for t in inline.iter(M + 't')) if inline is not None else ''
                else:
                    row[col] = strings[int(value.text)] if cell.get('t') == 's' else value.text or ''
            yield int(elem.attrib['r']), row
            elem.clear()


def load(version):
    path, host_sheets, spine_sheets = FILES[version]
    hosts, spines = {}, {}
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        strings = [''.join(t.text or '' for t in si.iter(M + 't')) for si in root.findall(M + 'si')]
        del root
        for sheet in host_sheets:
            for rowno, r in read_sheet(z, sheet, strings):
                host, leaf = r.get('C', ''), r.get('O', '')
                if not host.startswith('OD1-B1-EDC003-B300-') or not leaf.startswith('OD1-B1-EDC003-EW-'):
                    continue
                key = (host, r.get('D', ''), r.get('E', ''))
                if key in hosts:
                    raise ValueError(f'duplicate host key {version} {key}')
                hosts[key] = {
                    'leaf': leaf, 'leaf_port': r.get('S', ''),
                    'patch_panel': r.get('J', ''), 'patch_port_r': r.get('K', ''),
                    'patch_port_f': r.get('L', ''), 'sheet': sheet, 'row': rowno,
                }
        for sheet in spine_sheets:
            for rowno, r in read_sheet(z, sheet, strings):
                leaf = r.get('D', '')
                if not leaf.startswith('OD1-B1-EDC003-EW-'):
                    continue
                key = (leaf, r.get('F', ''))
                if key in spines:
                    raise ValueError(f'duplicate spine key {version} {key}')
                spines[key] = {
                    'spine': r.get('R', ''), 'spine_port': r.get('T', ''),
                    'structured_path': r.get('J', ''), 'source_patch_port': r.get('K', ''),
                    'destination_patch_port': r.get('L', ''), 'sheet': sheet, 'row': rowno,
                }
    return hosts, spines


def diff_records(old, new, endpoint_fields, patch_fields):
    rows = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key, {}), new.get(key, {})
        endpoint_changed = any(a.get(f) != b.get(f) for f in endpoint_fields)
        patch_changed = any(a.get(f) != b.get(f) for f in patch_fields)
        if a and b and not endpoint_changed and not patch_changed:
            continue
        rows.append({'key': key, 'in_v13': bool(a), 'in_v17': bool(b),
                     'endpoint_changed': endpoint_changed, 'patch_changed': patch_changed,
                     'v13': a, 'v17': b})
    return rows


old_hosts, old_spines = load('v1.3')
new_hosts, new_spines = load('v1.7')
host_diff = diff_records(old_hosts, new_hosts, ('leaf', 'leaf_port'),
                         ('patch_panel', 'patch_port_r', 'patch_port_f'))
spine_diff = diff_records(old_spines, new_spines, ('spine', 'spine_port'),
                          ('structured_path', 'source_patch_port', 'destination_patch_port'))
target_spine_diff = [r for r in spine_diff if r['key'][0][-6:] in TARGET]
summary = {
    'file_v13': str(FILES['v1.3'][0]), 'file_v17': str(FILES['v1.7'][0]),
    'host_rows': {'v13': len(old_hosts), 'v17': len(new_hosts)},
    'spine_rows': {'v13': len(old_spines), 'v17': len(new_spines)},
    'host_changes': {'total': len(host_diff),
                     'endpoint': sum(r['endpoint_changed'] for r in host_diff),
                     'patch': sum(r['patch_changed'] for r in host_diff)},
    'spine_changes': {'total': len(spine_diff),
                      'endpoint': sum(r['endpoint_changed'] for r in spine_diff),
                      'patch': sum(r['patch_changed'] for r in spine_diff)},
    'spine_changes_by_leaf': dict(collections.Counter(
        r['key'][0][-6:] for r in spine_diff)),
    'target_spine_changes': {'total': len(target_spine_diff),
                             'endpoint': sum(r['endpoint_changed'] for r in target_spine_diff),
                             'patch': sum(r['patch_changed'] for r in target_spine_diff)},
    'host_diffs': host_diff, 'spine_diffs': spine_diff,
}
(OUT / 'p2p-v13-v17-diff.json').write_text(json.dumps(summary, indent=2) + '\n')

with (OUT / 'fabric-target-leaf-spine-v1.7.csv').open('w', newline='') as stream:
    fields = ['plane', 'leaf', 'leaf_port', 'spine', 'spine_port', 'structured_cabling_path',
              'source_patch_port', 'destination_patch_port', 'workbook_sheet', 'workbook_row']
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for (leaf, port), r in sorted(new_spines.items()):
        if leaf[-6:] not in TARGET:
            continue
        writer.writerow({'plane': leaf[-6:-3], 'leaf': leaf, 'leaf_port': port,
                         'spine': r['spine'], 'spine_port': r['spine_port'],
                         'structured_cabling_path': r['structured_path'],
                         'source_patch_port': r['source_patch_port'],
                         'destination_patch_port': r['destination_patch_port'],
                         'workbook_sheet': r['sheet'], 'workbook_row': r['row']})

by_spine = collections.defaultdict(dict)
for (leaf, port), r in new_spines.items():
    if leaf[-6:] not in TARGET:
        continue
    by_spine[(leaf[-6:-3], r['spine'])][leaf[-6:]] = (leaf, port, r)
with (OUT / 'fabric-target-path-pairs-v1.7.csv').open('w', newline='') as stream:
    fields = ['plane', 'source_leaf', 'source_leaf_port', 'source_spine_port',
              'source_patch_path', 'source_patch_port', 'spine', 'destination_spine_port',
              'destination_leaf', 'destination_leaf_port', 'destination_patch_path',
              'destination_patch_port', 'source_workbook_row', 'destination_workbook_row']
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for (plane, spine), peers in sorted(by_spine.items()):
        left, right = ('P01-02', 'P01-04') if plane == 'P01' else ('P02-04', 'P02-02')
        a, ap, ar = peers[left]
        b, bp, br = peers[right]
        writer.writerow({'plane': plane, 'source_leaf': a, 'source_leaf_port': ap,
                         'source_spine_port': ar['spine_port'],
                         'source_patch_path': ar['structured_path'],
                         'source_patch_port': ar['source_patch_port'],
                         'spine': spine, 'destination_spine_port': br['spine_port'],
                         'destination_leaf': b, 'destination_leaf_port': bp,
                         'destination_patch_path': br['structured_path'],
                         'destination_patch_port': br['destination_patch_port'],
                         'source_workbook_row': ar['row'], 'destination_workbook_row': br['row']})

print(json.dumps({k: v for k, v in summary.items() if not k.endswith('_diffs')}, indent=2))
