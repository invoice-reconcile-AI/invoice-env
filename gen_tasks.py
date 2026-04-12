import copy
import re

with open('scen.txt', 'r', encoding='utf-8') as f:
    scen_str = f.read()

# We just want to duplicate the scenarios by literal string replacement
# Find the start of "easy-exact-match": {
blocks = re.findall(r'(\s+"[a-zA-Z0-9\-]+": \{.*?\n    \},)', scen_str, re.DOTALL)
if not blocks:
    print("Could not find blocks")

out_lines = [
    'from typing import Any',
    'from datetime import date',
    'from decimal import Decimal',
    'from server.models import Invoice, LineItem, PurchaseOrder, CompareItemAction, DiscrepancyType, GoodsReceivedNote, Discrepancy',
    '\n'
]
out_lines.append(scen_str[:-2]) # remove the closing }

for i in range(1, 45):
    block = blocks[i % len(blocks)]
    # rename key
    base_k = re.search(r'"([a-zA-Z0-9\-]+)":', block).group(1)
    new_k = f'{base_k}-var-{i}'
    block = block.replace(f'"{base_k}":', f'"{new_k}":')
    out_lines.append(block)

out_lines.append('\n}\n')

with open('server/tasks.py', 'w', encoding='utf-8') as f:
    f.writelines(out_lines)

print("Generated server/tasks.py")
