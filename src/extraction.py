import pdfplumber
import re
import streamlit as st

# FONCTION 1 : Analyse intelligente
def analyser_pdf_cis(fichier_pdf):
    """Extrait les règles Safeguard structurées."""
    resultats = []
    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                if not texte: continue
                lignes = texte.split('\n')
                regle_actuelle = None
                for ligne in lignes:
                    ligne = ligne.strip()
                    match = re.search(r"^(Safeguard \d+\.\d+):(.+)", ligne)
                    if match:
                        if regle_actuelle: resultats.append(regle_actuelle)
                        regle_actuelle = {
                            "page": i + 1,
                            "code": match.group(1),
                            "titre": match.group(2).strip(),
                            "description": ""
                        }
                        continue
                    if regle_actuelle:
                        if any(x in ligne for x in
                               ["Asset Type:", "Security Function:", "IG1", "CIS Controls", "Control"]):
                            continue
                        if len(ligne) > 5:
                            regle_actuelle["description"] += " " + ligne
                if regle_actuelle: resultats.append(regle_actuelle)
    except Exception as e:
        st.error(f"Erreur : {e}")
    return resultats


# FONCTION 2 : Extraction brute
def recuperer_tout_le_texte(fichier_pdf):
    """Extrait tout le texte brut du PDF."""
    texte_complet = ""
    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            # Barre de progression
            barre_progression = st.progress(0)
            total_pages = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                contenu_page = page.extract_text()
                if contenu_page:
                    texte_complet += f"\n\n--- PAGE {i + 1} ---\n"
                    texte_complet += contenu_page

                # Mise à jour de la barre
                barre_progression.progress((i + 1) / total_pages)

            barre_progression.empty()  # On efface la barre
    except Exception as e:
        st.error(f"Erreur lecture brute : {e}")
        return ""
    return texte_complet