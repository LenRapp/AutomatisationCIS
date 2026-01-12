import sys
import os
from src.extraction import analyser_pdf_cis
from src.generator import convertir_en_json

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_referentiel.py <chemin_du_pdf>")
        return

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Erreur : Le fichier '{pdf_path}' n'existe pas.")
        return

    print(f"Analyse de {pdf_path} en cours...")
    regles = analyser_pdf_cis(pdf_path)

    if not regles:
        print("Aucune règle trouvée. Vérifiez le format du PDF.")
        return

    print(f"{len(regles)} règles trouvées.")
    json_output = convertir_en_json(regles)

    output_filename = "referentiel.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(json_output)
    
    print(f"✅ Fichier généré avec succès : {output_filename}")

if __name__ == "__main__":
    main()
