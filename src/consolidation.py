import json
import glob
import os

def main():
    # 1. Chargement de la configuration externe
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ Erreur : config.json manquant.")
        return

    # On récupère les paramètres depuis la config (rien en dur)
    mapping = config.get("required_fields", {})
    source_dir = config.get("source_folder", "inputs_json")
    output_path = config.get("output_file", "resume_cis_intermediaire.json")
    default_val = config.get("default_value", "")

    # 2. Lecture dynamique avec GLOB
    # On cherche tous les .json dans le dossier source
    pattern = os.path.join(source_dir, "*.json")
    files = glob.glob(pattern)
    
    results = []

    print(f"🔄 Traitement de {len(files)} fichiers...")

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Gestion souple : liste ou objet unique
            items = data if isinstance(data, list) else data.get("items", [data])

            for item in items:
                clean_obj = {}
                
                # 3. Extraction dynamique basée sur la config
                # Le script ne sait pas ce qu'est "id" ou "titre", il suit juste le mapping
                for target_field, source_keys in mapping.items():
                    found_value = None
                    
                    # On teste les clés possibles définies dans le JSON
                    for key in source_keys:
                        # Utilisation de .get() pour la sécurité (évite KeyError)
                        val = item.get(key)
                        if val:
                            found_value = val
                            break # On a trouvé, on arrête de chercher
                    
                    # Si trouvé, on ajoute, sinon valeur par défaut
                    if found_value:
                        # Petit nettoyage basique (strip)
                        clean_obj[target_field] = str(found_value).strip()
                    else:
                        clean_obj[target_field] = default_val

                # On ajoute au résultat final seulement si on a au moins un champ rempli
                if any(v != default_val for v in clean_obj.values()):
                    clean_obj["source_file"] = os.path.basename(file_path)
                    results.append(clean_obj)

        except Exception as e:
            # Bloc try/except pour ne pas casser le script complet sur un fichier pourri
            print(f"⚠️ Erreur sur le fichier {file_path} : {e}")

    # 4. Sortie : Génération du fichier pivot
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"✅ Fichier pivot généré : {output_path} ({len(results)} règles)")
    except Exception as e:
        print(f"❌ Erreur d'écriture : {e}")

if __name__ == "__main__":
    main()