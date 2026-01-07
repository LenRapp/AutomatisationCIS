import json

def convertir_en_json(liste_regles):
    """
    Prend une liste de dictionnaires (règles) et retourne une chaîne JSON bien formatée.
    """
    # ensure_ascii=False permet de garder les accents lisibles
    # indent=4 permet d'avoir un fichier aéré et lisible
    json_str = json.dumps(liste_regles, indent=4, ensure_ascii=False)
    return json_str