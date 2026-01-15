import pdfplumber
import re
import json
import streamlit as st

def load_config():
    """Charge la configuration et prépare les regex pour la performance."""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            data = json.load(f).get("pdf_extraction", {})
            return data
    except:
        return {}

def detecter_technologie(text_page_garde):
    texte_clean = (text_page_garde or "").replace('\n', ' ')
    match = re.search(r"CIS\s+(.+?)\s+Benchmark", texte_clean, re.IGNORECASE)
    if match:
        nom_complet = match.group(1).strip()
        return " ".join(nom_complet.split()[:5]) if len(nom_complet) > 60 else nom_complet
    return "Technologie Inconnue"

def analyser_pdf_cis(fichier_pdf):
    config = load_config()
    
    # Pré-compilation des Regex
    raw_regex = config.get("rule_start_regex", r"^(\d+\.\d+)(:| )(.+)")
    try:
        REGEX_RULE = re.compile(raw_regex)
    except:
        REGEX_RULE = re.compile(r"^(\d+\.\d+)(:| )(.+)")

    SEVERITY_MAP = config.get("severity_keywords", {})
    SECTIONS_MAP = config.get("section_keywords", {})
    DEFAULT_SECTION = config.get("default_section", "description")

    resultats = []

    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            # Infos globales (Page 1 seulement)
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
            db_type = detecter_technologie(first_page_text)
            match_ver = re.search(r"v(\d+\.\d+(\.\d+)?)", first_page_text)
            version_cis = match_ver.group(1) if match_ver else "1.0"

            regle_actuelle = None
            section_en_cours = DEFAULT_SECTION

            # 2. Lecture optimisée
            for i, page in enumerate(pdf.pages):
                texte = page.extract_text()
                if not texte: continue

                lignes = texte.split('\n')

                for ligne in lignes:
                    ligne = ligne.strip()
                    if not ligne: continue

                    match = REGEX_RULE.search(ligne)

                    if match:
                        # Sauvegarde de la précédente
                        if regle_actuelle and regle_actuelle["severity"] != "Unknown":
                            regle_actuelle["title"] = regle_actuelle["title"].strip()
                            resultats.append(regle_actuelle)

                        try:
                            ctrl_id = match.group(1)
                            title = match.group(match.lastindex).strip()
                        except:
                            ctrl_id = "Unknown"
                            title = "Unknown"

                        regle_actuelle = {
                            "database_type": db_type,
                            "cis_benchmark_version": version_cis,
                            "control_id": ctrl_id,
                            "title": title,
                            "severity": "Unknown",
                            "page": i + 1
                        }
                        
                        # Init des sections vides pour éviter les KeyError plus tard
                        regle_actuelle[DEFAULT_SECTION] = ""
                        for sec_key in SECTIONS_MAP.values():
                            if sec_key != "ignore":
                                regle_actuelle[sec_key] = ""
                        
                        section_en_cours = DEFAULT_SECTION
                        continue

                    if regle_actuelle:
                        # Analyse Mots-clés (Sévérité)
                        # On ne cherche la sévérité que si elle est encore Unknown
                        if regle_actuelle["severity"] == "Unknown":
                            for sev_key, sev_val in SEVERITY_MAP.items():
                                if sev_key in ligne:
                                    regle_actuelle["severity"] = sev_val
                                    break 

                        found_section = False
                        for keyword, target_field in SECTIONS_MAP.items():
                            if ligne.startswith(keyword):
                                section_en_cours = target_field
                                found_section = True
                                break
                        
                        if found_section:
                            continue

                        # Ajout de contenu
                        if section_en_cours != "ignore":
                            # Filtre léger (ignore les numéros de page isolés)
                            if not ligne.startswith("Page ") and not ligne.startswith("CIS Benchmark"):
                                regle_actuelle[section_en_cours] += " " + ligne

            # Ajout de la dernière règle
            if regle_actuelle and regle_actuelle["severity"] != "Unknown":
                regle_actuelle["title"] = regle_actuelle["title"].strip()
                resultats.append(regle_actuelle)

    except Exception as e:
        st.error(f"Erreur technique : {e}")
        return []

    return resultats
