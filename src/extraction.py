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
    # This function is now designed to be thread-safe for use with Streamlit
    # by avoiding direct calls to Streamlit UI elements (e.g., st.error).
    # Errors should be returned or raised to be handled by the calling thread.
    
    print(f"Starting analysis for file: {getattr(fichier_pdf, 'name', 'unknown file')}")
    
    config = load_config()
    
    raw_regex = config.get("rule_start_regex", r"^(\d+\.\d+)(:| )(.+)")
    try:
        REGEX_RULE = re.compile(raw_regex)
    except re.error as e:
        print(f"Regex error in config: {e}")
        REGEX_RULE = re.compile(r"^(\d+\.\d+)(:| )(.+)")

    SEVERITY_MAP = config.get("severity_keywords", {})
    SECTIONS_MAP = config.get("section_keywords", {})
    DEFAULT_SECTION = config.get("default_section", "description")

    resultats = []

    try:
        with pdfplumber.open(fichier_pdf) as pdf:
            if not pdf.pages:
                print("Warning: PDF has no pages.")
                return []

            # Infos globales (Page 1 seulement)
            first_page_text = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=3) or ""
            db_type = detecter_technologie(first_page_text)
            match_ver = re.search(r"v(\d+\.\d+(\.\d+)?)", first_page_text)
            version_cis = match_ver.group(1) if match_ver else "1.0.0"

            regle_actuelle = None
            section_en_cours = DEFAULT_SECTION

            print(f"Total pages to process: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                print(f"  - Processing page {i + 1}/{len(pdf.pages)}...")
                try:
                    texte = page.extract_text(x_tolerance=1, y_tolerance=3)
                    if not texte:
                        print(f"    - Page {i + 1} has no extractable text.")
                        continue
                except Exception as e:
                    print(f"    - Error extracting text from page {i + 1}: {e}")
                    continue

                lignes = texte.split('\n')

                for ligne in lignes:
                    ligne = ligne.strip()
                    if not ligne:
                        continue

                    match = REGEX_RULE.search(ligne)

                    if match:
                        if regle_actuelle and regle_actuelle.get("severity") != "Unknown":
                            regle_actuelle["title"] = regle_actuelle["title"].strip()
                            for key, value in regle_actuelle.items():
                                if isinstance(value, str):
                                    regle_actuelle[key] = value.strip()
                            resultats.append(regle_actuelle)

                        ctrl_id = match.group(1)
                        title = match.group(match.lastindex).strip()

                        regle_actuelle = {
                            "database_type": db_type,
                            "cis_benchmark_version": version_cis,
                            "control_id": ctrl_id,
                            "title": title,
                            "severity": "Unknown",
                            "page": i + 1
                        }
                        
                        for sec_key in SECTIONS_MAP.values():
                            if sec_key != "ignore":
                                regle_actuelle[sec_key] = ""
                        regle_actuelle[DEFAULT_SECTION] = ""
                        section_en_cours = DEFAULT_SECTION
                        continue

                    if regle_actuelle:
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

                        if section_en_cours != "ignore":
                            if not ligne.startswith("Page ") and not ligne.startswith("CIS Benchmark"):
                                regle_actuelle[section_en_cours] += " " + ligne

            if regle_actuelle and regle_actuelle.get("severity") != "Unknown":
                regle_actuelle["title"] = regle_actuelle["title"].strip()
                for key, value in regle_actuelle.items():
                    if isinstance(value, str):
                        regle_actuelle[key] = value.strip()
                resultats.append(regle_actuelle)
        
        print(f"Finished analysis for {getattr(fichier_pdf, 'name', 'unknown file')}. Found {len(resultats)} rules.")

    except Exception as e:
        # Log error to console, as we are in a thread
        print(f"An unexpected error occurred in analyser_pdf_cis: {e}")
        # Potentially log traceback
        import traceback
        traceback.print_exc()
        return []

    return resultats
