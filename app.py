import streamlit as st
from src.extraction import analyser_pdf_cis
import json

st.set_page_config(page_title="Extracteur CIS", page_icon="⚡", layout="wide")

if 'json_data' not in st.session_state:
    st.session_state.json_data = None

def main():
    st.title("⚡ Automatisation CIS - Upload Fichier")
    def clear_state():
        st.session_state.json_data = None

    uploaded_file = st.file_uploader("Charge ton fichier PDF", type="pdf", on_change=clear_state)

    if uploaded_file:
        st.success(f"Document : {uploaded_file.name}")
        
        # Bouton d'action principal
        if st.button("🚀 LANCER L'EXTRACTION", type="primary"):
            with st.spinner("Analyse du document en cours..."):
                uploaded_file.seek(0)
                data = analyser_pdf_cis(uploaded_file)
                
                if data:
                    st.session_state.json_data = data
                    st.rerun()
                else:
                    st.error("Aucune règle n'a pu être extraite. Vérifiez le PDF ou la configuration.")

        # Affichage des résultats
        if st.session_state.json_data:
            data = st.session_state.json_data
            
            # Barre de statistiques
            col1, col2, col3 = st.columns(3)
            col1.metric("Règles Trouvées", len(data))
            
            # Export JSON
            json_str = json.dumps(data, indent=4, ensure_ascii=False)
            col2.download_button(
                "📥 Télécharger le JSON", 
                json_str, 
                "cis_export.json", 
                "application/json"
            )
            
            st.markdown("---")
            
            # Affichage "Accordéon"
            for i, r in enumerate(data):
                is_complete = r.get('severity') != "Unknown" and len(r.get('description', '')) > 5
                icon = "✅" if is_complete else "⚠️"
                
                title_display = f"{icon} [{r.get('control_id')}] {r.get('title')}"
                
                with st.expander(title_display):
                    # Formulaire de visualisation
                    c1, c2 = st.columns([1, 4])
                    c1.text_input("ID", r.get('control_id'), key=f"id_{i}", disabled=True)
                    c2.text_input("Sévérité", r.get('severity'), key=f"sev_{i}", disabled=True)
                    
                    st.text_area("Description", r.get('description'), height=100, key=f"desc_{i}")
                    
                    # Onglets pour les détails techniques
                    t1, t2, t3 = st.tabs(["Justification", "Impact", "Remédiation"])
                    t1.info(r.get('rationale'))
                    t2.warning(r.get('impact'))
                    t3.code(r.get('remediation'))
                    
                    st.caption(f"Page source : {r.get('page')}")

if __name__ == "__main__":
    main()
