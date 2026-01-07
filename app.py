import streamlit as st
from src.extraction import recuperer_tout_le_texte, analyser_pdf_cis
from src.generator import convertir_en_json  # <--- Nouvel import

# 1. Configuration
st.set_page_config(page_title="Extracteur PDF", page_icon="📄")

# Initialisation de l'état pour stocker les données JSON entre les rechargements
if 'json_data' not in st.session_state:
    st.session_state.json_data = None


def main():
    st.title("📄 Extracteur PDF & IA")
    st.write("Glisse ton fichier ci-dessous.")

    # Ajout d'un callback pour nettoyer les résultats si on change de fichier
    def clear_json_state():
        st.session_state.json_data = None

    uploaded_file = st.file_uploader(
        "Choisir un fichier PDF",
        type="pdf",
        on_change=clear_json_state
    )

    if uploaded_file is not None:
        st.success(f"✅ Fichier chargé : **{uploaded_file.name}**")

        # On ajoute le 3ème onglet "Export JSON"
        tab1, tab2, tab3 = st.tabs(["📝 Texte Brut", "🔍 Analyse IA", "💾 Export JSON"])

        # ONGLET 1 : Texte Brut
        with tab1:
            st.write("Récupère l'intégralité du texte du document.")

            if st.button("Extraire tout le texte"):
                with st.spinner('Extraction brute en cours...'):
                    uploaded_file.seek(0)
                    grand_texte = recuperer_tout_le_texte(uploaded_file)

                st.subheader("Aperçu")
                st.text_area("Contenu (2000 premiers caractères)", grand_texte[:2000] + "...", height=300)

                st.download_button(
                    label="💾 Télécharger le texte complet (.txt)",
                    data=grand_texte,
                    file_name="texte_complet.txt",
                    mime="text/plain"
                )

        # ONGLET 2 : Analyse
        with tab2:
            if st.button("Lancer l'analyse structurée"):
                uploaded_file.seek(0)
                regles = analyser_pdf_cis(uploaded_file)
                st.write(f"{len(regles)} règles trouvées.")

        # ONGLET 3 : Export JSON
        with tab3:
            st.header("Export des données")
            st.write("Générez un fichier JSON structuré contenant toutes les règles extraites.")

            if st.button("Générer l'aperçu JSON"):
                with st.spinner('Analyse et conversion en cours...'):
                    uploaded_file.seek(0)
                    regles = analyser_pdf_cis(uploaded_file)
                    st.session_state.json_data = regles  # Stockage dans la session

            # Si des données sont présentes en session
            if st.session_state.json_data:
                st.subheader("Aperçu des données")
                st.json(st.session_state.json_data)

                # Utilisation de la fonction du module src/generator.py
                json_str = convertir_en_json(st.session_state.json_data)

                st.download_button(
                    label="📥 Télécharger le fichier JSON",
                    data=json_str,
                    file_name="resultats_analyse.json",
                    mime="application/json"
                )


if __name__ == "__main__":
    main()