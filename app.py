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
        st.info(f"Fichiers détectés : {file1.name} (Réf) et {file2.name} (Cible)")
        
        # Lancement des extractions en parallèle
        if st.button("🚀 LANCER L'ANALYSE", type="primary"):
            if compare_data is None:
                st.error("Le module de comparaison (src/comparator.py) est manquant. Attendez la partie du collègue !")
                return

            with st.spinner("Extractions parallèles et calcul des différences..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # On lance les deux extractions en même temps
                    f1 = executor.submit(process_file, file1)
                    f2 = executor.submit(process_file, file2)
                    
                    data1 = f1.result()
                    data2 = f2.result()
                
                if data1 and data2:
                    # 3. APPEL AU BACKEND (Logic du collègue)
                    st.session_state.comparison_data = compare_data(data1, data2)
                    st.success("Analyse terminée !")
                else:
                    st.error("L'extraction a échoué sur l'un des fichiers.")
    
    elif len(uploaded_files) == 1:
        st.warning("Veuillez ajouter un deuxième fichier pour pouvoir lancer la comparaison.")

    if st.session_state.comparison_data:
        res = st.session_state.comparison_data
        stats = res.get('stats', {})
        
        st.divider()
        
        # Métriques de comparaison
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ancien Total", stats.get('count1', 0))
        c2.metric("Nouveau Total", stats.get('count2', 0), delta=stats.get('count2', 0) - stats.get('count1', 0))
        c3.metric("Ajouts", stats.get('added_count', 0), delta_color="normal")
        c4.metric("Suppressions", stats.get('removed_count', 0), delta_color="inverse")

        st.divider()

        # Visualisation par onglets
        tab_add, tab_rem, tab_mod = st.tabs([
            f"✅ Ajouts ({stats.get('added_count', 0)})", 
            f"❌ Suppressions ({stats.get('removed_count', 0)})", 
            f"⚠️ Modifications ({stats.get('modified_count', 0)})"
        ])
        
        with tab_add:
            for r in res.get('added', []):
                with st.expander(f"➕ [{r.get('control_id')}] {r.get('title')}"):
                    st.json(r)

        with tab_rem:
            for r in res.get('removed', []):
                with st.expander(f"➖ [{r.get('control_id')}] {r.get('title')}"):
                    st.json(r)

        with tab_mod:
            for item in res.get('modified', []):
                old, new = item.get('old', {}), item.get('new', {})
                with st.expander(f"📝 [{item.get('control_id')}] {new.get('title')}"):
                    col_a, col_b = st.columns(2)
                    col_a.write("**Version Précédente**")
                    col_a.caption(f"Sévérité : {old.get('severity')}")
                    col_b.write("**Nouvelle Version**")
                    col_b.caption(f"Sévérité : {new.get('severity')}")

if __name__ == "__main__":
    main()