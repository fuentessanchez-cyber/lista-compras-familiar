import os
from collections import defaultdict

import requests
import streamlit as st


st.set_page_config(page_title="Lista familiar", page_icon="🛒", layout="centered")

st.markdown(
    """<style>
    .block-container {max-width: 680px; padding-top: 1rem; padding-bottom: 3rem;}
    [data-testid="stNumberInput"] input {font-size: 1.05rem;}
    .done {color: #777; text-decoration: line-through;}
    
    /* Alinear en 1 línea SOLAMENTE los productos dentro de las categorías */
    [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
    }
    
    /* Dejar el 55% del espacio para el nombre del producto */
    [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) {
        width: 55% !important;
        flex: 1 1 55% !important;
        min-width: 0 !important;
    }
    
    /* Dar el 45% a la cantidad y forzar un ancho mínimo para que NO se oculten los botones + y - */
    [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
        width: 45% !important;
        flex: 1 1 45% !important;
        min-width: 120px !important; 
    }
    </style>""",
    unsafe_allow_html=True,
)



    
    /* Dar 30% de espacio a la caja de cantidad para que los botones no se salgan */
    [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
        width: 30% !important;
        flex: 1 1 30% !important;
        min-width: 0 !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

def setting(name: str) -> str:
    """Read a value from Streamlit secrets first, then environment variables."""
    try:
        return st.secrets[name]
    except (FileNotFoundError, KeyError):
        return os.getenv(name, "")


API_URL = setting("GAS_API_URL")
API_TOKEN = setting("GAS_API_TOKEN")


def api(action: str, payload: dict | None = None) -> dict:
    """Call the Google Apps Script web app."""
    if not API_URL:
        raise RuntimeError("Falta configurar GAS_API_URL en los secretos de Streamlit.")
    payload = {"action": action, "token": API_TOKEN, **(payload or {})}
    try:
        if action == "get_products":
            response = requests.get(API_URL, params=payload, timeout=20)
        else:
            response = requests.post(API_URL, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"No se pudo conectar con Google Sheets: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("La respuesta de Google Apps Script no es JSON válido.") from exc
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Error desconocido en Google Sheets."))
    return data


@st.cache_data(ttl=15, show_spinner=False)
def load_products() -> list[dict]:
    return api("get_products")["products"]


def refresh() -> None:
    load_products.clear()
    st.rerun()


def set_quantity(product_id: str) -> None:
    api("update_product", {"id": product_id, "quantity": int(st.session_state[f"qty_{product_id}"])})
    load_products.clear()


def set_cart(product_id: str) -> None:
    api("update_product", {"id": product_id, "in_cart": bool(st.session_state[f"cart_{product_id}"])})
    load_products.clear()


st.title("🛒 Lista familiar")
st.caption("Cambios compartidos en tiempo real")

try:
    products = load_products()
except RuntimeError as exc:
    st.error(str(exc))
    st.info("Configura los secretos y vuelve a cargar la página. Las instrucciones están en el README.")
    st.stop()

pantry_tab, shopping_tab = st.tabs(["🏠 Modo Despensa", "🛍️ Modo Compras"])

with pantry_tab:
    grouped = defaultdict(list)
    for product in products:
        grouped[product["category"]].append(product)

    for category, items in grouped.items():
        with st.expander(category, expanded=False):
            for item in items:
                key = f"qty_{item['id']}"
                # Keep a changed value in the browser, otherwise hydrate from Sheets.
                if key not in st.session_state:
                    st.session_state[key] = item["quantity"]

                    # Alineación vertical nativa de Streamlit
                    left, right = st.columns([3, 1], vertical_alignment="center")
                    # Quitamos el espacio por defecto que deja Streamlit abajo del texto
                    left.markdown(f"<p style='margin-bottom: 0px;'>{item['name']}</p>", unsafe_allow_html=True)
                    right.number_input("Cantidad", min_value=0, step=1, key=key, label_visibility="collapsed", on_change=set_quantity, args=(item["id"],), )
               
                st.divider()
                
    st.subheader("Agregar producto")
    with st.form("new_product", clear_on_submit=True):
        name = st.text_input("Nombre del producto", placeholder="Ej.: Ibuprofeno")
        option = st.selectbox("Categoría", list(grouped.keys()) + ["➕ Crear una categoría nueva"])
        new_category = st.text_input("Nueva categoría") if option.startswith("➕") else ""
        submitted = st.form_submit_button("Agregar a la despensa", use_container_width=True)
    if submitted:
        category = new_category.strip().upper() if option.startswith("➕") else option
        if not name.strip() or not category:
            st.warning("Indica el nombre y una categoría.")
        else:
            try:
                api("add_product", {"name": name.strip(), "category": category})
                refresh()
            except RuntimeError as exc:
                st.error(str(exc))

with shopping_tab:
    hide_done = st.toggle("Ocultar productos tachados", value=False)
    active = [item for item in products if item["quantity"] > 0]
    if not active:
        st.info("Aún no hay productos en la lista. Agrégalos desde Modo Despensa.")
    for item in active:
        if hide_done and item["in_cart"]:
            continue
        key = f"cart_{item['id']}"
        if key not in st.session_state:
            st.session_state[key] = item["in_cart"]
        label = f"{item['name']}  ·  {item['quantity']}"
        if item["in_cart"]:
            label = f":gray[~~{label}~~]"
        st.checkbox(label, key=key, on_change=set_cart, args=(item["id"],))

    if active:
        st.caption(f"{sum(not item['in_cart'] for item in active)} pendientes de {len(active)} productos")
