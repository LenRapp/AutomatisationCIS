import pdfplumber
import re
import streamlit as st


def detecter_technologie(first_page_text):
    text = first_page_text.lower()
    if "oracle" in text: return "Oracle Database"
    if "postgresql" in text: return "PostgreSQL"
    if "cis controls" in text: return "CIS Controls (Général)"
    return "Technologie inconnue"


def analyser_pdf_cis(fichier_pdf):
    resultats = []

    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            # 1. DÉTECTION GLOBALE
            page_garde = pdf.pages[0].extract_text() if len(pdf.pages) > 0 else ""
            type_db_detecte = detecter_technologie(page_garde)

            # 2. ANALYSE DES PAGES
            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                if not texte: continue

                lignes = texte.split('\n')
                regle_actuelle = None
                section_en_cours = "description"

                for ligne in lignes:
                    ligne = ligne.strip()

                    match = re.search(r"^(\d+\.\d+(\.\d+)?|Safeguard \d+\.\d+)(:| )(.+)", ligne)

                    if match:
                        if regle_actuelle:
                            # Petit nettoyage final de la description avant d'enregistrer
                            regle_actuelle["description"] = regle_actuelle["description"].strip()
                            resultats.append(regle_actuelle)

                        regle_actuelle = {
                            "database_type": type_db_detecte,
                            "cis_benchmark_version": "Inconnue",
                            "control_id": match.group(1),
                            "title": match.group(4).strip(),
                            "description": "",
                            "severity": "Unknown",
                            "rationale": "",
                            "impact": "",
                            "page": i + 1
                        }
                        continue
                    if regle_actuelle:
                        # Si la ligne contient ces mots, on ne l'ajoute pas à la description
                        # mais on essaie d'en extraire des infos utiles
                        if "Asset Type:" in ligne or "Security Function:" in ligne:
                            # On tente de récupérer les IG (IG1, IG2, IG3) pour la sévérité
                            igs = []
                            if "IG1" in ligne: igs.append("IG1")
                            if "IG2" in ligne: igs.append("IG2")
                            if "IG3" in ligne: igs.append("IG3")

                            if igs:
                                regle_actuelle["severity"] = ", ".join(igs)

                            continue  # On passe à la ligne suivante sans l'ajouter au texte

                        # Ignore les barres verticales seules ou les en-têtes de bas de page
                        if ligne in ["|", "| |", "| | |"] or "Controls and Safeguards Index" in ligne:
                            continue
                        if ligne.startswith("Rationale:"):
                            section_en_cours = "rationale"
                            continue
                        elif ligne.startswith("Impact:"):
                            section_en_cours = "impact"
                            continue

                        # Ajout du texte
                        if section_en_cours in regle_actuelle:
                            # On ajoute un espace seulement si nécessaire
                            regle_actuelle[section_en_cours] += " " + ligne

                if regle_actuelle:
                    regle_actuelle["description"] = regle_actuelle["description"].strip()
                    resultats.append(regle_actuelle)

    except Exception as e:
        st.error(f"Erreur extraction : {e}")
        return []

    return resultats


# FONCTION LECTURE BRUTE
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