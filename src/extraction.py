import pdfplumber
import re
import streamlit as st


# --- FONCTION 1 : Analyse Hybride (Compatible Patron) ---
def analyser_pdf_cis(fichier_pdf):
    """
    Extrait les règles en format JSON complet (Benchmark ou Controls).
    """
    resultats = []

    # Valeurs par défaut (à adapter plus tard dynamiquement)
    TYPE_DB = "Oracle Database"
    VERSION_CIS = "1.1"

    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            # On lit page par page
            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                if not texte: continue

                lignes = texte.split('\n')
                regle_actuelle = None
                section_en_cours = "description"  # description, rationale, impact...

                for ligne in lignes:
                    ligne = ligne.strip()

                    # --- LA CORRECTION EST ICI (REGEX HYBRIDE) ---
                    # Accepte "Safeguard 1.1" OU "1.1.1"
                    match = re.search(r"^(\d+\.\d+(\.\d+)?|Safeguard \d+\.\d+)(:| )(.+)", ligne)

                    if match:
                        # On sauvegarde la règle d'avant
                        if regle_actuelle:
                            resultats.append(regle_actuelle)

                        # On crée la nouvelle règle avec TOUS les champs du patron
                        regle_actuelle = {
                            "database_type": TYPE_DB,
                            "cis_benchmark_version": VERSION_CIS,
                            "control_id": match.group(1),  # Ex: 1.1.1
                            "title": match.group(4).strip(),  # Ex: Ensure remote login...
                            "description": "",
                            "severity": "Unknown",  # Sera mis à jour si trouvé
                            "rationale": "",
                            "impact": "",
                            "page": i + 1
                        }
                        section_en_cours = "description"
                        continue

                    # --- REMPLISSAGE INTELLIGENT ---
                    if regle_actuelle:
                        # Détection des mots-clés pour changer de case
                        if ligne.startswith("Rationale:"):
                            section_en_cours = "rationale"
                            continue
                        elif ligne.startswith("Impact:"):
                            section_en_cours = "impact"
                            continue
                        elif "Level 1" in ligne:
                            regle_actuelle["severity"] = "Level 1"
                        elif "Level 2" in ligne:
                            regle_actuelle["severity"] = "Level 2"

                        # On remplit la bonne case selon la section active
                        if section_en_cours in regle_actuelle:
                            regle_actuelle[section_en_cours] += " " + ligne

                # Ne pas oublier la dernière règle
                if regle_actuelle:
                    resultats.append(regle_actuelle)

    except Exception as e:
        st.error(f"Erreur extraction : {e}")
        return []

    return resultats


# --- FONCTION 2 : Lecture Brute (Inchangée) ---
def recuperer_tout_le_texte(fichier_pdf):
    texte_complet = ""
    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                c = page.extract_text()
                if c: texte_complet += f"\n--- P {i + 1} ---\n{c}"
    except:
        pass
    return texte_complet