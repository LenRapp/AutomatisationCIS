import streamlit as st
from src.extraction import recuperer_tout_le_texte, analyser_pdf_cis
from src.generator import convertir_en_json

# 1. Configuration de la page
st.set_page_config(page_title="Extracteur PDF CIS", page_icon="🛡️", layout="wide")

# Initialisation de l'état (mémoire)
if 'json_data' not in st.session_state:
    st.session_state.json_data = None


def main():
    st.title("🛡️ CIS Benchmark - Assistant d'Audit")
    st.write("Charge ton fichier PDF ci-dessous pour lancer l'analyse et la validation.")
    st.markdown("---")

    # --- ZONE D'UPLOAD (Au centre) ---
    def clear_json_state():
        st.session_state.json_data = None

    uploaded_file = st.file_uploader(
        "Glisse ton fichier PDF ici",
        type="pdf",
        on_change=clear_json_state
    )

    if uploaded_file is not None:
        st.success(f"✅ Fichier chargé : **{uploaded_file.name}**")

        # Création des onglets
        tab1, tab2, tab3 = st.tabs(["📝 Texte Brut", "🔍 Analyse Rapide", "✅ Validation & Export"])

        # --- ONGLET 1 : Texte Brut ---
        with tab1:
            st.write("Vérification du contenu brut extrait du PDF.")
            if st.button("Extraire tout le texte"):
                with st.spinner('Lecture en cours...'):
                    uploaded_file.seek(0)
                    grand_texte = recuperer_tout_le_texte(uploaded_file)
                st.text_area("Aperçu (début)", grand_texte[:3000] + "...", height=400)

        # --- ONGLET 2 : Analyse Rapide (Debug) ---
        with tab2:
            st.write("Vue technique des objets Python détectés.")
            if st.button("Lancer l'analyse moteur"):
                uploaded_file.seek(0)
                regles = analyser_pdf_cis(uploaded_file)
                st.write(f"Nombre d'objets détectés : **{len(regles)}**")
                st.write(regles[0] if regles else "Rien trouvé.")

        # --- ONGLET 3 : UI DE VALIDATION (Version Corrigée - Anti-Crash) ---
        with tab3:
            st.header("Validation des Données")
            st.info("Vérifie la qualité de l'extraction avant de générer le JSON final.")

            col1, col2 = st.columns([1, 4])
            with col1:
                bouton_analyse = st.button("🚀 LANCER L'ANALYSE", type="primary")

            if bouton_analyse:
                with st.spinner('Extraction et structuration des règles...'):
                    uploaded_file.seek(0)
                    regles = analyser_pdf_cis(uploaded_file)

                    if not regles:
                        st.error("⚠️ Aucune règle trouvée. Vérifie le format du PDF.")
                        st.session_state.json_data = None
                    else:
                        st.session_state.json_data = regles
                        st.rerun()  # Rafraichit la page

            # Affichage des résultats si disponibles
            if st.session_state.json_data:
                data = st.session_state.json_data

                # --- A. INFO DOCUMENT ---
                if len(data) > 0:
                    # On prend les infos de la première règle (communes à tout le doc)
                    db_type = data[0].get('database_type', 'Non détecté')
                    version = data[0].get('cis_benchmark_version', 'Non détectée')

                    st.info(f"📂 **Document Identifié** : {db_type} | **Version Benchmark** : {version}")

                # --- B. BARRE D'OUTILS (KPIs) ---
                col_kpi1, col_kpi2, col_filter = st.columns([1, 1, 2])

                nb_total = len(data)
                # On considère une règle "incomplète" si Severity est Unknown ou Description vide
                nb_erreurs = sum(1 for r in data if r['severity'] == 'Unknown' or len(r['description']) < 10)

                col_kpi1.metric("Règles Totales", nb_total)
                col_kpi2.metric("À Vérifier", nb_erreurs, delta_color="inverse")

                with col_filter:
                    afficher_erreurs_seules = st.checkbox("⚠️ Afficher uniquement les règles incomplètes",
                                                          value=True if nb_erreurs > 0 else False)

                st.markdown("---")

                # --- C. LISTE DES RÈGLES ---
                count_visible = 0

                # CORRECTION : On utilise 'enumerate' pour avoir un index 'i' unique
                for i, regle in enumerate(data):

                    est_incomplet = (regle['severity'] == 'Unknown') or (len(regle['description']) < 10)

                    if afficher_erreurs_seules and not est_incomplet:
                        continue

                    count_visible += 1

                    if est_incomplet:
                        icone = "⚠️"
                        titre_expander = f"{icone} [{regle['control_id']}] {regle['title']} (Incomplet)"
                    else:
                        icone = "✅"
                        titre_expander = f"{icone} [{regle['control_id']}] {regle['title']}"

                    # Création de la boîte (Expander)
                    with st.expander(titre_expander, expanded=est_incomplet):
                        # Ligne 1 : ID et Sévérité
                        c1, c2 = st.columns([1, 3])

                        # CORRECTION : On ajoute _{i} dans les keys pour éviter les doublons
                        c1.text_input("ID", regle['control_id'], key=f"id_{regle['control_id']}_{i}", disabled=True)

                        if regle['severity'] == 'Unknown':
                            c2.warning("⚠️ Sévérité non détectée !")
                        else:
                            c2.text_input("Sévérité", regle['severity'], key=f"sev_{regle['control_id']}_{i}",
                                          disabled=True)

                        # Ligne 2 : Description principale
                        st.text_area("Description", regle['description'], height=80,
                                     key=f"desc_{regle['control_id']}_{i}")

                        # Ligne 3 : Détails techniques (Rationale & Impact) dans des onglets
                        t_rat, t_imp = st.tabs(["💡 Rationale (Justification)", "💥 Impact"])
                        with t_rat:
                            st.write(regle.get('rationale', 'Pas de justification détectée.'))
                        with t_imp:
                            st.write(regle.get('impact', 'Pas d\'impact spécifié.'))

                        st.caption(f"📄 Page source : {regle['page']}")

                if count_visible == 0:
                    st.success("🎉 Aucune erreur à afficher ! Le document semble propre.")

                st.markdown("---")

                # --- D. EXPORT FINAL ---
                st.subheader("💾 Export Final")
                json_str = convertir_en_json(data)
                st.download_button(
                    label="📥 Télécharger le JSON validé",
                    data=json_str,
                    file_name="cis_benchmark_export.json",
                    mime="application/json",
                    type="primary"
                )


if __name__ == "__main__":
    main()