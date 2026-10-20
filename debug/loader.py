# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: 2026 the NijiN authors
"""Load the operator's tables and check them against the schema.

Tables are data: observation points, injections, probes. The public tree ships
empty templates and this loader; the values live in the operator's local copy.
A table that does not match its schema is refused before anything is armed.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = ('observe', 'inject', 'probe')
TOP_KEY = {'observe': 'points', 'inject': 'injections', 'probe': 'probes'}


def _type_ok(value, want):
    if want == 'object':
        return isinstance(value, dict)
    if want == 'array':
        return isinstance(value, list)
    if want == 'string':
        return isinstance(value, str)
    if want == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if want == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if want == 'boolean':
        return isinstance(value, bool)
    return True


def validate(doc, schema, path='$'):
    """Small JSON-schema subset: type, required, properties, items, enum."""
    errors = []
    if 'type' in schema and not _type_ok(doc, schema['type']):
        return [f'{path}: expected {schema["type"]}']
    if 'enum' in schema and doc not in schema['enum']:
        errors.append(f'{path}: {doc!r} not in {schema["enum"]}')
    if isinstance(doc, dict):
        for name in schema.get('required', []):
            if name not in doc:
                errors.append(f'{path}: missing {name}')
        for name, value in doc.items():
            sub = schema.get('properties', {}).get(name)
            if sub:
                errors += validate(value, sub, f'{path}.{name}')
            elif schema.get('additionalProperties') is False:
                errors.append(f'{path}: unknown field {name}')
    if isinstance(doc, list) and 'items' in schema:
        for index, value in enumerate(doc):
            errors += validate(value, schema['items'], f'{path}[{index}]')
    return errors


def load(path, kind):
    """Load one table. Raises ValueError with every schema problem at once."""
    if kind not in KINDS:
        raise ValueError(f'unknown table kind: {kind}')
    doc = json.loads(Path(path).read_text())
    schema = json.loads((HERE / 'schema' / f'{kind}.schema.json').read_text())
    errors = validate(doc, schema)
    if errors:
        raise ValueError(f'{path}: ' + '; '.join(errors))
    if TOP_KEY[kind] not in doc:
        raise ValueError(f'{path}: missing {TOP_KEY[kind]}')
    return doc


def template(kind):
    return json.loads((HERE / 'tables' / f'{kind}.json').read_text())
