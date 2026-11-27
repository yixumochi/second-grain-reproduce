"""Reuse a frozen allocation only when complete input content is unchanged.

Revision references are rebound in a copy. Frozen solver files are immutable.
"""
import copy
import hashlib
import json

REVISION_KEYS = frozenset(('geometry_revision', 'demand_revision',
                           'floor_demand_revision', 'building_demand_revision'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def rebind_allocation(current, frozen, result):
    mapping = {}
    changes = []

    def compare(old, new, path='input', field=None):
        if type(old) is not type(new):
            raise ValueError('STALE_FROZEN_TARGET: type changed at '+path)
        if isinstance(old, dict):
            if old.keys() != new.keys():
                raise ValueError('STALE_FROZEN_TARGET: fields changed at '+path)
            for key in old:
                compare(old[key], new[key], path+'.'+key, key)
        elif isinstance(old, list):
            if len(old) != len(new):
                raise ValueError('STALE_FROZEN_TARGET: count changed at '+path)
            for i, (a, b) in enumerate(zip(old, new)):
                compare(a, b, path+'['+str(i)+']')
        elif old != new:
            if field not in REVISION_KEYS or not isinstance(old, str) or not old or not new:
                raise ValueError('STALE_FROZEN_TARGET: content changed at '+path)
            if old in mapping and mapping[old] != new:
                raise ValueError('STALE_FROZEN_TARGET: inconsistent revision at '+path)
            mapping[old] = new
            changes.append(path)

    compare(frozen, current)
    if result.get('input_digest') != digest(frozen):
        raise ValueError('STALE_GLOBAL_PATCHWORK_RESULT')
    for key in ('geometry_revision', 'demand_revision'):
        if result.get(key) != frozen['building'][key]:
            raise ValueError('STALE_ALLOCATION_GEOMETRY: '+key)
        if current['dispatch'][key] != current['building'][key]:
            raise ValueError('STALE_DISPATCH_REVISION: '+key)

    def replace(value):
        if isinstance(value, dict):
            return {k: mapping.get(v, v) if k in REVISION_KEYS and isinstance(v, str)
                    else replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return copy.deepcopy(value)

    bound = replace(result)
    bound['input_digest'] = digest(current)
    if changes:
        bound['revision_binding'] = dict(
            status='CONTENT_IDENTICAL_REVISION_REBIND',
            original_input_digest=result['input_digest'],
            original_result_digest=digest(result),
            current_input_digest=bound['input_digest'],
            changed_reference_paths=changes, revision_map=mapping,
            allocation_recomputed=False, frozen_files_modified=False)
    return bound
