import io
import mysql.connector
import pandas as pd
import plotly.express as px
import qrcode
import streamlit as st
from PIL import Image

st.set_page_config(
    page_title="WMS Bodega Inteligente Multi-Bodega", layout="wide", page_icon="📦"
)

# ---------------------------------------------------------
# ESTILOS CSS PERSONALIZADOS (PALETA EMPRESARIAL)
# ---------------------------------------------------------
CSS_EMPRESARIAL = """
<style>
    /* Fondo principal de la app */
    .stApp {
        background-color: #F5F7FA;
    }
    
    /* Encabezados y Títulos */
    h1, h2, h3, h4 {
        color: #1F3864 !important;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Botones primarios */
    div.stButton > button[kind="primary"] {
        background-color: #1F3864 !important;
        color: #FFFFFF !important;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #152746 !important;
        box-shadow: 0 4px 10px rgba(31, 56, 100, 0.3);
    }

    /* Estilo de la Barra Lateral */
    section[data-testid="stSidebar"] {
        background-color: #1F3864 !important;
    }
    section[data-testid="stSidebar"] * {
        color: #F5F7FA !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        color: #F5F7FA !important;
    }

    /* Tarjetas de Métricas (KPIs) */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        border-left: 5px solid #1F3864;
    }
    div[data-testid="stMetricLabel"] {
        color: #5A6A85 !important;
        font-size: 0.9rem !important;
        font-weight: 600;
    }
    div[data-testid="stMetricValue"] {
        color: #1F3864 !important;
        font-weight: 700;
    }

    /* Tablas de Datos */
    .stDataFrame {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 5px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
</style>
"""
st.markdown(CSS_EMPRESARIAL, unsafe_allow_html=True)

# ---------------------------------------------------------
# CREDENCIALES, ROLES Y BODEGAS ASIGNADAS
# ---------------------------------------------------------
USUARIOS_PERMITIDOS = {
    "admin": {"password": "admin2026", "rol": "admin", "bodega_asignada": "TODAS"},
    "cristobal": {"password": "wms2026", "rol": "admin", "bodega_asignada": "TODAS"},
    "operador1": {"password": "bodega123", "rol": "operario", "bodega_asignada": "BOD-01"},
    "operador2": {"password": "bodega456", "rol": "operario", "bodega_asignada": "BOD-02"},
    "operador3": {"password": "bodega789", "rol": "operario", "bodega_asignada": "BOD-03"},
}

# ---------------------------------------------------------
# CONTROL DE SESIÓN Y AUTENTICACIÓN
# ---------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_actual" not in st.session_state:
    st.session_state.usuario_actual = ""
if "rol_actual" not in st.session_state:
    st.session_state.rol_actual = ""
if "bodega_usuario" not in st.session_state:
    st.session_state.bodega_usuario = ""
if "bodega_activa" not in st.session_state:
    st.session_state.bodega_activa = "BOD-01"

if "mensaje_exito_ingreso" not in st.session_state:
    st.session_state.mensaje_exito_ingreso = None
if "mensaje_exito_reubicacion" not in st.session_state:
    st.session_state.mensaje_exito_reubicacion = None
if "mensaje_exito_picking" not in st.session_state:
    st.session_state.mensaje_exito_picking = None

if "hoja_ruta_persistente" not in st.session_state:
    st.session_state.hoja_ruta_persistente = None
if "distancia_total_persistente" not in st.session_state:
    st.session_state.distancia_total_persistente = None
if "operaciones_pendientes_picking" not in st.session_state:
    st.session_state.operaciones_pendientes_picking = []


def login():
    st.sidebar.subheader("🔐 Inicio de Sesión de Personal")
    usuario_input = st.sidebar.text_input("Usuario")
    password_input = st.sidebar.text_input("Contraseña", type="password")

    if st.sidebar.button("Ingresar al Sistema", type="primary"):
        if (
            usuario_input in USUARIOS_PERMITIDOS
            and USUARIOS_PERMITIDOS[usuario_input]["password"] == password_input
        ):
            st.session_state.autenticado = True
            st.session_state.usuario_actual = usuario_input
            st.session_state.rol_actual = USUARIOS_PERMITIDOS[usuario_input]["rol"]
            st.session_state.bodega_usuario = USUARIOS_PERMITIDOS[usuario_input]["bodega_asignada"]

            if st.session_state.bodega_usuario != "TODAS":
                st.session_state.bodega_activa = st.session_state.bodega_usuario
            else:
                st.session_state.bodega_activa = "BOD-01"

            st.sidebar.success(f"¡Bienvenido, {usuario_input}!")
            st.rerun()
        else:
            st.sidebar.error("❌ Usuario o contraseña incorrectos.")


def logout():
    st.session_state.autenticado = False
    st.session_state.usuario_actual = ""
    st.session_state.rol_actual = ""
    st.session_state.bodega_usuario = ""
    st.session_state.hoja_ruta_persistente = None
    st.session_state.distancia_total_persistente = None
    st.session_state.operaciones_pendientes_picking = []
    st.session_state.mensaje_exito_ingreso = None
    st.session_state.mensaje_exito_reubicacion = None
    st.session_state.mensaje_exito_picking = None
    st.rerun()


if not st.session_state.autenticado:
    login()
    st.title("📦 Sistema de Gestión de Bodega (WMS 2D Multi-Bodega)")
    st.info("👈 Por favor, ingresa tus credenciales en la barra lateral para acceder al sistema.")

else:
    def obtener_conexion():
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            port=int(st.secrets["mysql"]["port"]),
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
        )

    def obtener_df(query, params=None):
        conn = obtener_conexion()
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df

    def ejecutar_query(query, params=None):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        cursor.close()
        conn.close()

    # ---------------------------------------------------------
    # CALLBACK PARA CAMBIO INSTANTÁNEO DE BODEGA
    # ---------------------------------------------------------
    def cambiar_bodega_callback():
        st.session_state.bodega_activa = st.session_state.selector_bodega_temp

    # BARRA LATERAL
    rol_label = "👑 Administrador" if st.session_state.rol_actual == "admin" else "👷 Operario"
    st.sidebar.markdown(f"👤 **Usuario:** `{st.session_state.usuario_actual}`")
    st.sidebar.markdown(f"🏷️ **Rol:** `{rol_label}`")

    df_bodegas = obtener_df("SELECT id_bodega, nombre FROM bodegas")
    dict_bodegas = dict(zip(df_bodegas["id_bodega"], df_bodegas["nombre"])) if not df_bodegas.empty else {}

    if st.session_state.rol_actual == "admin":
        st.sidebar.subheader("🏢 Seleccionar Bodega Activa")
        opciones_bodega = list(dict_bodegas.keys())
        idx_def = opciones_bodega.index(st.session_state.bodega_activa) if st.session_state.bodega_activa in opciones_bodega else 0
        
        st.sidebar.selectbox(
            "Filtrar Vista por Bodega:",
            opciones_bodega,
            format_func=lambda x: f"{x} - {dict_bodegas.get(x, '')}",
            index=idx_def,
            key="selector_bodega_temp",
            on_change=cambiar_bodega_callback
        )
    else:
        st.sidebar.markdown(f"🏢 **Bodega Asignada:** `{st.session_state.bodega_usuario}` - {dict_bodegas.get(st.session_state.bodega_usuario, '')}")
        st.session_state.bodega_activa = st.session_state.bodega_usuario

    if st.sidebar.button("🚪 Cerrar Sesión"):
        logout()

    st.sidebar.markdown("---")

    def cancelar_picking_callback():
        st.session_state.hoja_ruta_persistente = None
        st.session_state.distancia_total_persistente = None
        st.session_state.operaciones_pendientes_picking = []

    def confirmar_picking_callback():
        if st.session_state.operaciones_pendientes_picking:
            try:
                conn = obtener_conexion()
                cursor = conn.cursor()

                for op in st.session_state.operaciones_pendientes_picking:
                    if op["tipo"] == "DELETE":
                        cursor.execute("DELETE FROM inventario WHERE id_inventario = %s", (op["id_inventario"],))
                        cursor.execute("UPDATE ubicaciones SET estado = 'Libre' WHERE id_ubicacion = %s AND id_bodega = %s", (op["id_ubicacion"], st.session_state.bodega_activa))
                    elif op["tipo"] == "UPDATE":
                        cursor.execute("UPDATE inventario SET cantidad = %s WHERE id_inventario = %s", (op["nueva_cantidad"], op["id_inventario"]))

                    cursor.execute(
                        "INSERT INTO historial_movimientos (tipo_movimiento, sku, id_ubicacion, cantidad, id_bodega) VALUES ('DESPACHO', %s, %s, %s, %s)",
                        (op["sku"], op["id_ubicacion"], op["cantidad"], st.session_state.bodega_activa)
                    )

                conn.commit()
                cursor.close()
                conn.close()

                st.session_state.hoja_ruta_persistente = None
                st.session_state.distancia_total_persistente = None
                st.session_state.operaciones_pendientes_picking = []
                st.session_state.mensaje_exito_picking = "🎉 ¡Picking confirmado con éxito! El inventario ha sido actualizado."
            except Exception as e:
                st.session_state.mensaje_exito_picking = f"❌ Error: {e}"

    bodega_nombre_header = dict_bodegas.get(st.session_state.bodega_activa, st.session_state.bodega_activa)
    st.title(f"📦 WMS 2D - [{st.session_state.bodega_activa}: {bodega_nombre_header}]")

    if st.session_state.rol_actual == "admin":
        modulos_disponibles = [
            "🗺️ Mapa 2D & Estado",
            "📥 Recepción e Ingreso",
            "🔄 Reubicación de Casillas",
            "🛒 Picking / Despacho",
            "📊 Dashboard & KPIs",
            "📜 Historial Kárdex",
            "🏷️ Generador de Etiquetas QR",
        ]
    else:
        modulos_disponibles = [
            "🗺️ Mapa 2D & Estado",
            "📥 Recepción e Ingreso",
            "🔄 Reubicación de Casillas",
            "🛒 Picking / Despacho",
            "🏷️ Generador de Etiquetas QR",
        ]

    menu = st.sidebar.radio("Navegación / Módulos", modulos_disponibles)

    # MAPA 2D
    if menu == "🗺️ Mapa 2D & Estado":
        st.header(f"Mapa de Ocupación Física 2D ({st.session_state.bodega_activa})")

        query = """
        SELECT u.id_ubicacion, u.coord_x, u.coord_y, u.estado,
               COALESCE(i.sku, 'Vacío') AS sku,
               COALESCE(i.cantidad, 0) AS cantidad,
               COALESCE(p.nombre, 'Sin Producto') AS producto,
               COALESCE(p.capacidad_por_casilla, 10) AS capacidad
        FROM ubicaciones u
        LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
        LEFT JOIN productos p ON i.sku = p.sku
        WHERE u.id_bodega = %s;
        """
        df_mapa = obtener_df(query, (st.session_state.bodega_activa,))

        if df_mapa.empty:
            st.warning(f"No hay casillas registradas para la bodega {st.session_state.bodega_activa}.")
        else:
            df_mapa["Ocupacion_%"] = (df_mapa["cantidad"] / df_mapa["capacidad"]) * 100

            df_skus_existentes = (
                df_mapa[df_mapa["sku"] != "Vacío"][["sku", "producto"]]
                .drop_duplicates()
                .sort_values(by="sku")
            )

            opciones_buscador = ["🔍 Mostrar Todos los Productos"] + (
                df_skus_existentes["sku"] + " - " + df_skus_existentes["producto"]
            ).tolist()

            col_search1, col_search2 = st.columns([2, 1])

            with col_search1:
                sku_buscado_sel = st.selectbox("📍 Buscador Global de Producto (Ubicador de SKU):", opciones_buscador)

            df_mapa_plot = df_mapa.copy()

            if sku_buscado_sel != "🔍 Mostrar Todos los Productos":
                sku_clean_busqueda = sku_buscado_sel.split(" - ")[0]
                coincidencias = df_mapa_plot[df_mapa_plot["sku"] == sku_clean_busqueda]

                with col_search2:
                    st.metric(
                        label=f"Ubicaciones para {sku_clean_busqueda}",
                        value=f"{len(coincidencias)} Casilla(s)",
                        delta=f"{coincidencias['cantidad'].sum()} Unidades Total",
                    )

                df_mapa_plot["Estado_Grafico"] = df_mapa_plot.apply(
                    lambda r: r["estado"] if r["sku"] == sku_clean_busqueda else "Otro / Sin Coincidencia",
                    axis=1,
                )
                df_mapa_plot["Tamaño_Punto"] = df_mapa_plot.apply(
                    lambda r: 24 if r["sku"] == sku_clean_busqueda else 12, axis=1
                )
                color_map = {
                    "Libre": "#2ecc71",
                    "Ocupado": "#e74c3c",
                    "Inhabilitado": "#95a5a6",
                    "Otro / Sin Coincidencia": "#d6dbdf",
                }
            else:
                df_mapa_plot["Estado_Grafico"] = df_mapa_plot["estado"]
                df_mapa_plot["Tamaño_Punto"] = 18
                color_map = {"Libre": "#2ecc71", "Ocupado": "#e74c3c", "Inhabilitado": "#95a5a6"}

            fig = px.scatter(
                df_mapa_plot,
                x="coord_x",
                y="coord_y",
                color="Estado_Grafico",
                size="Tamaño_Punto",
                size_max=24,
                hover_name="id_ubicacion",
                hover_data=["sku", "producto", "cantidad", "capacidad", "Ocupacion_%"],
                text="id_ubicacion",
                color_discrete_map=color_map,
                title=f"Distribución Espacial de Casillas - {st.session_state.bodega_activa}",
            )

            fig.update_traces(
                marker=dict(line=dict(width=1, color="#1F3864")),
                textposition="top center",
                textfont=dict(size=13, color="#1F3864", family="Segoe UI Black"),
            )

            y_min, y_max = df_mapa_plot["coord_y"].min(), df_mapa_plot["coord_y"].max()
            x_min, x_max = df_mapa_plot["coord_x"].min(), df_mapa_plot["coord_x"].max()

            fig.update_layout(
                xaxis=dict(tickmode="linear", dtick=1, range=[x_min - 0.5, x_max + 0.5]),
                yaxis=dict(tickmode="linear", dtick=1, range=[y_min - 0.3, y_max + 0.6]),
                height=550,
                showlegend=True,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Detalle de Ubicaciones")
            df_tabla_display = df_mapa[df_mapa["sku"] == sku_buscado_sel.split(" - ")[0]] if sku_buscado_sel != "🔍 Mostrar Todos los Productos" else df_mapa
            st.dataframe(df_tabla_display[["id_ubicacion", "estado", "sku", "producto", "cantidad", "capacidad", "Ocupacion_%"]], use_container_width=True)

    # RECEPCIÓN
    elif menu == "📥 Recepción e Ingreso":
        st.header(f"Ingreso de Stock a Bodega ({st.session_state.bodega_activa})")

        if st.session_state.mensaje_exito_ingreso:
            st.success(st.session_state.mensaje_exito_ingreso)
            st.session_state.mensaje_exito_ingreso = None

        df_prods = obtener_df("SELECT sku, nombre, capacidad_por_casilla FROM productos")

        if df_prods.empty:
            st.warning("Asegúrate de tener productos registrados en el sistema.")
        else:
            sku_sel = st.selectbox("Seleccionar Producto (SKU)", df_prods["sku"] + " - " + df_prods["nombre"])
            sku_limpio = sku_sel.split(" - ")[0]
            cap_max = int(df_prods[df_prods["sku"] == sku_limpio]["capacidad_por_casilla"].values[0])

            query_disponibles = """
                SELECT u.id_ubicacion, 
                       COALESCE(i.cantidad, 0) AS cantidad_actual,
                       (%s - COALESCE(i.cantidad, 0)) AS espacio_disponible,
                       CASE 
                           WHEN i.id_inventario IS NULL THEN 'Completamente Libre'
                           ELSE 'Parcialmente Ocupada (Consolidar)'
                       END AS tipo_casilla
                FROM ubicaciones u
                LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
                WHERE u.id_bodega = %s
                  AND u.estado != 'Inhabilitado' 
                  AND (
                      i.id_inventario IS NULL 
                      OR (i.sku = %s AND i.cantidad < %s)
                  );
            """
            df_disponibles = obtener_df(query_disponibles, (cap_max, st.session_state.bodega_activa, sku_limpio, cap_max))

            if df_disponibles.empty:
                st.error(f"❌ No hay casillas disponibles ni espacio suficiente en la bodega {st.session_state.bodega_activa}.")
            else:
                df_disponibles["opcion_texto"] = df_disponibles["id_ubicacion"] + " [" + df_disponibles["tipo_casilla"] + " - Libre: " + df_disponibles["espacio_disponible"].astype(str) + " un.]"

                with st.form("form_ingreso"):
                    ubi_seleccionada_txt = st.selectbox("Seleccionar Casilla Destino", df_disponibles["opcion_texto"])
                    ubi_limpia = ubi_seleccionada_txt.split(" [")[0]
                    espacio_max = int(df_disponibles[df_disponibles["id_ubicacion"] == ubi_limpia]["espacio_disponible"].values[0])

                    st.info(f"Espacio máximo disponible en la casilla {ubi_limpia}: {espacio_max} unidades.")
                    cantidad_ingreso = st.number_input("Cantidad a Ingresar", min_value=1, max_value=espacio_max, value=1)
                    btn_ingresar = st.form_submit_button("Confirmar Ingreso", type="primary")

                    if btn_ingresar:
                        inv_existente = obtener_df("SELECT id_inventario, cantidad FROM inventario WHERE id_ubicacion = %s", (ubi_limpia,))

                        if inv_existente.empty:
                            ejecutar_query("INSERT INTO inventario (id_ubicacion, sku, cantidad) VALUES (%s, %s, %s)", (ubi_limpia, sku_limpio, cantidad_ingreso))
                        else:
                            nueva_cant = int(inv_existente["cantidad"].values[0]) + cantidad_ingreso
                            ejecutar_query("UPDATE inventario SET cantidad = %s WHERE id_ubicacion = %s", (nueva_cant, ubi_limpia))

                        ejecutar_query("UPDATE ubicaciones SET estado = 'Ocupado' WHERE id_ubicacion = %s AND id_bodega = %s", (ubi_limpia, st.session_state.bodega_activa))
                        ejecutar_query("INSERT INTO historial_movimientos (tipo_movimiento, sku, id_ubicacion, cantidad, id_bodega) VALUES ('ENTRADA', %s, %s, %s, %s)", (sku_limpio, ubi_limpia, cantidad_ingreso, st.session_state.bodega_activa))

                        st.session_state.mensaje_exito_ingreso = f"🎉 ¡Ingreso registrado! {cantidad_ingreso} un. de {sku_limpio} en {ubi_limpia} ({st.session_state.bodega_activa})."
                        st.rerun()

    # REUBICACIÓN
    elif menu == "🔄 Reubicación de Casillas":
        st.header(f"Reubicación Interna ({st.session_state.bodega_activa})")

        if st.session_state.mensaje_exito_reubicacion:
            st.success(st.session_state.mensaje_exito_reubicacion)
            st.session_state.mensaje_exito_reubicacion = None

        df_origenes = obtener_df("""
            SELECT i.id_inventario, i.id_ubicacion, i.sku, i.cantidad, p.nombre, p.capacidad_por_casilla
            FROM inventario i
            JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion
            JOIN productos p ON i.sku = p.sku
            WHERE u.id_bodega = %s AND i.cantidad > 0
            ORDER BY i.id_ubicacion ASC
        """, (st.session_state.bodega_activa,))

        if df_origenes.empty:
            st.info(f"No hay casillas con stock para reubicar en {st.session_state.bodega_activa}.")
        else:
            df_origenes["display_origen"] = df_origenes["id_ubicacion"] + " | " + df_origenes["sku"] + " - " + df_origenes["nombre"] + " (Stock: " + df_origenes["cantidad"].astype(str) + ")"

            col_orig, col_dest = st.columns(2)

            with col_orig:
                st.subheader("1. Origen")
                origen_sel_txt = st.selectbox("Casilla a Trasladar", df_origenes["display_origen"])
                ubi_origen = origen_sel_txt.split(" | ")[0]
                row_origen = df_origenes[df_origenes["id_ubicacion"] == ubi_origen].iloc[0]

                id_inv_origen = int(row_origen["id_inventario"])
                sku_origen = row_origen["sku"]
                cant_disponible_origen = int(row_origen["cantidad"])
                cap_max_sku = int(row_origen["capacidad_por_casilla"])

                cant_a_mover = st.number_input(f"Cantidad a Mover (Máx: {cant_disponible_origen})", min_value=1, max_value=cant_disponible_origen, value=cant_disponible_origen)

            with col_dest:
                st.subheader("2. Destino")
                query_destinos = """
                    SELECT u.id_ubicacion, 
                           COALESCE(i.cantidad, 0) AS cantidad_actual,
                           (%s - COALESCE(i.cantidad, 0)) AS espacio_disponible,
                           CASE 
                               WHEN i.id_inventario IS NULL THEN 'Completamente Libre'
                               ELSE 'Mismo SKU (Consolidar)'
                           END AS tipo_casilla
                    FROM ubicaciones u
                    LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
                    WHERE u.id_bodega = %s
                      AND u.estado != 'Inhabilitado' 
                      AND u.id_ubicacion != %s
                      AND (
                          i.id_inventario IS NULL 
                          OR (i.sku = %s AND i.cantidad + %s <= %s)
                      )
                    ORDER BY u.id_ubicacion ASC;
                """
                df_destinos = obtener_df(query_destinos, (cap_max_sku, st.session_state.bodega_activa, ubi_origen, sku_origen, cant_a_mover, cap_max_sku))

                if df_destinos.empty:
                    st.error("❌ No hay casillas destino disponibles.")
                    btn_mover = False
                else:
                    df_destinos["display_destino"] = df_destinos["id_ubicacion"] + " [" + df_destinos["tipo_casilla"] + " - Libre: " + df_destinos["espacio_disponible"].astype(str) + " un.]"
                    destino_sel_txt = st.selectbox("Casilla Destino", df_destinos["display_destino"])
                    ubi_destino = destino_sel_txt.split(" [")[0]

                    st.markdown("<br>", unsafe_allow_html=True)
                    btn_mover = st.button("🚀 Confirmar Reubicación", type="primary", use_container_width=True)

            if btn_mover:
                if cant_a_mover == cant_disponible_origen:
                    ejecutar_query("DELETE FROM inventario WHERE id_inventario = %s", (id_inv_origen,))
                    ejecutar_query("UPDATE ubicaciones SET estado = 'Libre' WHERE id_ubicacion = %s AND id_bodega = %s", (ubi_origen, st.session_state.bodega_activa))
                else:
                    nueva_cant_origen = cant_disponible_origen - cant_a_mover
                    ejecutar_query("UPDATE inventario SET cantidad = %s WHERE id_inventario = %s", (nueva_cant_origen, id_inv_origen))

                inv_destino = obtener_df("SELECT id_inventario, cantidad FROM inventario WHERE id_ubicacion = %s", (ubi_destino,))

                if inv_destino.empty:
                    ejecutar_query("INSERT INTO inventario (id_ubicacion, sku, cantidad) VALUES (%s, %s, %s)", (ubi_destino, sku_origen, cant_a_mover))
                    ejecutar_query("UPDATE ubicaciones SET estado = 'Ocupado' WHERE id_ubicacion = %s AND id_bodega = %s", (ubi_destino, st.session_state.bodega_activa))
                else:
                    nueva_cant_dest = int(inv_destino["cantidad"].values[0]) + cant_a_mover
                    id_inv_dest = int(inv_destino["id_inventario"].values[0])
                    ejecutar_query("UPDATE inventario SET cantidad = %s WHERE id_inventario = %s", (nueva_cant_dest, id_inv_dest))

                st.session_state.mensaje_exito_reubicacion = f"✅ Reubicados {cant_a_mover} un. de {sku_origen} de {ubi_origen} a {ubi_destino}."
                st.rerun()

    # PICKING
    elif menu == "🛒 Picking / Despacho":
        st.header(f"Picking y Despacho ({st.session_state.bodega_activa})")

        if st.session_state.mensaje_exito_picking:
            st.success(st.session_state.mensaje_exito_picking)
            st.session_state.mensaje_exito_picking = None

        df_inv = obtener_df("""
            SELECT i.sku, p.nombre, SUM(i.cantidad) as total_disponible
            FROM inventario i
            JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion
            JOIN productos p ON i.sku = p.sku
            WHERE u.id_bodega = %s
            GROUP BY i.sku, p.nombre
        """, (st.session_state.bodega_activa,))

        if df_inv.empty:
            st.info(f"No hay inventario disponible en {st.session_state.bodega_activa}.")
        else:
            st.subheader("1. Selección de Productos")
            df_inv["opcion_display"] = df_inv["sku"] + " - " + df_inv["nombre"] + " (Stock: " + df_inv["total_disponible"].astype(str) + ")"
            skus_seleccionados = st.multiselect("Productos a Despachar", df_inv["opcion_display"])

            if skus_seleccionados:
                st.markdown("---")
                st.subheader("2. Definir Cantidades")
                cantidades_solicitadas = {}
                cols = st.columns(min(len(skus_seleccionados), 3))

                for idx, item in enumerate(skus_seleccionados):
                    sku_clean = item.split(" - ")[0]
                    nombre_prod = item.split(" - ")[1].split(" (")[0]
                    max_disp = int(df_inv[df_inv["sku"] == sku_clean]["total_disponible"].values[0])

                    with cols[idx % 3]:
                        st.markdown(f"**{sku_clean}** - {nombre_prod}")
                        cant = st.number_input(f"Cantidad (Máx: {max_disp})", min_value=1, max_value=max_disp, value=1, key=f"cant_{sku_clean}")
                        cantidades_solicitadas[sku_clean] = cant

                if st.button("🚀 Generar Ruta de Picking Óptima", type="primary"):
                    puntos_extraccion = []
                    operaciones_db = []

                    for sku_clean, cant_solicitada in cantidades_solicitadas.items():
                        df_casillas = obtener_df("""
                            SELECT i.id_inventario, i.id_ubicacion, i.cantidad, u.coord_x, u.coord_y
                            FROM inventario i
                            JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion
                            WHERE i.sku = %s AND u.id_bodega = %s
                            ORDER BY i.cantidad ASC
                        """, (sku_clean, st.session_state.bodega_activa))

                        por_despachar = cant_solicitada

                        for _, row in df_casillas.iterrows():
                            if por_despachar <= 0:
                                break

                            id_inv = row["id_inventario"]
                            ubi = row["id_ubicacion"]
                            cant_en_casilla = row["cantidad"]
                            cx, cy = row["coord_x"], row["coord_y"]

                            if cant_en_casilla <= por_despachar:
                                despacho_casilla = cant_en_casilla
                                operaciones_db.append({"tipo": "DELETE", "id_inventario": id_inv, "id_ubicacion": ubi, "sku": sku_clean, "cantidad": despacho_casilla})
                            else:
                                despacho_casilla = por_despachar
                                nueva_cant = cant_en_casilla - por_despachar
                                operaciones_db.append({"tipo": "UPDATE", "id_inventario": id_inv, "nueva_cantidad": nueva_cant, "id_ubicacion": ubi, "sku": sku_clean, "cantidad": despacho_casilla})

                            por_despachar -= despacho_casilla
                            puntos_extraccion.append({"SKU": sku_clean, "Ubicación": ubi, "Extraer": despacho_casilla, "x": cx, "y": cy})

                    pos_actual = (0, 0)
                    ruta_ordenada = []
                    distancia_total = 0.0
                    pendientes = puntos_extraccion.copy()
                    paso = 1

                    while pendientes:
                        mejor_idx = 0
                        menor_dist = abs(pendientes[0]["x"] - pos_actual[0]) + abs(pendientes[0]["y"] - pos_actual[1])

                        for i in range(1, len(pendientes)):
                            dist = abs(pendientes[i]["x"] - pos_actual[0]) + abs(pendientes[i]["y"] - pos_actual[1])
                            if dist < menor_dist:
                                menor_dist = dist
                                mejor_idx = i

                        siguiente_punto = pendientes.pop(mejor_idx)
                        distancia_total += menor_dist
                        pos_actual = (siguiente_punto["x"], siguiente_punto["y"])
                        siguiente_punto["Paso"] = paso
                        siguiente_punto["Dist. Tramo (m)"] = menor_dist
                        ruta_ordenada.append(siguiente_punto)
                        paso += 1

                    df_hoja_ruta = pd.DataFrame(ruta_ordenada)
                    if not df_hoja_ruta.empty:
                        df_hoja_ruta = df_hoja_ruta[["Paso", "Ubicación", "SKU", "Extraer", "Dist. Tramo (m)", "x", "y"]]

                    st.session_state.hoja_ruta_persistente = df_hoja_ruta
                    st.session_state.distancia_total_persistente = distancia_total
                    st.session_state.operaciones_pendientes_picking = operaciones_db
                    st.rerun()

            if st.session_state.hoja_ruta_persistente is not None:
                st.markdown("---")
                st.subheader("📋 Hoja de Ruta Activa:")
                st.info(f"📏 Distancia Total Estimada: {st.session_state.distancia_total_persistente:.1f} m")
                st.dataframe(st.session_state.hoja_ruta_persistente, use_container_width=True)

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.button("❌ Cancelar Ruta", use_container_width=True, on_click=cancelar_picking_callback)
                with col_btn2:
                    st.button("✅ Confirmar y Finalizar Picking", type="primary", use_container_width=True, on_click=confirmar_picking_callback)

    # DASHBOARD
    elif menu == "📊 Dashboard & KPIs":
        st.header(f"Analítica de Operación y Reportes - {st.session_state.bodega_activa}")

        # ---------------------------------------------------------
        # BLOQUE 1: MÉTRICAS PRINCIPALES DE INVENTARIO
        # ---------------------------------------------------------
        st.subheader("📌 Métricas Principales de Inventario")

        total_casillas = obtener_df("SELECT COUNT(*) as t FROM ubicaciones WHERE id_bodega = %s", (st.session_state.bodega_activa,))["t"].values[0] or 1
        casillas_ocupadas = obtener_df("SELECT COUNT(*) as t FROM ubicaciones WHERE estado = 'Ocupado' AND id_bodega = %s", (st.session_state.bodega_activa,))["t"].values[0]
        casillas_libres = total_casillas - casillas_ocupadas

        stock_actual = obtener_df("""
            SELECT COALESCE(SUM(i.cantidad), 0) as t 
            FROM inventario i 
            JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion 
            WHERE u.id_bodega = %s
        """, (st.session_state.bodega_activa,))["t"].values[0]

        capacidad_total_bodega = obtener_df("""
            SELECT COALESCE(SUM(p.capacidad_por_casilla), 500) as t 
            FROM ubicaciones u 
            LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
            LEFT JOIN productos p ON i.sku = p.sku 
            WHERE u.id_bodega = %s
        """, (st.session_state.bodega_activa,))["t"].values[0] or 500

        total_skus = obtener_df("SELECT COUNT(*) as t FROM productos")["t"].values[0]

        kpi1, kpi2 = st.columns(2)
        kpi1.metric("Total SKUs Registrados", f"{total_skus} Productos")
        kpi2.metric("Total Unidades en Stock", f"{stock_actual:.1f} Un.")

        st.markdown("---")

        # ---------------------------------------------------------
        # BLOQUE 2: RENDIMIENTO DE PICKING / DESPACHOS
        # ---------------------------------------------------------
        st.subheader("🛒 Rendimiento de Picking / Despachos")

        picking_mes_actual = obtener_df("""
            SELECT COALESCE(SUM(cantidad), 0) as t 
            FROM historial_movimientos 
            WHERE tipo_movimiento = 'DESPACHO' AND id_bodega = %s 
              AND MONTH(fecha_hora) = MONTH(CURRENT_DATE()) 
              AND YEAR(fecha_hora) = YEAR(CURRENT_DATE())
        """, (st.session_state.bodega_activa,))["t"].values[0]

        picking_mes_pasado = obtener_df("""
            SELECT COALESCE(SUM(cantidad), 0) as t 
            FROM historial_movimientos 
            WHERE tipo_movimiento = 'DESPACHO' AND id_bodega = %s 
              AND MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH) 
              AND YEAR(fecha_hora) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)
        """, (st.session_state.bodega_activa,))["t"].values[0]

        diff_picking = picking_mes_actual - picking_mes_pasado
        delta_str = f"↑ +{diff_picking:.0f} Unid. vs Mes Pasado" if diff_picking >= 0 else f"↓ {diff_picking:.0f} Unid. vs Mes Pasado"

        p_col1, p_col2, p_col3 = st.columns(3)
        p_col1.metric("Picking Mes Actual", f"{picking_mes_actual:.0f} Unidades", delta_str)
        p_col2.metric("Picking Mes Pasado", f"{picking_mes_pasado:.0f} Unidades")
        p_col3.metric("Casillas Disponibles / Libres", f"{casillas_libres}")

        st.markdown("---")

        # ---------------------------------------------------------
        # BLOQUE 3: TENDENCIA DIARIA DE PICKING CON FILTRO DE SKU
        # ---------------------------------------------------------
        st.subheader("📈 Tendencia Diaria de Picking (Días 1 al 31)")

        df_skus_picking = obtener_df("""
            SELECT DISTINCT h.sku, p.nombre
            FROM historial_movimientos h
            JOIN productos p ON h.sku = p.sku
            WHERE h.tipo_movimiento = 'DESPACHO' AND h.id_bodega = %s
            ORDER BY h.sku ASC
        """, (st.session_state.bodega_activa,))

        opciones_filtro_sku = ["🔍 Todos los SKUs (Suma Global)"] + (
            df_skus_picking["sku"] + " - " + df_skus_picking["nombre"]
        ).tolist() if not df_skus_picking.empty else ["🔍 Todos los SKUs (Suma Global)"]

        sku_filtro_sel = st.selectbox("📦 Filtrar Serie Temporal por SKU:", opciones_filtro_sku)

        if sku_filtro_sel == "🔍 Todos los SKUs (Suma Global)":
            query_picking_diario = """
                SELECT DAY(fecha_hora) AS dia,
                       SUM(CASE WHEN MONTH(fecha_hora) = MONTH(CURRENT_DATE()) THEN cantidad ELSE 0 END) AS Mes_Actual,
                       SUM(CASE WHEN MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH) THEN cantidad ELSE 0 END) AS Mes_Anterior
                FROM historial_movimientos
                WHERE tipo_movimiento = 'DESPACHO' AND id_bodega = %s
                GROUP BY DAY(fecha_hora)
            """
            params_picking = (st.session_state.bodega_activa,)
        else:
            sku_clean_filtro = sku_filtro_sel.split(" - ")[0]
            query_picking_diario = """
                SELECT DAY(fecha_hora) AS dia,
                       SUM(CASE WHEN MONTH(fecha_hora) = MONTH(CURRENT_DATE()) THEN cantidad ELSE 0 END) AS Mes_Actual,
                       SUM(CASE WHEN MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH) THEN cantidad ELSE 0 END) AS Mes_Anterior
                FROM historial_movimientos
                WHERE tipo_movimiento = 'DESPACHO' AND id_bodega = %s AND sku = %s
                GROUP BY DAY(fecha_hora)
            """
            params_picking = (st.session_state.bodega_activa, sku_clean_filtro)

        df_picking_diario = obtener_df(query_picking_diario, params_picking)

        df_31_dias = pd.DataFrame({"dia": list(range(1, 32))})
        if not df_picking_diario.empty:
            df_chart_picking = pd.merge(df_31_dias, df_picking_diario, on="dia", how="left").fillna(0)
        else:
            df_chart_picking = df_31_dias.copy()
            df_chart_picking["Mes_Actual"] = 0
            df_chart_picking["Mes_Anterior"] = 0

        df_chart_melted = df_chart_picking.melt(
            id_vars=["dia"], 
            value_vars=["Mes_Actual", "Mes_Anterior"],
            var_name="Periodo", 
            value_name="Unidades Despachadas"
        )
        df_chart_melted["Periodo"] = df_chart_melted["Periodo"].replace({"Mes_Actual": "Mes Actual", "Mes_Anterior": "Mes Anterior"})

        fig_picking_line = px.line(
            df_chart_melted,
            x="dia",
            y="Unidades Despachadas",
            color="Periodo",
            markers=True,
            title=f"Evolución del Picking Diario - {sku_filtro_sel}",
            labels={"dia": "Día del Mes", "Unidades Despachadas": "Unidades Despachadas"},
            color_discrete_map={"Mes Actual": "#1F3864", "Mes Anterior": "#94A3B8"}
        )
        fig_picking_line.update_layout(
            height=400, 
            xaxis=dict(tickmode="linear", dtick=1),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_picking_line, use_container_width=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # BLOQUE 4: GRÁFICOS DE DONA / ANILLO COMPARATIVOS
        # ---------------------------------------------------------
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("📦 Ocupación Volumétrica de Bodega")
            
            capacidad_libre = max(0.0, capacidad_total_bodega - stock_actual)
            df_volumen = pd.DataFrame({
                "Estado_Volumen": ["Capacidad Usada", "Capacidad Disponible"],
                "Unidades": [stock_actual, capacidad_libre]
            })

            fig_pie_vol = px.pie(
                df_volumen,
                names="Estado_Volumen",
                values="Unidades",
                hole=0.4,
                color="Estado_Volumen",
                color_discrete_map={"Capacidad Usada": "#1F3864", "Capacidad Disponible": "#E2E8F0"}
            )
            fig_pie_vol.update_traces(textinfo="percent+label")
            fig_pie_vol.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie_vol, use_container_width=True)

        with col_g2:
            st.subheader("🎯 Ocupación Física de Casillas")
            df_estados = obtener_df("""
                SELECT estado, COUNT(*) as cantidad
                FROM ubicaciones
                WHERE id_bodega = %s
                GROUP BY estado
            """, (st.session_state.bodega_activa,))

            if df_estados.empty:
                st.info("No hay casillas registradas.")
            else:
                fig_pie = px.pie(
                    df_estados,
                    names="estado",
                    values="cantidad",
                    hole=0.4,
                    color="estado",
                    color_discrete_map={"Libre": "#10B981", "Ocupado": "#EF4444", "Inhabilitado": "#94A3B8"}
                )
                fig_pie.update_traces(textinfo="percent+label")
                fig_pie.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # BLOQUE 5: REPORTES DE SKUs SIN MOVIMIENTO (BAJA ROTACIÓN)
        # ---------------------------------------------------------
        st.subheader("🧊 Reporte de SKUs Sin Movimiento (Baja Rotación / Stock Inactivo)")

        dias_umbral = st.slider("🗿 Seleccionar umbral de inactividad (Días sin movimiento):", min_value=0, max_value=90, value=0)

        query_inactivos = """
            SELECT i.sku, p.nombre, SUM(i.cantidad) AS stock_actual,
                   COALESCE(MAX(h.fecha_hora), 'Sin Movimientos Registrados') AS ultima_fecha_movimiento,
                   COALESCE(DATEDIFF(CURRENT_DATE(), MAX(h.fecha_hora)), 999) AS dias_sin_movimiento
            FROM inventario i
            JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion
            JOIN productos p ON i.sku = p.sku
            LEFT JOIN historial_movimientos h ON i.sku = h.sku AND h.id_bodega = %s
            WHERE u.id_bodega = %s
            GROUP BY i.sku, p.nombre
            HAVING dias_sin_movimiento >= %s
            ORDER BY dias_sin_movimiento DESC;
        """
        df_inactivos = obtener_df(query_inactivos, (st.session_state.bodega_activa, st.session_state.bodega_activa, dias_umbral))

        if df_inactivos.empty:
            st.success(f"🎉 ¡Excelente! No hay SKUs con más de {dias_umbral} días sin movimiento en {st.session_state.bodega_activa}.")
        else:
            st.warning(f"⚠️ Se encontraron {len(df_inactivos)} SKU(s) con stock guardado sin registrar ningún movimiento en {dias_umbral} días o más.")
            st.dataframe(df_inactivos[["sku", "nombre", "stock_actual", "ultima_fecha_movimiento", "dias_sin_movimiento"]], use_container_width=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # BLOQUE 6: EXPORTAR REPORTE EXCEL COMPLETO
        # ---------------------------------------------------------
        df_inv_exp = obtener_df("SELECT i.*, u.id_bodega FROM inventario i JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion WHERE u.id_bodega = %s", (st.session_state.bodega_activa,))
        df_kardex_exp = obtener_df("SELECT * FROM historial_movimientos WHERE id_bodega = %s ORDER BY fecha_hora DESC", (st.session_state.bodega_activa,))

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_inv_exp.to_excel(writer, sheet_name="Inventario_Actual", index=False)
            df_kardex_exp.to_excel(writer, sheet_name="Kardex_Movimientos", index=False)
            if not df_inactivos.empty:
                df_inactivos.to_excel(writer, sheet_name="Stock_Inactivo", index=False)

        st.download_button(
            label=f"📥 Descargar Reporte Completo {st.session_state.bodega_activa} (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"Reporte_WMS_Completo_{st.session_state.bodega_activa}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

    # KÁRDEX
    elif menu == "📜 Historial Kárdex":
        st.header(f"Trazabilidad ({st.session_state.bodega_activa})")
        df_kardex = obtener_df("SELECT id_movimiento, fecha_hora, tipo_movimiento, sku, id_ubicacion, cantidad, id_bodega FROM historial_movimientos WHERE id_bodega = %s ORDER BY fecha_hora DESC", (st.session_state.bodega_activa,))

        if df_kardex.empty:
            st.info(f"No hay movimientos registrados en {st.session_state.bodega_activa}.")
        else:
            st.dataframe(df_kardex, use_container_width=True)

    # QR
    elif menu == "🏷️ Generador de Etiquetas QR":
        st.header("Generador de Etiquetas QR")
        opcion_qr = st.radio("Tipo de etiqueta", ["Ubicación / Casilla", "Producto / SKU"])

        if opcion_qr == "Ubicación / Casilla":
            df_ubis = obtener_df("SELECT id_ubicacion FROM ubicaciones WHERE id_bodega = %s", (st.session_state.bodega_activa,))
            if not df_ubis.empty:
                ubi_sel = st.selectbox("Seleccionar Casilla", df_ubis["id_ubicacion"])

                if st.button("Generar QR", type="primary"):
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(f"WMS-UBICACION:{st.session_state.bodega_activa}:{ubi_sel}")
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")

                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    st.image(buf.getvalue(), caption=f"QR Casilla: {ubi_sel} ({st.session_state.bodega_activa})", width=250)
                    st.download_button(label=f"📥 Descargar QR {ubi_sel}.png", data=buf.getvalue(), file_name=f"QR_{st.session_state.bodega_activa}_{ubi_sel}.png", mime="image/png", type="primary")
        else:
            df_prods = obtener_df("SELECT sku, nombre FROM productos")
            if not df_prods.empty:
                prod_sel = st.selectbox("Seleccionar Producto", df_prods["sku"] + " - " + df_prods["nombre"])
                sku_qr = prod_sel.split(" - ")[0]

                if st.button("Generar QR", type="primary"):
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(f"WMS-SKU:{sku_qr}")
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")

                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    st.image(buf.getvalue(), caption=f"QR SKU: {sku_qr}", width=250)
                    st.download_button(label=f"📥 Descargar QR {sku_qr}.png", data=buf.getvalue(), file_name=f"QR_SKU_{sku_qr}.png", mime="image/png", type="primary")
