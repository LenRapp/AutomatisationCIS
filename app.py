import streamlit as st
from src.extraction import analyser_pdf_cis
# On importe la logique du collègue (Développeur 1)
try:
    from src.comparator import compare_data
except ImportError:
    # Fallback pour éviter que l'interface ne plante totalement si le fichier n'existe pas encore
    compare_data = None

import json
import concurrent.futures

st.set_page_config(page_title="Comparateur CIS", page_icon="⚡", layout="wide")

if 'comparison_data' not in st.session_state:
    st.session_state.comparison_data = None

def process_file(file):
    """Prépare le fichier pour l'extraction."""
    file.seek(0)
    return analyser_pdf_cis(file)

def main():
    st.title("⚡ Comparateur CIS - Interface UI")
    
    def clear_state():
        st.session_state.comparison_data = None


    uploaded_files = st.file_uploader(
        "Déposez vos deux fichiers PDF CIS", 
        type="pdf", 
        accept_multiple_files=True, 
        on_change=clear_state
    )

    if len(uploaded_files) == 2:
        file1, file2 = uploaded_files
        st.info(f"Mode Comparaison : {file1.name} (Réf) vs {file2.name} (Cible)")
        
        # 2. ACTION (Lancement des extractions en parallèle)
        if st.button("🚀 LANCER LA COMPARAISON", type="primary"):
            if compare_data is None:
                st.error("Le module de comparaison (src/comparator.py) est manquant. Attendez la partie du collègue !")
                return

            with st.spinner("Extractions parallèles et calcul des différences..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # On lance les deux extractions en même temps
                    f1 = executor.submit(process_file, file1)
                    f2 = executor(process_file, file2)
                    
                    data1 = f1.result()
                    data2 = f2.result()
                
                if data1 and data2:
                    # 3. APPEL AU BACKEND (Logic du collègue)
                    st.session_state.comparison_data = compare_data(data1, data2)
                    st.success("Analyse terminée !")
                else:
                    st.error("L'extraction a échoué sur l'un des fichiers.")

    elif len(uploaded_files) == 1:
        file1 = uploaded_files[0]
        st.info(f"Mode Extraction Simple : {file1.name}")
        
        if st.button("🚀 LANCER L'EXTRACTION", type="primary"):
            with st.spinner("Analyse du document en cours..."):
                data = process_file(file1)
                if data:
                    st.session_state.comparison_data = {"single_mode": True, "data": data}
                    st.success("Extraction terminée !")
                else:
                    st.error("Aucune règle n'a pu être extraite.")

    # 4. AFFICHAGE VISUEL
    if st.session_state.comparison_data:
        res = st.session_state.comparison_data
        
        # CAS 1 : MODE EXTRACTION SIMPLE
        if res.get("single_mode"):
            data = res["data"]
            st.divider()
            
            # Barre de statistiques et Export
            c1, c2 = st.columns([1, 3])
            c1.metric("Règles Trouvées", len(data))
            
            json_str = json.dumps(data, indent=4, ensure_ascii=False)
            c2.download_button("📥 Télécharger le JSON", json_str, "cis_export.json", "application/json")
            
            st.divider()
            
            # Affichage "Accordéon" détaillé (Rendu Original)
            for i, r in enumerate(data):
                is_complete = r.get('severity') != "Unknown" and len(r.get('description', '')) > 5
                icon = "✅" if is_complete else "⚠️"
                
                title_display = f"{icon} [{r.get('control_id')}] {r.get('title')}"
                
                with st.expander(title_display):
                    # Formulaire de visualisation
                    c1, c2 = st.columns([1, 4])
                    c1.text_input("ID", r.get('control_id'), key=f"id_{i}", disabled=True)
                    c2.text_input("Sévérité", r.get('severity'), key=f"sev_{i}", disabled=True)
                    
                    st.text_area("Description", r.get('description', ''), height=100, key=f"desc_{i}")
                    
                    # Onglets pour les détails techniques
                    t1, t2, t3 = st.tabs(["Justification", "Impact", "Remédiation"])
                    t1.info(r.get('rationale', 'Non renseigné'))
                    t2.warning(r.get('impact', 'Non renseigné'))
                    t3.code(r.get('remediation', ''))
                    
                    st.caption(f"Page source : {r.get('page')}")
                    
        # CAS 2 : MODE COMPARAISON
        else:
            stats = res.get('stats', {})

if __name__ == "__main__":
    main()