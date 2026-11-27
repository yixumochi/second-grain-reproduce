"""One-time, read-only import. Replay never reads the original project paths."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    args = parser.parse_args()
    package, runtime = args.package, args.runtime
    transaction = runtime / 'agent_loop_01/AGENT_LOOP_20260914_144931'
    checkpoint = transaction / 'pre_action_checkpoint'
    case = ROOT / 'case'
    if (case / 'manifest.json').exists():
        raise RuntimeError('Fixture already imported; refusing to replace its provenance.')
    files = {
        'inputs/inventory.json': package / '05_MATERIAL_STOCK/earthwise_inventory_normalized.json',
        'inputs/design_supply.json': package / '05_MATERIAL_STOCK/design_supply_families.json',
        'inputs/allocation_before.json': checkpoint / 'allocation_json.json',
        'inputs/elements.json': checkpoint / 'element_semantics_json.json',
        'inputs/action.json': checkpoint / 'design_action_state_json.json',
        'inputs/graph_before.json': package / '04_ASSEMBLY_SEMANTICS/building_assembly_graph_sanitized.json',
        'inputs/panels_before.json': package / '04_ASSEMBLY_SEMANTICS/wall_panel_load_transfer_before_agent_action.json',
        'inputs/framework_before.json': runtime / 'archsim_integration/reference_framework.json',
        'inputs/loads_before.json': runtime / 'building_assembly/karamba_panel_loads.json',
        'historical/requirement.json': package / '03_AGENT_LOOP/secondary_backing_requirement.json',
        'historical/options.json': package / '03_AGENT_LOOP/secondary_backing_options.json',
        'historical/decision.json': package / '03_AGENT_LOOP/agent_decision.json',
        'historical/ledger.json': package / '03_AGENT_LOOP/agent_backing_stock_ledger.json',
        'historical/graph_after.json': package / '04_ASSEMBLY_SEMANTICS/building_assembly_graph_after_agent_action.json',
        'historical/transfer_after.json': package / '04_ASSEMBLY_SEMANTICS/wall_panel_load_transfer_after_agent_action.json',
        'historical/framework_after.json': transaction / 'analysis_framework_after_agent_action.json',
        'historical/loads_after.json': transaction / 'karamba_panel_loads_after_agent_action.json',
        'historical/structural_result.json': package / '06_STRUCTURE/structural_result_after_agent_action.json',
        'historical/transaction_manifest.json': package / '03_AGENT_LOOP/transaction_manifest.json',
    }
    provenance = {}
    for relative, source in files.items():
        target = case / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        provenance[relative] = {
            'source': str(source), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'bytes': target.stat().st_size,
            'origin': 'FINAL_PACKAGE' if source.is_relative_to(package) else 'RECOVERED_RUNTIME'}
        value = json.loads(target.read_text(encoding='utf-8-sig'))
        provenance[relative]['semantic_sha256'] = hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    original_manifest = json.loads(files['historical/transaction_manifest.json'].read_text(encoding='utf-8-sig'))
    for relative, key in [('inputs/allocation_before.json', 'allocation_json'),
                          ('inputs/elements.json', 'element_semantics_json'),
                          ('inputs/action.json', 'design_action_state_json')]:
        assert provenance[relative]['sha256'] == original_manifest['inputs'][key]['sha256']
        provenance[relative]['matches_original_transaction_checkpoint_hash'] = True
    code = package / '08_CODE/agent'
    for relative in ['timber_agent/materials/secondary_backing_agent.py',
                     'timber_agent/materials/allocation_revision_binding.py',
                     'scripts/finalize_agent_correction_loop.py']:
        source = code / relative
        target = ROOT / 'original-code' / Path(relative).name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        provenance['../original-code/' + target.name] = {
            'source': str(source), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'origin': 'UNMODIFIED_CODE_REFERENCE'}
        if 'materials/' in relative:
            working = ROOT / 'src' / 'timber_baseline' / target.name
            working.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, working)
    manifest = {
        'schema': 'TIMBER_BASELINE_FIXTURE_V1', 'case_id': 'secondary-backing-a',
        'transaction_id': original_manifest['transaction_id'], 'files': provenance,
        'structural_evidence_scope': 'Historical file association only. No solver input signature '
          'was recorded in the original result. Import hashes do not certify a new or historically bound solve.'}
    (case / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'files_imported': len(files), 'case': str(case)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
