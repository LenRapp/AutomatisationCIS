import json
import os
from typing import Dict, Any, List

def load_json_file(path: str) -> Any:
    """Charge un fichier JSON depuis le chemin spécifié."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Le fichier {path} est introuvable.")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(data: Any, path: str) -> None:
    """Sauvegarde les données dans un fichier JSON."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_year_in_text(text: str, old_year: str = "2025", new_year: str = "2026") -> str:
    """Remplace l'année dans une chaîne de caractères."""
    return text.replace(old_year, new_year) if text else text

def generate_2026_file(file_2025_path: str, summary_file_path: str, output_path: str) -> Dict[str, int]:
    """
    Met à jour le benchmark 2025 avec les données du résumé pour créer la version 2026.
    
    Args:
        file_2025_path (str): Chemin du fichier source (version précédente).
        summary_file_path (str): Chemin du fichier résumé contenant les mises à jour.
        output_path (str): Chemin de sauvegarde du nouveau fichier.
        
    Returns:
        dict: Statistiques de la mise à jour (updated, unchanged, year_replaced).
    """
    print(f"🔄 Traitement : {file_2025_path} + {summary_file_path} -> {output_path}")
    
    # Chargement des données
    data_2025 = load_json_file(file_2025_path)
    summary_data = load_json_file(summary_file_path)

    # Indexation du résumé par control_id pour accès rapide (O(1))
    updates_map = {r.get('control_id'): r for r in summary_data if r.get('control_id')}
    
    stats = {"updated": 0, "unchanged": 0, "year_replaced": 0}
    new_data = []

    # Normalisation de la source (liste ou dict avec clé 'items')
    source_items = data_2025 if isinstance(data_2025, list) else data_2025.get('items', [])

    # Liste des champs susceptibles d'être mis à jour via le résumé
    fields_to_update = ['title', 'description', 'severity', 'remediation', 'rationale', 'impact']

    for rule in source_items:
        rule_id = rule.get('control_id')
        
        # Application des mises à jour du résumé
        if rule_id in updates_map:
            new_info = updates_map[rule_id]
            for field in fields_to_update:
                if field in new_info:
                    rule[field] = new_info[field]
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1
        # On parcourt toutes les valeurs textuelles de la règle pour remplacer l'année
        for key, value in rule.items():
            if isinstance(value, str) and "2025" in value:
                rule[key] = update_year_in_text(value)
                stats["year_replaced"] += 1
        
        new_data.append(rule)

    #Sauvegarde
    final_structure = new_data if isinstance(data_2025, list) else {"items": new_data}
    save_json_file(final_structure, output_path)
    
    return stats