import json

def compare_rules(old_rules, new_rules):
    old_rules_dict = {rule['control_id']: rule for rule in old_rules}
    new_rules_dict = {rule['control_id']: rule for rule in new_rules}

    added_ids = new_rules_dict.keys() - old_rules_dict.keys()
    deleted_ids = old_rules_dict.keys() - new_rules_dict.keys()
    common_ids = old_rules_dict.keys() & new_rules_dict.keys()

    added = [new_rules_dict[id] for id in added_ids]
    deleted = [old_rules_dict[id] for id in deleted_ids]
    modified = []

    for id in common_ids:
        old_rule = old_rules_dict[id]
        new_rule = new_rules_dict[id]
        
        # Comparaison détaillée des champs
        field_changes = {}
        all_keys = set(old_rule.keys()) | set(new_rule.keys())

        for key in all_keys:
            old_value = old_rule.get(key, '')
            new_value = new_rule.get(key, '')
            # Normaliser les chaînes pour la comparaison
            if isinstance(old_value, str) and isinstance(new_value, str):
                if old_value.strip() != new_value.strip():
                    field_changes[key] = {'old': old_value.strip(), 'new': new_value.strip()}
            elif old_value != new_value:
                field_changes[key] = {'old': old_value, 'new': new_value}
        
        # Ignorer les changements non pertinents (ex: numéro de page)
        if 'page' in field_changes:
            del field_changes['page']

        if field_changes:
            modified.append({
                'control_id': id,
                'changes': field_changes
            })

    return {
        'added': added,
        'deleted': deleted,
        'modified': modified
    }

if __name__ == '__main__':
    # Exemple de données basé sur la structure de extraction.py
    old_rules_data = [
        {
            "control_id": "1.1", "title": "Rule 1", "description": "Description 1", 
            "severity": "Level 1", "cis_benchmark_version": "1.0", "page": 10
        },
        {
            "control_id": "1.2", "title": "Rule 2", "description": "Old Description 2", 
            "severity": "Level 1", "cis_benchmark_version": "1.0", "page": 12
        },
        {
            "control_id": "1.3", "title": "Rule 3", "description": "Description 3", 
            "severity": "Level 2", "cis_benchmark_version": "1.0", "page": 15
        }
    ]

    new_rules_data = [
        {
            "control_id": "1.1", "title": "Rule 1", "description": "Description 1", 
            "severity": "Level 1", "cis_benchmark_version": "2.0", "page": 11
        },
        {
            "control_id": "1.2", "title": "Rule 2 - Modified Title", "description": "  New Description 2  ", 
            "severity": "Level 1", "cis_benchmark_version": "2.0", "page": 13
        },
        {
            "control_id": "1.4", "title": "Rule 4", "description": "Description 4", 
            "severity": "Level 1", "cis_benchmark_version": "2.0", "page": 18
        }
    ]

    differences = compare_rules(old_rules_data, new_rules_data)

    print("Differences found:")
    print("\nAdded:", json.dumps(differences['added'], indent=2))
    print("\nDeleted:", json.dumps(differences['deleted'], indent=2))
    print("\nModified:", json.dumps(differences['modified'], indent=2))
