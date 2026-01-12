import pdfplumber
import re
import streamlit as st


def detecter_technologie(text_page_garde):
        #on enlève les sauts de ligne bizarres pour faciliter la recherche
        texte_clean = text_page_garde.replace('\n', ' ')

        # re.IGNORECASE permet de ne pas se soucier des majuscules/minuscules
        match = re.search(r"CIS\s+(.+?)\s+Benchmark", texte_clean, re.IGNORECASE)

        if match:
            nom_complet = match.group(1).strip()

            # Si le nom est très long (plus de 50 caractères),
            # c'est peut-être une erreur de lecture, on garde juste les 3 premiers mots.
            if len(nom_complet) > 60:
                 mots = nom_complet.split()
                 return " ".join(mots[:4])
            return nom_complet
        return "Technologie Inconnue"


def analyser_pdf_cis(fichier_pdf):
    resultats = []

    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            page_garde = pdf.pages[0].extract_text() if len(pdf.pages) > 0 else ""
            type_db_detecte = detecter_technologie(page_garde)

            match_version = re.search(r"v(\d+\.\d+(\.\d+)?)", page_garde)
            version_cis = match_version.group(1) if match_version else "1.0"

            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                if not texte: continue

                lignes = texte.split('\n')
                regle_actuelle = None
                section_en_cours = "description"

                for ligne in lignes:
                    ligne = ligne.strip()

                    # DÉTECTION D'UN NOUVEAU TITRE
                    # Accepte "1.1.1 Titre" OU "Safeguard 1.1 Titre"
                    match = re.search(r"^(\d+\.\d+(\.\d+)?|Safeguard \d+\.\d+)(:| )(.+)", ligne)

                    if match:
                        # SAUVEGARDE DE LA RÈGLE PRÉCÉDENTE
                        if regle_actuelle:
                            if regle_actuelle["severity"] != "Unknown":
                                regle_actuelle["description"] = regle_actuelle["description"].strip()
                                # On nettoie le titre
                                regle_actuelle["title"] = re.sub(r"\.+\s*\d+$", "", regle_actuelle["title"]).strip()
                                resultats.append(regle_actuelle)

                        regle_actuelle = {
                            "database_type": type_db_detecte,
                            "cis_benchmark_version": version_cis,
                            "control_id": match.group(1),
                            "title": match.group(4).strip(),
                            "description": "",
                            "severity": "Unknown",
                            "rationale": "",
                            "impact": "",
                            "page": i + 1
                        }
                        section_en_cours = "description"
                        continue

                    # REMPLISSAGE DES CHAMPS
                    if regle_actuelle:
                        if "Level 1" in ligne:
                            regle_actuelle["severity"] = "Medium (Level 1)"
                        elif "Level 2" in ligne:
                            regle_actuelle["severity"] = "High (Level 2)"

                        elif "IG1" in ligne:
                            regle_actuelle["severity"] = "IG1"
                        elif "IG2" in ligne:
                            regle_actuelle["severity"] = "IG2"
                        elif "IG3" in ligne:
                            regle_actuelle["severity"] = "IG3"

                        if ligne.startswith("Rationale:"):
                            section_en_cours = "rationale"
                            continue
                        elif ligne.startswith("Impact:"):
                            section_en_cours = "impact"
                            continue
                        elif ligne.startswith("Audit:"):
                            section_en_cours = "audit"
                            continue
                        elif "Profile Applicability" in ligne:
                            continue

                        if section_en_cours in ["description", "rationale", "impact"]:
                            # On évite d'ajouter des numéros de page ou des lignes vides
                            if len(ligne) > 3 and not ligne.startswith("Page"):
                                regle_actuelle[section_en_cours] += " " + ligne

                # N'oublie pas la dernière règle du fichier !
                if regle_actuelle and regle_actuelle["severity"] != "Unknown":
                    regle_actuelle["description"] = regle_actuelle["description"].strip()
                    regle_actuelle["title"] = re.sub(r"\.+\s*\d+$", "", regle_actuelle["title"]).strip()
                    resultats.append(regle_actuelle)

    except Exception as e:
        st.error(f"Erreur extraction : {e}")
        return []

    return resultats


def recuperer_tout_le_texte(fichier_pdf):
    texte_complet = ""
    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text()
                if t: texte_complet += f"\n--- P{i + 1} ---\n{t}"
    except:
        pass
    return texte_complet

'''
import json
import sys

def audit_qualite_json(fichier_json):
    
    print(f"--- 🔍 Audit Qualité : {fichier_json} ---")
    
    try:
        with open(fichier_json, 'r', encoding='utf-8') as f:
            regles = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lecture JSON : {e}")
        return

    total = len(regles)
    print(f"📊 Nombre de règles trouvées : {total}")
    


    for regle in regles:
        id_r = regle.get("control_id", "???")
        
        # Test 1 : Description vide
        if not regle.get("description", "").strip():
            print(f"   ⚠️ [{id_r}] Description vide !")
            erreurs += 1
            
        # Test 2 : Severity Unknown
        if regle.get("severity") == "Unknown":
            print(f"   ⚠️ [{id_r}] Sévérité Inconnue !")
            erreurs += 1

        titre = regle.get("title", "")
        if "...." in titre or len(titre) < 5:
            print(f"   ⚠️ [{id_r}] Titre mal nettoyé : '{titre}'")
            erreurs += 1

    if erreurs == 0:
        print("\n✅ Audit contenu : Aucune anomalie détectée.")
    else:
        print(f"\n❌ Audit contenu : {erreurs} anomalies à corriger.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        audit_qualite_json(sys.argv[1])
    else:
        print("Usage: python quality_check.py <chemin_vers_resultats.json>")'''