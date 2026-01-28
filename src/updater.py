import json
import os
from typing import Dict, Any

def load_json_file(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(data: Any, path: str) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_year_in_text(text: str, old_year: str, new_year: str) -> str:
    if not isinstance(text, str): return text
    return text.replace(old_year, new_year)

def normalize_id(id_val):
    """Nettoyage des IDs (ex: ' 3.3.3 ' -> '3.3.3')."""
    if id_val is None:
        return ""
    return str(id_val).strip().replace(" ", "")

def run_dynamic_update(
        source_path: str,
        summary_path: str,
        output_json: str,
        old_year: str = "2025",
        new_year: str = "2026",
        progress_callback=None
) -> Dict[str, int]:
    # Chargement
    data_source = load_json_file(source_path)
    data_summary = load_json_file(summary_path)

    deleted_ids = set()
    updates_map = {}
    added_items = []

    # Analyse du résumé
    if isinstance(data_summary, dict):
        raw_deleted = data_summary.get('removed', []) + data_summary.get('deleted', [])
        added_items = data_summary.get('added', [])
        for r in raw_deleted:
            rid = normalize_id(r.get('control_id'))
            if rid: deleted_ids.add(rid)
        for mod in data_summary.get('modified', []):
            rid = normalize_id(mod.get('control_id'))
            if rid: updates_map[rid] = mod
    elif isinstance(data_summary, list):
        for r in data_summary:
            rid = normalize_id(r.get('control_id'))
            if rid: updates_map[rid] = r

    # Traitement
    source_items = data_source if isinstance(data_source, list) else data_source.get('items', [])
    final_items = []
    stats = {"deleted": 0, "updated": 0, "unchanged": 0, "added": 0, "year_replaced": 0}
    fields = ['title', 'description', 'severity', 'remediation', 'rationale', 'impact']
    total = len(source_items)

    for i, rule in enumerate(source_items):
        if progress_callback:
            progress_callback((i / total) * 0.9)

        clean_id = normalize_id(rule.get('control_id'))

        if clean_id in deleted_ids:
            stats['deleted'] += 1
            continue

        if clean_id in updates_map:
            changes = updates_map[clean_id].get('changes', updates_map[clean_id])
            for f in fields:
                val = changes.get(f)
                if isinstance(val, dict) and 'new' in val:
                    rule[f] = val['new']
                elif val:
                    rule[f] = val
            stats['updated'] += 1
        else:
            stats['unchanged'] += 1

        for k, v in rule.items():
            if isinstance(v, str) and old_year in v:
                rule[k] = update_year_in_text(v, old_year, new_year)
                stats['year_replaced'] += 1
        final_items.append(rule)

    # Ajouts
    for new_rule in added_items:
        for k, v in new_rule.items():
            if isinstance(v, str) and old_year in v:
                new_rule[k] = update_year_in_text(v, old_year, new_year)
        final_items.append(new_rule)
        stats['added'] += 1

    if progress_callback: progress_callback(1.0)

    # Sauvegarde
    save_json_file({"items": final_items}, output_json)
    return stats