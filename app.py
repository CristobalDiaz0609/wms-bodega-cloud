import io
import streamlit as st
import pandas as pd
import plotly.express as px
import mysql.connector

st.set_page_config(page_title="WMS - Gestor de Bodega 2D", layout="wide")

st.title("📦 Sistema WMS - Gestión e Inventario Físico 2D")
st.caption("Conectado en tiempo real a MySQL Local")

# -----------------------------------------------------------------------------
# 1. FUNCIONES DE CONEXIÓN Y BASE DE DATOS
# -----------------------------------------------------------------------------
def obtener_conexion():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="Bosterjack1",  # <-- PON TU CLAVE DE MYSQL WORKBENCH
        database="wms_bodega"
    )

def cargar_datos_bodega():
    conn = obtener_conexion()
    query = """
    SELECT 
        u.id_ubicacion AS Ubicacion_ID,
        z.nombre AS Zona,
        u.coord_x AS X,
        u.coord_y AS Y,
        u.estado AS Estado,
        COALESCE(i.sku, 'N/A') AS SKU,
        COALESCE(p.nombre, 'Vacío') AS Producto,
        COALESCE(p.capacidad_por_casilla, 0) AS Capacidad_Max_SKU,
        COALESCE(i.cantidad, 0) AS Cantidad_Actual
    FROM ubicaciones u
    JOIN zonas z ON u.id_zona = z.id_zona
    LEFT JOIN inventario i ON u.id_ubicacion = i.id_ubicacion
    LEFT JOIN productos p ON i.sku = p.sku;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def obtener_productos_con_stock():
    conn = obtener_conexion()
    query = """
    SELECT 
        p.sku, 
        p.nombre, 
        p.categoria, 
        p.unidad_medida, 
        p.capacidad_por_casilla,
        COALESCE(SUM(i.cantidad), 0) AS stock_total
    FROM productos p
    LEFT JOIN inventario i ON p.sku = i.sku
    GROUP BY p.sku, p.nombre, p.categoria, p.unidad_medida, p.capacidad_por_casilla;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def cargar_historial():
    conn = obtener_conexion()
    query = """
    SELECT 
        h.id_movimiento AS ID,
        h.fecha_hora AS 'Fecha y Hora',
        h.tipo_movimiento AS 'Tipo Operación',
        h.sku AS SKU,
        p.nombre AS Producto,
        h.id_ubicacion AS Ubicación,
        h.cantidad AS Cantidad
    FROM historial_movimientos h
    LEFT JOIN productos p ON h.sku = p.sku
    ORDER BY h.fecha_hora DESC;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def registrar_ingreso(id_ubicacion, sku, cantidad):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id_inventario, cantidad FROM inventario WHERE id_ubicacion = %s AND sku = %s",
            (id_ubicacion, sku)
        )
        existente = cursor.fetchone()

        if existente:
            nueva_cant = existente[1] + cantidad
            cursor.execute(
                "UPDATE inventario SET cantidad = %s WHERE id_inventario = %s",
                (nueva_cant, existente[0])
            )
        else:
            cursor.execute(
                "INSERT INTO inventario (id_ubicacion, sku, cantidad) VALUES (%s, %s, %s)",
                (id_ubicacion, sku, cantidad)
            )

        cursor.execute(
            "UPDATE ubicaciones SET estado = 'Ocupado' WHERE id_ubicacion = %s",
            (id_ubicacion,)
        )

        cursor.execute(
            "INSERT INTO historial_movimientos (tipo_movimiento, sku, id_ubicacion, cantidad) VALUES ('ENTRADA', %s, %s, %s)",
            (sku, id_ubicacion, cantidad)
        )

        conn.commit()
        st.success(f"✅ ¡Ingreso exitoso! Se añadieron {cantidad} un. de {sku} a {id_ubicacion}.")
    except Exception as e:
        conn.rollback()
        st.error(f"Error al registrar ingreso: {e}")
    finally:
        conn.close()

def procesar_despacho_pedido(sku, cantidad_solicitada):
    conn = obtener_conexion()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT i.id_inventario, i.id_ubicacion, i.cantidad
            FROM inventario i
            WHERE i.sku = %s AND i.cantidad > 0
            ORDER BY i.cantidad ASC
        """, (sku,))
        filas = cursor.fetchall()

        por_retirar = cantidad_solicitada
        retiros = []

        for f in filas:
            if por_retirar <= 0:
                break
            cant_a_sacar = min(f['cantidad'], por_retirar)
            nueva_cant = f['cantidad'] - cant_a_sacar
            por_retirar -= cant_a_sacar

            retiros.append((f['id_inventario'], f['id_ubicacion'], cant_a_sacar, nueva_cant))

        for id_inv, id_ub, cant_sacar, nueva_cant in retiros:
            if nueva_cant == 0:
                cursor.execute("DELETE FROM inventario WHERE id_inventario = %s", (id_inv,))
                cursor.execute("UPDATE ubicaciones SET estado = 'Libre' WHERE id_ubicacion = %s", (id_ub,))
            else:
                cursor.execute("UPDATE inventario SET cantidad = %s WHERE id_inventario = %s", (nueva_cant, id_inv))

            cursor.execute(
                "INSERT INTO historial_movimientos (tipo_movimiento, sku, id_ubicacion, cantidad) VALUES ('DESPACHO', %s, %s, %s)",
                (sku, id_ub, cant_sacar)
            )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al procesar pedido: {e}")
        return False
    finally:
        conn.close()

def convertir_df_a_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()

# -----------------------------------------------------------------------------
# 2. CARGA DE DATOS Y ESTRUCTURA DE 3 PÁGINAS
# -----------------------------------------------------------------------------
try:
    df_bodega = cargar_datos_bodega()
    df_productos = obtener_productos_con_stock()
    lista_productos = df_productos.to_dict('records')

    dict_prods = {p['sku']: p for p in lista_productos}
    opciones_prod = {f"{p['sku']} - {p['nombre']}": p['sku'] for p in lista_productos}

    tab_operativa, tab_analitica, tab_info = st.tabs([
        "🗺️ Operación y Mapa 2D", 
        "📊 KPIs y Trazabilidad", 
        "ℹ️ Información y Parámetros"
    ])

    # =========================================================================
    # PÁGINA 1: OPERACIÓN Y MAPA 2D
    # =========================================================================
    with tab_operativa:
        with st.expander("🛒 **MÓDULO DE PEDIDOS: BUSCAR DÓNDE RETIRAR PRODUCTOS**", expanded=False):
            col_p1, col_p2, col_p3 = st.columns([2, 1, 1])

            with col_p1:
                prod_pedido_str = st.selectbox("Seleccionar Producto Requerido:", list(opciones_prod.keys()), key="p_prod")
                sku_pedido = opciones_prod[prod_pedido_str]

            with col_p2:
                cant_pedido = st.number_input("Cantidad Requerida:", min_value=1, value=1, step=1, key="p_cant")

            with col_p3:
                st.write(" ")
                st.write(" ")
                btn_buscar_ruta = st.button("🔍 Buscar Dónde Ir", use_container_width=True)

            df_stock_prod = df_bodega[df_bodega["SKU"] == sku_pedido]
            total_stock = df_stock_prod["Cantidad_Actual"].sum()

            if btn_buscar_ruta or st.session_state.get("ver_ruta"):
                st.session_state["ver_ruta"] = True

                if total_stock < cant_pedido:
                    st.error(f"❌ Stock Insuficiente: Se solicitan {cant_pedido} un., pero solo hay {int(total_stock)} un. disponibles.")
                else:
                    st.success(f"📍 **HOJA DE RUTA ENCONTRADA:** Para retirar {cant_pedido} un. de {sku_pedido}, dirígete a:")

                    df_disponibles = df_stock_prod[df_stock_prod["Cantidad_Actual"] > 0].sort_values(by="Cantidad_Actual", ascending=True)

                    por_sacar = cant_pedido
                    hoja_ruta = []

                    for _, row in df_disponibles.iterrows():
                        if por_sacar <= 0:
                            break
                        sacar = min(row["Cantidad_Actual"], por_sacar)
                        por_sacar -= sacar
                        hoja_ruta.append({
                            "Paso": len(hoja_ruta) + 1,
                            "Zona": row["Zona"],
                            "Ubicación / Casilla": row["Ubicacion_ID"],
                            "Coordenada X (Fila)": int(row["X"]),
                            "Coordenada Y (Pasillo/Nivel)": int(row["Y"]),
                            "Retirar (Unidades)": int(sacar),
                            "Quedan en Casilla": int(row["Cantidad_Actual"] - sacar)
                        })

                    df_ruta = pd.DataFrame(hoja_ruta)
                    st.dataframe(df_ruta, use_container_width=True)

                    c_conf1, c_conf2 = st.columns([1, 3])
                    with c_conf1:
                        if st.button("📦 Confirmar Retiro de Bodega", type="primary", use_container_width=True):
                            if procesar_despacho_pedido(sku_pedido, cant_pedido):
                                st.balloons()
                                st.success("🎉 ¡Pedido completado y movimiento registrado en el historial!")
                                st.session_state["ver_ruta"] = False
                                st.rerun()

        st.divider()

        # Barra Lateral
        st.sidebar.header("🔍 Filtro de Visualización")
        zona_seleccionada = st.sidebar.selectbox("Selecciona la Zona:", df_bodega["Zona"].unique())
        busqueda = st.sidebar.text_input("Buscar en Mapa (Producto/SKU):")

        st.sidebar.divider()
        st.sidebar.header("📥 Entrada / Recepción")

        opciones_prod_ingreso = {f"{p['sku']} - {p['nombre']} (Máx {p['capacidad_por_casilla']} un)": p['sku'] for p in lista_productos}
        prod_ingreso_str = st.sidebar.selectbox("Producto a Ingresar:", list(opciones_prod_ingreso.keys()))
        sku_ingreso = opciones_prod_ingreso[prod_ingreso_str]
        capacidad_limite = dict_prods[sku_ingreso]['capacidad_por_casilla']

        cant_ingreso = st.sidebar.number_input("Cantidad a Ingresar:", min_value=1, max_value=capacidad_limite, value=1, step=1)

        opciones_casillas = {}
        for _, row in df_bodega.iterrows():
            if row["Estado"] == "Libre":
                if cant_ingreso <= capacidad_limite:
                    label = f"{row['Ubicacion_ID']} (Libre - Capacidad: 0/{capacidad_limite})"
                    opciones_casillas[label] = row['Ubicacion_ID']
            elif row["SKU"] == sku_ingreso:
                espacio_restante = capacidad_limite - row["Cantidad_Actual"]
                if cant_ingreso <= espacio_restante:
                    label = f"{row['Ubicacion_ID']} (Ocupada - Actual: {row['Cantidad_Actual']}/{capacidad_limite})"
                    opciones_casillas[label] = row['Ubicacion_ID']

        with st.sidebar.form("form_ingreso", clear_on_submit=False):
            if opciones_casillas:
                ub_destino_str = st.selectbox("Casillas Válidas:", list(opciones_casillas.keys()))
                submit_btn = st.form_submit_button("🚀 Cargar a Ubicación")

                if submit_btn:
                    ub_destino = opciones_casillas[ub_destino_str]
                    registrar_ingreso(ub_destino, sku_ingreso, cant_ingreso)
                    st.rerun()
            else:
                st.warning(f"⚠️ No hay casillas con espacio para ingresar {cant_ingreso} un.")
                st.form_submit_button("🚀 Cargar a Ubicación", disabled=True)

        # Mapa 2D
        df_zona = df_bodega[df_bodega["Zona"] == zona_seleccionada].copy()

        st.subheader(f"🗺️ Mapa Físico - {zona_seleccionada}")
        color_map = {"Libre": "#2ecc71", "Ocupado": "#e74c3c", "Inhabilitado": "#95a5a6"}

        if busqueda:
            df_zona["Coincide"] = df_zona["Producto"].str.contains(busqueda, case=False) | df_zona["SKU"].str.contains(busqueda, case=False)
            df_zona["Color_Visual"] = df_zona.apply(
                lambda r: "#f1c40f" if r["Coincide"] and r["Estado"] == "Ocupado" else color_map.get(r["Estado"], "#2ecc71"), axis=1
            )
        else:
            df_zona["Color_Visual"] = df_zona["Estado"].map(color_map)

        fig = px.scatter(
            df_zona,
            x="X",
            y="Y",
            color="Color_Visual",
            color_discrete_map="identity",
            text="Ubicacion_ID",
            hover_data=["Producto", "SKU", "Cantidad_Actual", "Capacidad_Max_SKU", "Estado"],
            size_max=40,
        )

        fig.update_traces(
            marker=dict(size=35, symbol="square", line=dict(width=2, color="DarkSlateGrey")),
            textposition="top center"
        )

        fig.update_layout(
            xaxis=dict(title="Estante / Fila (X)", dtick=1),
            yaxis=dict(title="Pasillo / Nivel (Y)", dtick=1),
            height=400,
            showlegend=False
        )

        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        st.subheader("📋 Detalle de Inventario Físico")
        st.dataframe(
            df_zona[["Ubicacion_ID", "Estado", "SKU", "Producto", "Cantidad_Actual", "Capacidad_Max_SKU"]],
            use_container_width=True
        )

    # =========================================================================
    # PÁGINA 2: ANALÍTICA, KPIS Y TRAZABILIDAD (KÁRDEX)
    # =========================================================================
    with tab_analitica:
        st.subheader("📊 Indicadores Clave de Desempeño (KPIs)")

        total_casillas = len(df_bodega["Ubicacion_ID"].unique())
        casillas_ocupadas = len(df_bodega[df_bodega["Estado"] == "Ocupado"]["Ubicacion_ID"].unique())
        casillas_libres = total_casillas - casillas_ocupadas
        
        pct_casillas_ocupadas = (casillas_ocupadas / total_casillas * 100) if total_casillas > 0 else 0

        capacidad_total_unidades = df_bodega["Capacidad_Max_SKU"].sum()
        unidades_actuales = df_bodega["Cantidad_Actual"].sum()
        pct_ocupacion_bodega = (unidades_actuales / capacidad_total_unidades * 100) if capacidad_total_unidades > 0 else 0

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(
            "Ocupación de Casillas", 
            f"{pct_casillas_ocupadas:.1f}%", 
            f"{casillas_ocupadas}/{total_casillas} Módulos Utilizados"
        )
        kpi2.metric(
            "Ocupación de Bodega", 
            f"{pct_ocupacion_bodega:.1f}%", 
            f"{int(unidades_actuales)}/{int(capacidad_total_unidades)} Unidades Soportadas"
        )
        kpi3.metric("Casillas Libres", f"{casillas_libres}")
        kpi4.metric("Total Unidades Stock", f"{int(unidades_actuales)} un.")

        st.divider()

        df_stock_prod_graf = df_bodega[df_bodega["Cantidad_Actual"] > 0].groupby("Producto")["Cantidad_Actual"].sum().reset_index()

        if not df_stock_prod_graf.empty:
            col_g1, col_g2 = st.columns([1, 1])
            with col_g1:
                fig_pie = px.pie(
                    df_stock_prod_graf,
                    values="Cantidad_Actual",
                    names="Producto",
                    title="📈 Distribución de Stock por Producto",
                    hole=0.4
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_g2:
                fig_bar = px.bar(
                    df_stock_prod_graf,
                    x="Producto",
                    y="Cantidad_Actual",
                    title="📦 Stock Total por Categoría/Producto",
                    labels={"Cantidad_Actual": "Unidades"},
                    color="Producto"
                )
                st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        st.subheader("📜 Historial de Trazabilidad (Kárdex)")
        df_historial = cargar_historial()
        if not df_historial.empty:
            st.dataframe(df_historial, use_container_width=True)
        else:
            st.info("Aún no se han registrado movimientos de inventario.")

    # =========================================================================
    # PÁGINA 3: INFORMACIÓN, MANUAL, CATÁLOGO CON STOCK Y EXPORTACIÓN
    # =========================================================================
    with tab_info:
        st.header("ℹ️ Información del Sistema y Parámetros de Bodega")
        st.write("Guía operativa, exportación de reportes y catálogo general con stock en tiempo real.")

        col_inf1, col_inf2 = st.columns([1, 1])

        with col_inf1:
            st.subheader("📘 Manual de Usuario")
            st.markdown("""
            * **1. Recepción e Ingreso:** Selecciona el producto e ingresa unidades a través de la barra lateral.
            * **2. Preparación de Pedidos:** Genera hojas de ruta optimizadas con coordenadas físicas `(X, Y)`.
            * **3. Trazabilidad:** Monitorea entradas y salidas auditadas por fecha y hora en tiempo real.
            """)

        with col_inf2:
            st.subheader("📥 Exportación de Datos en Excel")
            df_historial_exp = cargar_historial()
            
            tipo_reporte = st.selectbox(
                "Selecciona el reporte que deseas descargar:",
                ["Inventario Físico Actual", "Historial de Trazabilidad (Kárdex)", "Catálogo General de Productos"]
            )

            if tipo_reporte == "Inventario Físico Actual":
                df_exportar = df_bodega
                nombre_archivo = "Reporte_Inventario_Fisico.xlsx"
            elif tipo_reporte == "Historial de Trazabilidad (Kárdex)":
                df_exportar = df_historial_exp
                nombre_archivo = "Reporte_Historial_Kardex.xlsx"
            else:
                df_exportar = df_productos
                nombre_archivo = "Reporte_Catalogo_Productos.xlsx"

            bytes_excel = convertir_df_a_excel(df_exportar)

            st.download_button(
                label=f"🟢 Descargar {tipo_reporte} (.xlsx)",
                data=bytes_excel,
                file_name=nombre_archivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

        st.divider()

        st.subheader("📦 Catálogo Oficial de Productos y Stock Disponible")
        df_prods_mostrar = df_productos.rename(columns={
            "sku": "SKU",
            "nombre": "Nombre Producto",
            "categoria": "Categoría",
            "unidad_medida": "Unidad",
            "capacidad_por_casilla": "Capacidad Máx/Casilla",
            "stock_total": "Stock Total en Bodega"
        })
        st.dataframe(df_prods_mostrar, use_container_width=True)

except Exception as e:
    st.error(f"⚠️ Error de conexión o ejecución en MySQL: {e}")