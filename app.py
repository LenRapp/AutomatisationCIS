import streamlit as st

# On va chercher les fonctions dans le dossier 'src', fichier 'extraction'
from src.extraction import recuperer_tout_le_texte, analyser_pdf_cis

# 1. Configuration
st.set_page_config(page_title="Extracteur PDF", page_icon="📄")

# APPLICATION PRINCIPALE
def main():
    st.title("📄 Extracteur PDF & IA")
    st.write("Glisse ton fichier ci-dessous.")

    uploaded_file = st.file_uploader("Choisir un fichier PDF", type="pdf")

    if uploaded_file is not None:
        st.success(f"✅ Fichier chargé : **{uploaded_file.name}**")

        # On "unpack" la liste retournée par st.tabs
        tab1, tab2 = st.tabs(["📝 Texte Brut", "🔍 Analyse IA"])

        # ONGLET 1 : Texte Brut
        with tab1:
            st.write("Récupère l'intégralité du texte du document.")

            if st.button("Extraire tout le texte"):
                with st.spinner('Extraction brute en cours...'):
                    # On remet le pointeur du fichier au début
                    uploaded_file.seek(0)
                    grand_texte = recuperer_tout_le_texte(uploaded_file)

                # Affichage
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

if __name__ == "__main__":
    main()