import streamlit as st

def fazer_login(usuario, perfil):
st.session_state["autenticado"] = True
st.session_state["usuario_logado"] = usuario
st.session_state["perfil"] = perfil

def verificar_autenticacao():
return st.session_state.get("autenticado", False)

def fazer_logout():
for key in list(st.session_state.keys()):
del st.session_state[key]
