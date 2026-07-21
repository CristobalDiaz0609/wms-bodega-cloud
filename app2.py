import io
import mysql.connector
import pandas as pd
import plotly.express as px
import qrcode
import streamlit as st
from PIL import Image

st.set_page_config(
    page_title="WMS Bodega Inteligente", layout="wide", page_icon="📦"
)


# ---------------------------------------------------------
# CONEXIÓN A BASE DE DATOS (Adaptado para Streamlit Cloud / Aiven)
# ---------------------------------------------------------
def obtener_conexion():
    return mysql.connector.connect(
        host=st.secrets["mysql"]["host"],
        port=int(st.secrets["mysql"]["port"]),
        user=st.secrets["mysql"]["user"],
        password=st.secrets["mysql"]["password"],
        database=st.secrets["mysql"]["database"],
    )


# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE CONSULTA
# ---------------------------------------------------------
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
# INTERFAZ Y NAVEGACIÓN
# ---------------------------------------------------------
st.title("📦 Sistema de Gestión de Bodega (WMS 2D)")

menu = st.sidebar.radio(
    "Navegación / Módulos",
    [
        "🗺️ Mapa 2D & Estado",
        "📥 Recepción e Ingreso",
        "🛒 Picking / Despacho",
        "📊 Dashboard & KPIs",
        "📜 Historial Kárdex",
        "🏷️ Generador de Etiquetas QR",
    ],
)

# ---------------------------------------------------------
# 1. MAPA 2D & ESTADO DE UBICACIONES
# ---------------------------------------------------------
if menu == "🗺️ Mapa 2D & Estado":
    st.header("Mapa de Ocupación Física 2D")

    query = """
    SELECT u.id_ubicacion, u.coord_x, u.coord_y, u.estado,
           COALESCE(i.sku, 'Vacío') AS sku,
           COALESCE(i.cantidad, 0) AS cantidad,
           COALESCE(p.nombre, 'Sin Producto') AS producto,
           COALESCE(p.capacidad_por_casilla, 10) AS capacidad
    FROM ubicaciones u
    LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
    LEFT JOIN productos p ON i.sku = p.sku;
    """
    df_mapa = obtener_df(query)

    if not df_mapa.empty:
        df_mapa["Ocupacion_%"] = (
            df_mapa["cantidad"] / df_mapa["capacidad"]
        ) * 100

        fig = px.scatter(
            df_mapa,
            x="coord_x",
            y="coord_y",
            color="estado",
            size="cantidad",
            size_max=30,
            hover_name="id_ubicacion",
            hover_data=[
                "sku",
                "producto",
                "cantidad",
                "capacidad",
                "Ocupacion_%",
            ],
            text="id_ubicacion",
            color_discrete_map={
                "Libre": "#2ecc71",
                "Ocupado": "#e74c3c",
                "Inhabilitado": "#95a5a6",
            },
            title="Distribución Espacial de Casillas",
        )
        fig.update_traces(textposition="top center")
        fig.update_layout(
            xaxis=dict(tickmode="linear", dtick=1),
            yaxis=dict(tickmode="linear", dtick=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Detalle de Ubicaciones")
        st.dataframe(
            df_mapa[[
                "id_ubicacion",
                "estado",
                "sku",
                "producto",
                "cantidad",
                "capacidad",
                "Ocupacion_%",
            ]],
            use_container_width=True,
        )

# ---------------------------------------------------------
# 2. RECEPCIÓN E INGRESO DE MERCADERÍA
# ---------------------------------------------------------
elif menu == "📥 Recepción e Ingreso":
    st.header("Ingreso de Stock a Bodega")

    df_prods = obtener_df(
        "SELECT sku, nombre, capacidad_por_casilla FROM productos"
    )
    df_libres = obtener_df(
        "SELECT id_ubicacion FROM ubicaciones WHERE estado = 'Libre'"
    )

    if df_prods.empty or df_libres.empty:
        st.warning(
            "Asegúrate de tener productos registrados y casillas libres"
            " disponibles."
        )
    else:
        with st.form("form_ingreso"):
            sku_sel = st.selectbox(
                "Seleccionar Producto (SKU)",
                df_prods["sku"] + " - " + df_prods["nombre"],
            )
            sku_limpio = sku_sel.split(" - ")[0]

            cap_max = df_prods[df_prods["sku"] == sku_limpio][
                "capacidad_por_casilla"
            ].values[0]
            st.info(
                f"Capacidad máxima permitida por casilla para este SKU:"
                f" {cap_max} unidades."
            )

            ubicacion_sel = st.selectbox(
                "Seleccionar Casilla Disponible", df_libres["id_ubicacion"]
            )
            cantidad_ingreso = st.number_input(
                "Cantidad a Ingresar",
                min_value=1,
                max_value=int(cap_max),
                value=1,
            )

            btn_ingresar = st.form_submit_button("Confirmar Ingreso")

            if btn_ingresar:
                ejecutar_query(
                    "INSERT INTO inventario (id_ubicacion, sku, cantidad)"
                    " VALUES (%s, %s, %s)",
                    (ubicacion_sel, sku_limpio, cantidad_ingreso),
                )
                ejecutar_query(
                    "UPDATE ubicaciones SET estado = 'Ocupado' WHERE"
                    " id_ubicacion = %s",
                    (ubicacion_sel,),
                )
                ejecutar_query(
                    "INSERT INTO historial_movimientos (tipo_movimiento, sku,"
                    " id_ubicacion, cantidad) VALUES ('ENTRADA', %s, %s, %s)",
                    (sku_limpio, ubicacion_sel, cantidad_ingreso),
                )
                st.success(
                    f"✅ Se ingresaron {cantidad_ingreso} unidades de"
                    f" {sku_limpio} en la casilla {ubicacion_sel}."
                )
                st.rerun()

# ---------------------------------------------------------
# 3. PICKING / DESPACHO DE PEDIDOS (Con Estado de Sesión Persistente)
# ---------------------------------------------------------
elif menu == "🛒 Picking / Despacho":
    st.header("Motor de Picking y Despacho")

    # Inicializar la variable persistente en el estado de la sesión si no existe
    if "hoja_ruta_persistente" not in st.session_state:
        st.session_state.hoja_ruta_persistente = None

    df_inv = obtener_df("""
        SELECT i.sku, p.nombre, SUM(i.cantidad) as total_disponible
        FROM inventario i
        JOIN productos p ON i.sku = p.sku
        GROUP BY i.sku, p.nombre
    """)

    if df_inv.empty:
        st.info("No hay inventario disponible en la bodega para realizar despachos.")
    else:
        sku_despacho = st.selectbox(
            "Seleccionar Producto a Despachar",
            df_inv["sku"] + " - " + df_inv["nombre"],
        )
        sku_clean = sku_despacho.split(" - ")[0]

        max_disponible = int(
            df_inv[df_inv["sku"] == sku_clean]["total_disponible"].values[0]
        )
        cant_solicitada = st.number_input(
            f"Cantidad a Solicitar (Máx: {max_disponible})",
            min_value=1,
            max_value=max_disponible,
            value=1,
        )

        # Al presionar el botón calculamos y GUARDAMOS la ruta en st.session_state
        if st.button("Generar Hoja de Ruta / Ejecutar Picking"):
            df_casillas = obtener_df(
                "SELECT id_inventario, id_ubicacion, cantidad FROM inventario"
                " WHERE sku = %s ORDER BY cantidad ASC",
                (sku_clean,),
            )

            por_despachar = cant_solicitada
            hoja_ruta = []

            for idx, row in df_casillas.iterrows():
                if por_despachar <= 0:
                    break

                id_inv = row["id_inventario"]
                ubi = row["id_ubicacion"]
                cant_en_casilla = row["cantidad"]

                if cant_en_casilla <= por_despachar:
                    despacho_casilla = cant_en_casilla
                    ejecutar_query(
                        "DELETE FROM inventario WHERE id_inventario = %s",
                        (id_inv,),
                    )
                    ejecutar_query(
                        "UPDATE ubicaciones SET estado = 'Libre' WHERE"
                        " id_ubicacion = %s",
                        (ubi,),
                    )
                else:
                    despacho_casilla = por_despachar
                    nueva_cant = cant_en_casilla - por_despachar
                    ejecutar_query(
                        "UPDATE inventario SET cantidad = %s WHERE"
                        " id_inventario = %s",
                        (nueva_cant, id_inv),
                    )

                ejecutar_query(
                    "INSERT INTO historial_movimientos (tipo_movimiento, sku,"
                    " id_ubicacion, cantidad) VALUES ('DESPACHO', %s, %s, %s)",
                    (sku_clean, ubi, despacho_casilla),
                )

                por_despachar -= despacho_casilla
                hoja_ruta.append({"Ubicación": ubi, "Extraer": despacho_casilla})

            # Guardar el DataFrame generado en la sesión
            st.session_state.hoja_ruta_persistente = pd.DataFrame(hoja_ruta)
            st.success("🎉 ¡Picking completado con éxito!")

        # Renderizar la Hoja de Ruta mientras siga guardada en la sesión
        if st.session_state.hoja_ruta_persistente is not None:
            st.markdown("---")
            st.subheader("📋 Hoja de Ruta Activa para Operador:")
            st.table(st.session_state.hoja_ruta_persistente)

            # Botón para limpiar la vista cuando el operador termine la tarea
            if st.button("🗑️ Limpiar / Finalizar Ruta"):
                st.session_state.hoja_ruta_persistente = None
                st.rerun()

# ---------------------------------------------------------
# 4. DASHBOARD & KPIS
# ---------------------------------------------------------
elif menu == "📊 Dashboard & KPIs":
    st.header("Analítica de Operación y Reportes")

    total_casillas = obtener_df("SELECT COUNT(*) as t FROM ubicaciones")[
        "t"
    ].values[0]
    casillas_ocupadas = obtener_df(
        "SELECT COUNT(*) as t FROM ubicaciones WHERE estado = 'Ocupado'"
    )["t"].values[0]

    cap_tot = (
        obtener_df("""
        SELECT SUM(p.capacidad_por_casilla) as t 
        FROM ubicaciones u 
        CROSS JOIN (SELECT AVG(capacidad_por_casilla) as capacidad_por_casilla FROM productos) p
    """)["t"].values[0]
        or 1
    )

    stock_actual = obtener_df(
        "SELECT COALESCE(SUM(cantidad), 0) as t FROM inventario"
    )["t"].values[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Ocupación de Casillas",
        f"{(casillas_ocupadas/total_casillas)*100:.1f}%",
        f"{casillas_ocupadas}/{total_casillas} Módulos",
    )
    col2.metric(
        "Ocupación Volumétrica",
        f"{(stock_actual/cap_tot)*100:.1f}%",
        f"{stock_actual} Unidades",
    )
    col3.metric("Casillas Libres", f"{total_casillas - casillas_ocupadas}")
    col4.metric("Total Unidades en Stock", f"{stock_actual}")

    st.markdown("---")

    # Exportación a Excel
    st.subheader("📤 Exportar Reportes a Excel")

    df_inv_exp = obtener_df("SELECT * FROM inventario")
    df_kardex_exp = obtener_df(
        "SELECT * FROM historial_movimientos ORDER BY fecha_hora DESC"
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_inv_exp.to_excel(
            writer, sheet_name="Inventario_Actual", index=False
        )
        df_kardex_exp.to_excel(
            writer, sheet_name="Kardex_Movimientos", index=False
        )

    st.download_button(
        label="📥 Descargar Reporte Completo (.xlsx)",
        data=buffer.getvalue(),
        file_name="Reporte_WMS_Bodega.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )

# ---------------------------------------------------------
# 5. HISTORIAL KÁRDEX
# ---------------------------------------------------------
elif menu == "📜 Historial Kárdex":
    st.header("Trazabilidad y Auditoría (Kárdex)")

    df_kardex = obtener_df("""
        SELECT id_movimiento, fecha_hora, tipo_movimiento, sku, id_ubicacion, cantidad 
        FROM historial_movimientos 
        ORDER BY fecha_hora DESC
    """)

    if df_kardex.empty:
        st.info("No hay registros de movimientos en la base de datos.")
    else:
        st.dataframe(df_kardex, use_container_width=True)

# ---------------------------------------------------------
# 6. GENERADOR DE ETIQUETAS QR
# ---------------------------------------------------------
elif menu == "🏷️ Generador de Etiquetas QR":
    st.header("Generador e Impresión de Etiquetas QR")
    st.write(
        "Genera e imprime códigos QR para identificar casillas físicamente o"
        " etiquetar paletas/productos."
    )

    opcion_qr = st.radio(
        "¿Qué tipo de etiqueta deseas generar?",
        ["Ubicación / Casilla", "Producto / SKU"],
    )

    if opcion_qr == "Ubicación / Casilla":
        df_ubis = obtener_df("SELECT id_ubicacion FROM ubicaciones")
        if not df_ubis.empty:
            ubi_sel = st.selectbox(
                "Seleccionar Casilla para Etiquetar", df_ubis["id_ubicacion"]
            )

            if st.button("Generar Código QR de Casilla"):
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(f"WMS-UBICACION:{ubi_sel}")
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                buf = io.BytesIO()
                img.save(buf, format="PNG")

                st.image(
                    buf.getvalue(),
                    caption=f"Etiqueta QR para Casilla: {ubi_sel}",
                    width=250,
                )
                st.download_button(
                    label=f"📥 Descargar QR {ubi_sel}.png",
                    data=buf.getvalue(),
                    file_name=f"QR_Ubicacion_{ubi_sel}.png",
                    mime="image/png",
                )
    else:
        df_prods = obtener_df("SELECT sku, nombre FROM productos")
        if not df_prods.empty:
            prod_sel = st.selectbox(
                "Seleccionar Producto para Etiquetar",
                df_prods["sku"] + " - " + df_prods["nombre"],
            )
            sku_qr = prod_sel.split(" - ")[0]

            if st.button("Generar Código QR de Producto"):
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(f"WMS-SKU:{sku_qr}")
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                buf = io.BytesIO()
                img.save(buf, format="PNG")

                st.image(
                    buf.getvalue(),
                    caption=f"Etiqueta QR para SKU: {sku_qr}",
                    width=250,
                )
                st.download_button(
                    label=f"📥 Descargar QR {sku_qr}.png",
                    data=buf.getvalue(),
                    file_name=f"QR_SKU_{sku_qr}.png",
                    mime="image/png",
                )
