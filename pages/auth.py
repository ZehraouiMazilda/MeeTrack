import streamlit as st
from database import create_user, login_user

def show():
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("""
        <div style="text-align:center; padding: 2.5rem 0 2rem;">
            <div style="font-family:'Syne',sans-serif; font-size:0.75rem; font-weight:700;
                        letter-spacing:0.2em; text-transform:uppercase; color:#4f6ef7; margin-bottom:0.8rem;">
                Master SISE · 2025–2026
            </div>
            <div style="font-family:'Syne',sans-serif; font-size:3rem; font-weight:800; line-height:1.1;">
                Meet<span style="background:linear-gradient(135deg,#4f6ef7,#7c3aed);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">Track</span>
            </div>
            <div style="color:#64748b; font-size:0.9rem; margin-top:0.6rem;">
                Analyse intelligente de réunions en temps réel
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔑 Connexion", "✨ Créer un compte"])

        with tab_login:
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            username = st.text_input("Nom d'utilisateur", key="login_user", placeholder="ex: alice")
            password = st.text_input("Mot de passe", type="password", key="login_pass", placeholder="••••••••")
            st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

            if st.button("Se connecter", key="btn_login"):
                if not username or not password:
                    st.error("Remplis tous les champs.")
                else:
                    ok, user = login_user(username, password)
                    if ok:
                        st.session_state.user = user
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error("Identifiants incorrects.")

        with tab_register:
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            new_user = st.text_input("Nom d'utilisateur", key="reg_user", placeholder="ex: bob")
            new_pass = st.text_input("Mot de passe", type="password", key="reg_pass", placeholder="••••••••")
            new_pass2 = st.text_input("Confirmer le mot de passe", type="password", key="reg_pass2", placeholder="••••••••")
            st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

            if st.button("Créer mon compte", key="btn_register"):
                if not new_user or not new_pass:
                    st.error("Remplis tous les champs.")
                elif new_pass != new_pass2:
                    st.error("Les mots de passe ne correspondent pas.")
                elif len(new_pass) < 4:
                    st.error("Mot de passe trop court (min 4 caractères).")
                else:
                    ok, msg = create_user(new_user, new_pass)
                    if ok:
                        st.success(msg + " Tu peux maintenant te connecter.")
                    else:
                        st.error(msg)