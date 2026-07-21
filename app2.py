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
# CONEXIÓN A BASE DE DATOS
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
        fig.update_traces(
            marker=dict(size=28, line=dict(width=1, color="DarkSlateGrey")),
            textposition="top center",
        )
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
# 2. RECEPCIÓN E INGRESO DE MERCADERÍA (CON CONSOLIDACIÓN)
# ---------------------------------------------------------
elif menu == "📥 Recepción e Ingreso":
    st.header("Ingreso de Stock a Bodega")

    df_prods = obtener_df(
        "SELECT sku, nombre, capacidad_por_casilla FROM productos"
    )

    if df_prods.empty:
        st.warning("Asegúrate de tener productos registrados en el sistema.")
    else:
        sku_sel = st.selectbox(
            "Seleccionar Producto (SKU)",
            df_prods["sku"] + " - " + df_prods["nombre"],
        )
        sku_limpio = sku_sel.split(" - ")[0]

        cap_max = int(
            df_prods[df_prods["sku"] == sku_limpio][
                "capacidad_por_casilla"
            ].values[0]
        )

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
            WHERE u.estado != 'Inhabilitado' 
              AND (
                  i.id_inventario IS NULL 
                  OR (i.sku = %s AND i.cantidad < %s)
              );
        """
        df_disponibles = obtener_df(
            query_disponibles, (cap_max, sku_limpio, cap_max)
        )

        if df_disponibles.empty:
            st.error(
                "❌ No hay casillas disponibles ni espacio suficiente para"
                " consolidar este producto."
            )
        else:
            df_disponibles["opcion_texto"] = (
                df_disponibles["id_ubicacion"]
                + " ["
                + df_disponibles["tipo_casilla"]
                + " - Espacio libre: "
                + df_disponibles["espacio_disponible"].astype(str)
                + " un.]"
            )

            with st.form("form_ingreso"):
                ubi_seleccionada_txt = st.selectbox(
                    "Seleccionar Casilla Destino",
                    df_disponibles["opcion_texto"],
                )
                ubi_limpia = ubi_seleccionada_txt.split(" [")[0]

                espacio_max = int(
                    df_disponibles[
                        df_disponibles["id_ubicacion"] == ubi_limpia
                    ]["espacio_disponible"].values[0]
                )

                st.info(
                    f"Espacio máximo disponible en la casilla {ubi_limpia}:"
                    f" {espacio_max} unidades."
                )

                cantidad_ingreso = st.number_input(
                    "Cantidad a Ingresar",
                    min_value=1,
                    max_value=espacio_max,
                    value=1,
                )

                btn_ingresar = st.form_submit_button("Confirmar Ingreso")

                if btn_ingresar:
                    inv_existente = obtener_df(
                        "SELECT id_inventario, cantidad FROM inventario WHERE"
                        " id_ubicacion = %s",
                        (ubi_limpia,),
                    )

                    if inv_existente.empty:
                        ejecutar_query(
                            "INSERT INTO inventario (id_ubicacion, sku,"
                            " cantidad) VALUES (%s, %s, %s)",
                            (ubi_limpia, sku_limpio, cantidad_ingreso),
                        )
                    else:
                        nueva_cant = (
                            int(inv_existente["cantidad"].values[0])
                            + cantidad_ingreso
                        )
                        ejecutar_query(
                            "UPDATE inventario SET cantidad = %s WHERE"
                            " id_ubicacion = %s",
                            (nueva_cant, ubi_limpia),
                        )

                    ejecutar_query(
                        "UPDATE ubicaciones SET estado = 'Ocupado' WHERE"
                        " id_ubicacion = %s",
                        (ubi_limpia,),
                    )

                    ejecutar_query(
                        "INSERT INTO historial_movimientos (tipo_movimiento,"
                        " sku, id_ubicacion, cantidad) VALUES ('ENTRADA', %s,"
                        " %s, %s)",
                        (sku_limpio, ubi_limpia, cantidad_ingreso),
                    )

                    st.success(
                        f"✅ Se ingresaron {cantidad_ingreso} unidades de"
                        f" {sku_limpio} en la casilla {ubi_limpia}."
                    )
                    st.rerun()

# ---------------------------------------------------------
# 3. PICKING / DESPACHO DE PEDIDOS (MULTI-SKU)
# ---------------------------------------------------------
elif menu == "🛒 Picking / Despacho":
    st.header("Motor de Picking y Despacho Multi-SKU")

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
        st.subheader("1. Selección de Productos para el Pedido")
        
        df_inv["opcion_display"] = df_inv["sku"] + " - " + df_inv["nombre"] + " (Stock: " + df_inv["total_disponible"].astype(str) + ")"
        
        skus_seleccionados = st.multiselect(
            "Seleccionar Producto(s) a Despachar",
            df_inv["opcion_display"]
        )

        if skus_seleccionados:
            st.markdown("---")
            st.subheader("2. Definir Cantidades a Extraer")
            
            cantidades_solicitadas = {}
            with st.form("form_multi_picking"):
                cols = st.columns(min(len(skus_seleccionados), 3))
                
                for idx, item in enumerate(skus_seleccionados):
                    sku_clean = item.split(" - ")[0]
                    nombre_prod = item.split(" - ")[1].split(" (")[0]
                    max_disp = int(df_inv[df_inv["sku"] == sku_clean]["total_disponible"].values[0])
                    
                    with cols[idx % 3]:
                        st.markdown(f"**{sku_clean}** - {nombre_prod}")
                        cant = st.number_input(
                            f"Cantidad (Máx: {max_disp})",
                            min_value=1,
                            max_value=max_disp,
                            value=1,
                            key=f"cant_{sku_clean}"
                        )
                        cantidades_solicitadas[sku_clean] = cant

                btn_generar_ruta = st.form_submit_button("🚀 Generar Hoja de Ruta / Ejecutar Picking")

                if btn_generar_ruta:
                    hoja_ruta = []

                    for sku_clean, cant_solicitada in cantidades_solicitadas.items():
                        df_casillas = obtener_df(
                            "SELECT id_inventario, id_ubicacion, cantidad FROM inventario WHERE sku = %s ORDER BY cantidad ASC",
                            (sku_clean,),
                        )

                        por_despachar = cant_solicitada

                        for _, row in df_casillas.iterrows():
                            if por_despachar <= 0:
                                break

                            id_inv = row["id_inventario"]
                            ubi = row["id_ubicacion"]
                            cant_en_casilla = row["cantidad"]

                            if cant_en_casilla <= por_despachar:
                                despacho_casilla = cant_en_casilla
                                ejecutar_query("DELETE FROM inventario WHERE id_inventario = %s", (id_inv,))
                                ejecutar_query("UPDATE ubicaciones SET estado = 'Libre' WHERE id_ubicacion = %s", (ubi,))
                            else:
                                despacho_casilla = por_despachar
                                nueva_cant = cant_en_casilla - por_despachar
                                ejecutar_query("UPDATE inventario SET cantidad = %s WHERE id_inventario = %s", (nueva_cant, id_inv))

                            ejecutar_query(
                                "INSERT INTO historial_movimientos (tipo_movimiento, sku, id_ubicacion, cantidad) VALUES ('DESPACHO', %s, %s, %s)",
                                (sku_clean, ubi, despacho_casilla),
                            )

                            por_despachar -= despacho_casilla
                            hoja_ruta.append({
                                "SKU": sku_clean,
                                "Ubicación": ubi,
                                "Extraer": despacho_casilla
                            })

                    df_hoja_ruta = pd.DataFrame(hoja_ruta)
                    if not df_hoja_ruta.empty:
                        df_hoja_ruta = df_hoja_ruta.sort_values(by="Ubicación").reset_index(drop=True)

                    st.session_state.hoja_ruta_persistente = df_hoja_ruta
                    st.success("🎉 ¡Picking multi-producto completado con éxito!")
                    st.rerun()

        if st.session_state.hoja_ruta_persistente is not None:
            st.markdown("---")
            st.subheader("📋 Hoja de Ruta Activa para Operador (Optimizada por Ubicación):")
            st.dataframe(st.session_state.hoja_ruta_persistente, use_container_width=True)

            if st.button("🗑️ Limpiar / Finalizar Ruta"):
                st.session_state.hoja_ruta_persistente = None
                st.rerun()

# ---------------------------------------------------------
# 4. DASHBOARD & KPIS
# ---------------------------------------------------------
elif menu == "📊 Dashboard & KPIs":
    st.header("Analítica de Operación y Reportes")

    # --- CONSULTAS BASE A LA BASE DE DATOS ---
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

    total_skus = obtener_df("SELECT COUNT(*) as t FROM productos")["t"].values[
        0
    ]

    picking_mes_actual_raw = obtener_df("""
        SELECT COALESCE(SUM(cantidad), 0) as t 
        FROM historial_movimientos 
        WHERE tipo_movimiento = 'DESPACHO' 
          AND MONTH(fecha_hora) = MONTH(CURRENT_DATE()) 
          AND YEAR(fecha_hora) = YEAR(CURRENT_DATE())
    """)["t"].values[0]

    picking_mes_pasado_raw = obtener_df("""
        SELECT COALESCE(SUM(cantidad), 0) as t 
        FROM historial_movimientos 
        WHERE tipo_movimiento = 'DESPACHO' 
          AND MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH) 
          AND YEAR(fecha_hora) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)
    """)["t"].values[0]

    picking_mes_actual = int(picking_mes_actual_raw)
    picking_mes_pasado = int(picking_mes_pasado_raw)
    delta_picking = picking_mes_actual - picking_mes_pasado

    # --- FILA 1: MÉTRICAS GENERALES DE INVENTARIO ---
    st.subheader("📌 Métricas Principales de Inventario")
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total SKUs Registrados", f"{total_skus} Productos")
    col2.metric("Total Unidades en Stock", f"{stock_actual} Un.")
    col3.metric(
        "Ocupación de Casillas",
        f"{(casillas_ocupadas/total_casillas)*100:.1f}%",
        f"{casillas_ocupadas}/{total_casillas} Casillas",
    )
    col4.metric(
        "Ocupación Volumétrica",
        f"{(stock_actual/cap_tot)*100:.1f}%",
        f"Cap. Máx: {cap_tot}",
    )

    # --- FILA 2: RENDIMIENTO DE PICKING Y DISPONIBILIDAD ---
    st.markdown("---")
    st.subheader("🛒 Rendimiento de Picking / Despachos")
    col_p1, col_p2, col_p3 = st.columns(3)

    col_p1.metric(
        label="Picking Mes Actual",
        value=f"{picking_mes_actual} Unidades",
        delta=f"{delta_picking:+d} Unid. vs Mes Pasado",
    )
    col_p2.metric("Picking Mes Pasado", f"{picking_mes_pasado} Unidades")
    col_p3.metric("Casillas Disponibles / Libres", f"{total_casillas - casillas_ocupadas}")

    # --- GRÁFICO DE LÍNEAS CON FILTRO POR SKU ---
    st.markdown("#### 📈 Tendencia Diaria de Picking (Días 1 al 31)")

    # Obtener catálogo de SKUs para el selector
    df_lista_skus = obtener_df("SELECT sku, nombre FROM productos")
    opciones_sku = ["Todos los SKUs"] + (df_lista_skus["sku"] + " - " + df_lista_skus["nombre"]).tolist()

    sku_filtro_sel = st.selectbox("🔍 Filtrar gráfico por SKU:", opciones_sku)

    # Construir clausula SQL de filtro según la opción elegida
    if sku_filtro_sel == "Todos los SKUs":
        where_sku = ""
        params_sku = ()
    else:
        sku_clean_filtro = sku_filtro_sel.split(" - ")[0]
        where_sku = " AND sku = %s "
        params_sku = (sku_clean_filtro,)

    # Consultas filtradas o globales
    df_diario_actual = obtener_df(f"""
        SELECT DAY(fecha_hora) as dia, SUM(cantidad) as picking_actual
        FROM historial_movimientos
        WHERE tipo_movimiento = 'DESPACHO'
          AND MONTH(fecha_hora) = MONTH(CURRENT_DATE())
          AND YEAR(fecha_hora) = YEAR(CURRENT_DATE())
          {where_sku}
        GROUP BY DAY(fecha_hora)
    """, params_sku if where_sku else None)

    df_diario_pasado = obtener_df(f"""
        SELECT DAY(fecha_hora) as dia, SUM(cantidad) as picking_pasado
        FROM historial_movimientos
        WHERE tipo_movimiento = 'DESPACHO'
          AND MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH)
          AND YEAR(fecha_hora) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)
          {where_sku}
        GROUP BY DAY(fecha_hora)
    """, params_sku if where_sku else None)

    df_dias = pd.DataFrame({"Día del Mes": range(1, 32)})

    df_tendencia = df_dias.merge(df_diario_actual, left_on="Día del Mes", right_on="dia", how="left")
    df_tendencia = df_tendencia.merge(df_diario_pasado, left_on="Día del Mes", right_on="dia", how="left")
    df_tendencia.fillna(0, inplace=True)

    df_lineas = pd.melt(
        df_tendencia,
        id_vars=["Día del Mes"],
        value_vars=["picking_actual", "picking_pasado"],
        var_name="Periodo",
        value_name="Unidades Despachadas"
    )
    df_lineas["Periodo"] = df_lineas["Periodo"].replace({
        "picking_actual": "Mes Actual",
        "picking_pasado": "Mes Anterior"
    })

    fig_lineas = px.line(
        df_lineas,
        x="Día del Mes",
        y="Unidades Despachadas",
        color="Periodo",
        markers=True,
        color_discrete_map={
            "Mes Actual": "#2980b9",
            "Mes Anterior": "#bdc3c7"
        },
        title=f"Evolución del Picking Diario - [{sku_filtro_sel}]"
    )

    fig_lineas.update_layout(
        xaxis=dict(tickmode="linear", dtick=1, range=[1, 31]),
        yaxis_title="Unidades Despachadas",
        xaxis_title="Día del Mes (1 al 31)",
        height=400,
        hovermode="x unified"
    )

    st.plotly_chart(fig_lineas, use_container_width=True)

    st.markdown("---")

    # --- EXPORTACIÓN DE REPORTES A EXCEL ---
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
