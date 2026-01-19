import streamlit as st
from src.extraction import analyser_pdf_cis
from src.comparator import compare_rules
import json
import concurrent.futures

st.set_page_config(page_title="Comparateur CIS", page_icon="⚡", layout="wide")

# Initialize session state
if 'comparison_data' not in st.session_state:
    st.session_state.comparison_data = None
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 'added' # Default active tab

def process_file(file):
    """Wrapper function for PDF processing."""
    file.seek(0) # Reset file pointer
    return analyser_pdf_cis(file)

def main():
    st.title("⚡ Comparateur de Benchmarks CIS")

    def clear_state():
        """Resets the session state."""
        st.session_state.comparison_data = None
        st.session_state.active_tab = 'added'

    # --- UI for File Upload ---
    uploaded_files = st.file_uploader(
        "Déposez vos deux fichiers PDF CIS (un fichier de référence et un fichier cible)",
        type="pdf",
        accept_multiple_files=True,
        on_change=clear_state
    )

    # --- LOGIC for Processing Files ---
    if len(uploaded_files) == 2:
        file1, file2 = uploaded_files
        st.info(f"Fichier de référence (Ancien): **{file1.name}** | Fichier cible (Nouveau): **{file2.name}**")

        if st.button("🚀 Lancer la Comparaison", type="primary", use_container_width=True):
            progress_placeholder = st.empty()
            with st.spinner("Analyse des documents en cours..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    progress_placeholder.info(f"Étape 1/4 : Lancement de l'extraction pour {file1.name} et {file2.name}...")
                    future1 = executor.submit(process_file, file1)
                    future2 = executor.submit(process_file, file2)

                    progress_placeholder.info(f"Étape 2/4 : En attente de la fin de l'extraction pour {file1.name}...")
                    data1 = future1.result()
                    progress_placeholder.info(f"-> Terminé pour {file1.name}. {len(data1) if data1 else 0} règles trouvées.")

                    progress_placeholder.info(f"Étape 3/4 : En attente de la fin de l'extraction pour {file2.name}...")
                    data2 = future2.result()
                    progress_placeholder.info(f"-> Terminé pour {file2.name}. {len(data2) if data2 else 0} règles trouvées.")

                if data1 and data2:
                    progress_placeholder.info("Étape 4/4 : Comparaison des ensembles de règles...")
                    comparison_result = compare_rules(data1, data2)
                    
                    # Add stats to the result for easier access in the UI
                    comparison_result['stats'] = {
                        'added': len(comparison_result['added']),
                        'deleted': len(comparison_result['deleted']),
                        'modified': len(comparison_result['modified'])
                    }
                    st.session_state.comparison_data = comparison_result
                    progress_placeholder.empty() # Clear progress messages
                    st.success("Analyse comparative terminée !")
                else:
                    st.error("L'extraction des données a échoué pour au moins un des fichiers. Assurez-vous qu'ils sont valides.")

    elif len(uploaded_files) == 1:
        st.warning("Mode simple fichier : Affiche les règles extraites. Pour comparer, déposez un second fichier.")
        # Simplified display for single file extraction
        if st.button("🔍 Extraire les règles du document", use_container_width=True):
             with st.spinner("Analyse du document en cours..."):
                data = process_file(uploaded_files[0])
                if data:
                    st.session_state.comparison_data = {"single_mode": True, "data": data}
                    st.success(f"Extraction terminée : {len(data)} règles trouvées.")
                else:
                    st.error("Aucune règle n'a pu être extraite.")


    # --- UI for Displaying Results ---
    if st.session_state.comparison_data:
        res = st.session_state.comparison_data
        st.divider()

        if res.get("single_mode"):
            # Display for single file extraction
            st.header("Règles Extraites")
            st.metric("Nombre total de règles", len(res['data']))
            json_export = json.dumps(res['data'], indent=2)
            st.download_button("📥 Télécharger le JSON", json_export, "extraction.json", "application/json")
            for rule in res['data']:
                with st.expander(f"**{rule.get('control_id', 'N/A')}**: {rule.get('title', 'Sans titre')}"):
                    st.json(rule)
        else:
            # Display for comparison result
            st.header("Résultats de la Comparaison")
            stats = res.get('stats', {})
            
            # --- Metrics ---
            col1, col2, col3 = st.columns(3)
            col1.metric("🟢 Règles Ajoutées", stats.get('added', 0))
            col2.metric("🔴 Règles Supprimées", stats.get('deleted', 0))
            col3.metric("🟠 Règles Modifiées", stats.get('modified', 0))

            # --- Detailed Tabs ---
            tab_added, tab_deleted, tab_modified = st.tabs(["Ajouts", "Suppressions", "Modifications"])

            with tab_added:
                st.subheader(f"{stats.get('added', 0)} nouvelles règles")
                for rule in res.get('added', []):
                    with st.expander(f"**{rule.get('control_id', 'N/A')}**: {rule.get('title', 'Sans titre')}"):
                        st.json(rule)

            with tab_deleted:
                st.subheader(f"{stats.get('deleted', 0)} règles obsolètes")
                for rule in res.get('deleted', []):
                    with st.expander(f"**{rule.get('control_id', 'N/A')}**: {rule.get('title', 'Sans titre')}"):
                        st.json(rule)

            with tab_modified:
                st.subheader(f"{stats.get('modified', 0)} règles mises à jour")
                for mod in res.get('modified', []):
                    title = mod.get('control_id', 'N/A')
                    with st.expander(f"**ID de Contrôle : {title}**"):
                        st.write("Champs modifiés :")
                        for field, changes in mod.get('changes', {}).items():
                            st.markdown(f"- **{field.replace('_', ' ').capitalize()}**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.text_area("Valeur Précédente", value=str(changes.get('old', '')), height=100, disabled=True, key=f"old_{title}_{field}")
                            with col2:
                                st.text_area("Nouvelle Valeur", value=str(changes.get('new', '')), height=100, disabled=True, key=f"new_{title}_{field}")

if __name__ == "__main__":
    main()
