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
# CREDENCIALES Y ROLES DE ACCESO
# USUARIO : {"password": "...", "rol": "admin" o "operario"}
# ---------------------------------------------------------
USUARIOS_PERMITIDOS = {
    "admin": {"password": "admin2026", "rol": "admin"},
    "cristobal": {"password": "wms2026", "rol": "admin"},
    "operador1": {"password": "bodega123", "rol": "operario"},
    "operador2": {"password": "bodega456", "rol": "operario"},
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
            st.session_state.rol_actual = USUARIOS_PERMITIDOS[usuario_input][
                "rol"
            ]
            st.sidebar.success(f"¡Bienvenido, {usuario_input}!")
            st.rerun()
        else:
            st.sidebar.error("❌ Usuario o contraseña incorrectos.")


def logout():
    st.session_state.autenticado = False
    st.session_state.usuario_actual = ""
    st.session_state.rol_actual = ""
    st.session_state.hoja_ruta_persistente = None
    st.session_state.distancia_total_persistente = None
    st.session_state.operaciones_pendientes_picking = []
    st.rerun()


# ---------------------------------------------------------
# SI NO ESTÁ AUTENTICADO, MOSTRAR PANTALLA DE LOGIN Y BLOQUEAR
# ---------------------------------------------------------
if not st.session_state.autenticado:
    login()
    st.title("📦 Sistema de Gestión de Bodega (WMS 2D)")
    st.info(
        "👈 Por favor, ingresa tus credenciales en la barra lateral para acceder"
        " al sistema."
    )

else:
    # Muestra usuario activo y su rol asignado
    rol_label = (
        "👑 Administrador"
        if st.session_state.rol_actual == "admin"
        else "👷 Operario"
    )
    st.sidebar.markdown(f"👤 **Usuario:** `{st.session_state.usuario_actual}`")
    st.sidebar.markdown(f"🏷️ **Rol:** `{rol_label}`")

    if st.sidebar.button("🚪 Cerrar Sesión"):
        logout()

    st.sidebar.markdown("---")

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
    # INTERFAZ Y NAVEGACIÓN SEGÚN EL ROL
    # ---------------------------------------------------------
    st.title("📦 Sistema de Gestión de Bodega (WMS 2D)")

    # Definir módulos según el rol asignado
    if st.session_state.rol_actual == "admin":
        modulos_disponibles = [
            "🗺️ Mapa 2D & Estado",
            "📥 Recepción e Ingreso",
            "🛒 Picking / Despacho",
            "📊 Dashboard & KPIs",
            "📜 Historial Kárdex",
            "🏷️ Generador de Etiquetas QR",
        ]
    else:
        # Operario: Solo los 3 primeros y el de etiquetas QR
        modulos_disponibles = [
            "🗺️ Mapa 2D & Estado",
            "📥 Recepción e Ingreso",
            "🛒 Picking / Despacho",
            "🏷️ Generador de Etiquetas QR",
        ]

    menu = st.sidebar.radio("Navegación / Módulos", modulos_disponibles)

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
    # 2. RECEPCIÓN E INGRESO DE MERCADERÍA
    # ---------------------------------------------------------
    elif menu == "📥 Recepción e Ingreso":
        st.header("Ingreso de Stock a Bodega")

        df_prods = obtener_df(
            "SELECT sku, nombre, capacidad_por_casilla FROM productos"
        )

        if df_prods.empty:
            st.warning(
                "Asegúrate de tener productos registrados en el sistema."
            )
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
                            "SELECT id_inventario, cantidad FROM inventario"
                            " WHERE id_ubicacion = %s",
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
                            "INSERT INTO historial_movimientos"
                            " (tipo_movimiento, sku, id_ubicacion, cantidad)"
                            " VALUES ('ENTRADA', %s, %s, %s)",
                            (sku_limpio, ubi_limpia, cantidad_ingreso),
                        )

                        st.success(
                            f"✅ Se ingresaron {cantidad_ingreso} unidades de"
                            f" {sku_limpio} en la casilla {ubi_limpia}."
                        )
                        st.rerun()

    # ---------------------------------------------------------
    # 3. PICKING / DESPACHO DE PEDIDOS
    # ---------------------------------------------------------
    elif menu == "🛒 Picking / Despacho":
        st.header("Motor de Picking y Despacho Multi-SKU (Ruta Óptima 2D)")

        if "hoja_ruta_persistente" not in st.session_state:
            st.session_state.hoja_ruta_persistente = None
        if "distancia_total_persistente" not in st.session_state:
            st.session_state.distancia_total_persistente = None
        if "operaciones_pendientes_picking" not in st.session_state:
            st.session_state.operaciones_pendientes_picking = []

        df_inv = obtener_df("""
            SELECT i.sku, p.nombre, SUM(i.cantidad) as total_disponible
            FROM inventario i
            JOIN productos p ON i.sku = p.sku
            GROUP BY i.sku, p.nombre
        """)

        if df_inv.empty:
            st.info(
                "No hay inventario disponible en la bodega para realizar"
                " despachos."
            )
        else:
            st.subheader("1. Selección de Productos para el Pedido")

            df_inv["opcion_display"] = (
                df_inv["sku"]
                + " - "
                + df_inv["nombre"]
                + " (Stock: "
                + df_inv["total_disponible"].astype(str)
                + ")"
            )

            skus_seleccionados = st.multiselect(
                "Seleccionar Producto(s) a Despachar", df_inv["opcion_display"]
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
                        max_disp = int(
                            df_inv[df_inv["sku"] == sku_clean][
                                "total_disponible"
                            ].values[0]
                        )

                        with cols[idx % 3]:
                            st.markdown(f"**{sku_clean}** - {nombre_prod}")
                            cant = st.number_input(
                                f"Cantidad (Máx: {max_disp})",
                                min_value=1,
                                max_value=max_disp,
                                value=1,
                                key=f"cant_{sku_clean}",
                            )
                            cantidades_solicitadas[sku_clean] = cant

                    btn_generar_ruta = st.form_submit_button(
                        "🚀 Generar Hoja de Ruta Óptima"
                    )

                    if btn_generar_ruta:
                        puntos_extraccion = []
                        operaciones_db = []

                        for (
                            sku_clean,
                            cant_solicitada,
                        ) in cantidades_solicitadas.items():
                            df_casillas = obtener_df(
                                """
                                SELECT i.id_inventario, i.id_ubicacion, i.cantidad, u.coord_x, u.coord_y
                                FROM inventario i
                                JOIN ubicaciones u ON i.id_ubicacion = u.id_ubicacion
                                WHERE i.sku = %s
                                ORDER BY i.cantidad ASC
                            """,
                                (sku_clean,),
                            )

                            por_despachar = cant_solicitada

                            for _, row in df_casillas.iterrows():
                                if por_despachar <= 0:
                                    break

                                id_inv = row["id_inventario"]
                                ubi = row["id_ubicacion"]
                                cant_en_casilla = row["cantidad"]
                                cx = row["coord_x"]
                                cy = row["coord_y"]

                                if cant_en_casilla <= por_despachar:
                                    despacho_casilla = cant_en_casilla
                                    operaciones_db.append({
                                        "tipo": "DELETE",
                                        "id_inventario": id_inv,
                                        "id_ubicacion": ubi,
                                        "sku": sku_clean,
                                        "cantidad": despacho_casilla,
                                    })
                                else:
                                    despacho_casilla = por_despachar
                                    nueva_cant = cant_en_casilla - por_despachar
                                    operaciones_db.append({
                                        "tipo": "UPDATE",
                                        "id_inventario": id_inv,
                                        "nueva_cantidad": nueva_cant,
                                        "id_ubicacion": ubi,
                                        "sku": sku_clean,
                                        "cantidad": despacho_casilla,
                                    })

                                por_despachar -= despacho_casilla
                                puntos_extraccion.append({
                                    "SKU": sku_clean,
                                    "Ubicación": ubi,
                                    "Extraer": despacho_casilla,
                                    "x": cx,
                                    "y": cy,
                                })

                        pos_actual = (0, 0)
                        ruta_ordenada = []
                        distancia_total = 0.0

                        pendientes = puntos_extraccion.copy()
                        paso = 1

                        while pendientes:
                            mejor_idx = 0
                            menor_dist = abs(
                                pendientes[0]["x"] - pos_actual[0]
                            ) + abs(pendientes[0]["y"] - pos_actual[1])

                            for i in range(1, len(pendientes)):
                                dist = abs(
                                    pendientes[i]["x"] - pos_actual[0]
                                ) + abs(pendientes[i]["y"] - pos_actual[1])
                                if dist < menor_dist:
                                    menor_dist = dist
                                    mejor_idx = i

                            siguiente_punto = pendientes.pop(mejor_idx)
                            distancia_total += menor_dist
                            pos_actual = (
                                siguiente_punto["x"],
                                siguiente_punto["y"],
                            )

                            siguiente_punto["Paso"] = paso
                            siguiente_punto["Dist. Tramo (m)"] = menor_dist
                            ruta_ordenada.append(siguiente_punto)
                            paso += 1

                        df_hoja_ruta = pd.DataFrame(ruta_ordenada)
                        if not df_hoja_ruta.empty:
                            df_hoja_ruta = df_hoja_ruta[[
                                "Paso",
                                "Ubicación",
                                "SKU",
                                "Extraer",
                                "Dist. Tramo (m)",
                                "x",
                                "y",
                            ]]

                        st.session_state.hoja_ruta_persistente = df_hoja_ruta
                        st.session_state.distancia_total_persistente = (
                            distancia_total
                        )
                        st.session_state.operaciones_pendientes_picking = (
                            operaciones_db
                        )
                        st.info(
                            "📋 Ruta generada exitosamente. Revisa la ruta y"
                            " presiona 'Confirmar y Finalizar' para descontar"
                            " del inventario."
                        )
                        st.rerun()

            if st.session_state.hoja_ruta_persistente is not None:
                st.markdown("---")
                st.subheader("📋 Hoja de Ruta Activa para Operador:")

                st.info(
                    "📏 **Distancia Total Recorrida Estimada:**"
                    f" {st.session_state.distancia_total_persistente:.1f}"
                    " metros/unidades (Punto de inicio: Puerta (0,0))"
                )
                st.dataframe(
                    st.session_state.hoja_ruta_persistente,
                    use_container_width=True,
                )

                col_btn1, col_btn2 = st.columns(2)

                with col_btn1:
                    if st.button(
                        "❌ Cancelar / Limpiar Ruta (Sin Descontar Stock)",
                        use_container_width=True,
                    ):
                        st.session_state.hoja_ruta_persistente = None
                        st.session_state.distancia_total_persistente = None
                        st.session_state.operaciones_pendientes_picking = []
                        st.warning(
                            "⚠️ Ruta cancelada. El inventario no sufrió"
                            " modificaciones."
                        )
                        st.rerun()

                with col_btn2:
                    if st.button(
                        "✅ Confirmar y Finalizar Picking (Descontar Stock)",
                        type="primary",
                        use_container_width=True,
                    ):
                        if st.session_state.operaciones_pendientes_picking:
                            for (
                                op
                            ) in (
                                st.session_state.operaciones_pendientes_picking
                            ):
                                if op["tipo"] == "DELETE":
                                    ejecutar_query(
                                        "DELETE FROM inventario WHERE"
                                        " id_inventario = %s",
                                        (op["id_inventario"],),
                                    )
                                    ejecutar_query(
                                        "UPDATE ubicaciones SET estado ="
                                        " 'Libre' WHERE id_ubicacion = %s",
                                        (op["id_ubicacion"],),
                                    )
                                elif op["tipo"] == "UPDATE":
                                    ejecutar_query(
                                        "UPDATE inventario SET cantidad = %s"
                                        " WHERE id_inventario = %s",
                                        (
                                            op["nueva_cantidad"],
                                            op["id_inventario"],
                                        ),
                                    )

                                ejecutar_query(
                                    "INSERT INTO historial_movimientos"
                                    " (tipo_movimiento, sku, id_ubicacion,"
                                    " cantidad) VALUES ('DESPACHO', %s, %s,"
                                    " %s)",
                                    (op["sku"], op["id_ubicacion"], op["cantidad"]),
                                )

                        st.session_state.hoja_ruta_persistente = None
                        st.session_state.distancia_total_persistente = None
                        st.session_state.operaciones_pendientes_picking = []
                        st.success(
                            "🎉 ¡Picking confirmado con éxito! El inventario ha"
                            " sido actualizado."
                        )
                        st.rerun()

    # ---------------------------------------------------------
    # 4. DASHBOARD & KPIS (EXCLUSIVO ADMIN)
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

        total_skus = obtener_df("SELECT COUNT(*) as t FROM productos")[
            "t"
        ].values[0]

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

        st.markdown("---")
        st.subheader("🛒 Rendimiento de Picking / Despachos")
        col_p1, col_p2, col_p3 = st.columns(3)

        col_p1.metric(
            label="Picking Mes Actual",
            value=f"{picking_mes_actual} Unidades",
            delta=f"{delta_picking:+d} Unid. vs Mes Pasado",
        )
        col_p2.metric("Picking Mes Pasado", f"{picking_mes_pasado} Unidades")
        col_p3.metric(
            "Casillas Disponibles / Libres",
            f"{total_casillas - casillas_ocupadas}",
        )

        st.markdown("---")
        st.subheader("⚠️ Proyección y Predicción de Quiebre de Stock")

        df_stock_prods = obtener_df("""
            SELECT p.sku, p.nombre, COALESCE(SUM(i.cantidad), 0) as stock_actual
            FROM productos p
            LEFT JOIN inventario i ON p.sku = i.sku
            GROUP BY p.sku, p.nombre
        """)

        df_salidas_mes = obtener_df("""
            SELECT sku, COALESCE(SUM(cantidad), 0) as salidas_mes
            FROM historial_movimientos
            WHERE tipo_movimiento = 'DESPACHO'
              AND MONTH(fecha_hora) = MONTH(CURRENT_DATE())
              AND YEAR(fecha_hora) = YEAR(CURRENT_DATE())
            GROUP BY sku
        """)

        if not df_stock_prods.empty:
            df_quiebre = df_stock_prods.merge(
                df_salidas_mes, on="sku", how="left"
            )
            df_quiebre["salidas_mes"] = df_quiebre["salidas_mes"].fillna(0)

            dia_actual_mes = pd.Timestamp.now().day or 1

            df_quiebre["Promedio Salida Diaria"] = (
                df_quiebre["salidas_mes"] / dia_actual_mes
            ).round(2)

            def calcular_dias_restantes(row):
                if row["Promedio Salida Diaria"] <= 0:
                    return 999
                return int(row["stock_actual"] / row["Promedio Salida Diaria"])

            df_quiebre["Días para Quiebre"] = df_quiebre.apply(
                calcular_dias_restantes, axis=1
            )

            def categorizar_riesgo(dias):
                if dias <= 7:
                    return "🔴 Crítico (Reordenar ya)"
                elif dias <= 15:
                    return "🟡 Moderado"
                else:
                    return "🟢 Normal"

            df_quiebre["Estado Quiebre"] = df_quiebre["Días para Quiebre"].apply(
                categorizar_riesgo
            )

            df_display_quiebre = df_quiebre.copy()
            df_display_quiebre["Días para Quiebre"] = df_display_quiebre[
                "Días para Quiebre"
            ].astype(str)
            df_display_quiebre.loc[
                df_display_quiebre["Días para Quiebre"] == "999",
                "Días para Quiebre",
            ] = "Sin salidas recientes"

            st.dataframe(
                df_display_quiebre[[
                    "sku",
                    "nombre",
                    "stock_actual",
                    "salidas_mes",
                    "Promedio Salida Diaria",
                    "Días para Quiebre",
                    "Estado Quiebre",
                ]],
                use_container_width=True,
            )

        st.markdown("---")
        st.subheader(
            "🧊 Reporte de SKUs Sin Movimiento (Baja Rotación / Stock Inactivo)"
        )

        dias_inactivos_sel = st.slider(
            "🎚️ Seleccionar umbral de inactividad (Días sin movimiento):",
            min_value=0,
            max_value=30,
            value=0,
            step=1,
            help=(
                "Mueve la barra a 0 o 1 para ver el stock inactivo desde hoy o"
                " ayer."
            ),
        )

        df_inactivos = obtener_df(
            """
            SELECT p.sku, p.nombre,
                   COALESCE(SUM(i.cantidad), 0) AS stock_actual,
                   MAX(m.fecha_hora) AS ultima_fecha_movimiento,
                   COALESCE(DATEDIFF(CURRENT_DATE(), MAX(m.fecha_hora)), 999) AS dias_sin_movimiento
            FROM productos p
            LEFT JOIN inventario i ON p.sku = i.sku
            LEFT JOIN historial_movimientos m ON p.sku = m.sku
            GROUP BY p.sku, p.nombre
            HAVING dias_sin_movimiento >= %s AND stock_actual > 0
            ORDER BY dias_sin_movimiento DESC;
        """,
            (dias_inactivos_sel,),
        )

        if df_inactivos.empty:
            st.success(
                "✅ ¡Excelente! No hay SKUs con stock retenido e inactivo por"
                f" {dias_inactivos_sel} días o más."
            )
        else:
            st.warning(
                f"⚠️ Se encontraron **{len(df_inactivos)} SKU(s)** con stock"
                " guardado sin registrar ningún movimiento en"
                f" **{dias_inactivos_sel} días o más**."
            )

            df_inactivos_display = df_inactivos.copy()
            df_inactivos_display["ultima_fecha_movimiento"] = (
                df_inactivos_display["ultima_fecha_movimiento"]
                .astype(str)
                .replace("None", "Sin registros de movimiento")
            )
            df_inactivos_display["dias_sin_movimiento"] = df_inactivos_display[
                "dias_sin_movimiento"
            ].replace(999, "Sin movimientos registrados")

            st.dataframe(
                df_inactivos_display[[
                    "sku",
                    "nombre",
                    "stock_actual",
                    "ultima_fecha_movimiento",
                    "dias_sin_movimiento",
                ]],
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown("#### 📈 Tendencia Diaria de Picking (Días 1 al 31)")

        df_lista_skus = obtener_df("SELECT sku, nombre FROM productos")
        opciones_sku = ["Todos los SKUs"] + (
            df_lista_skus["sku"] + " - " + df_lista_skus["nombre"]
        ).tolist()

        sku_filtro_sel = st.selectbox(
            "🔍 Filtrar gráfico por SKU:", opciones_sku
        )

        if sku_filtro_sel == "Todos los SKUs":
            where_sku = ""
            params_sku = ()
        else:
            sku_clean_filtro = sku_filtro_sel.split(" - ")[0]
            where_sku = " AND sku = %s "
            params_sku = (sku_clean_filtro,)

        df_diario_actual = obtener_df(
            f"""
            SELECT DAY(fecha_hora) as dia, SUM(cantidad) as picking_actual
            FROM historial_movimientos
            WHERE tipo_movimiento = 'DESPACHO'
              AND MONTH(fecha_hora) = MONTH(CURRENT_DATE())
              AND YEAR(fecha_hora) = YEAR(CURRENT_DATE())
              {where_sku}
            GROUP BY DAY(fecha_hora)
        """,
            params_sku if where_sku else None,
        )

        df_diario_pasado = obtener_df(
            f"""
            SELECT DAY(fecha_hora) as dia, SUM(cantidad) as picking_pasado
            FROM historial_movimientos
            WHERE tipo_movimiento = 'DESPACHO'
              AND MONTH(fecha_hora) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH)
              AND YEAR(fecha_hora) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)
              {where_sku}
            GROUP BY DAY(fecha_hora)
        """,
            params_sku if where_sku else None,
        )

        df_dias = pd.DataFrame({"Día del Mes": range(1, 32)})

        df_tendencia = df_dias.merge(
            df_diario_actual,
            left_on="Día del Mes",
            right_on="dia",
            how="left",
        )
        df_tendencia = df_tendencia.merge(
            df_diario_pasado,
            left_on="Día del Mes",
            right_on="dia",
            how="left",
        )
        df_tendencia.fillna(0, inplace=True)

        df_lineas = pd.melt(
            df_tendencia,
            id_vars=["Día del Mes"],
            value_vars=["picking_actual", "picking_pasado"],
            var_name="Periodo",
            value_name="Unidades Despachadas",
        )
        df_lineas["Periodo"] = df_lineas["Periodo"].replace({
            "picking_actual": "Mes Actual",
            "picking_pasado": "Mes Anterior",
        })

        fig_lineas = px.line(
            df_lineas,
            x="Día del Mes",
            y="Unidades Despachadas",
            color="Periodo",
            markers=True,
            color_discrete_map={
                "Mes Actual": "#2980b9",
                "Mes Anterior": "#bdc3c7",
            },
            title=f"Evolución del Picking Diario - [{sku_filtro_sel}]",
        )

        fig_lineas.update_layout(
            xaxis=dict(tickmode="linear", dtick=1, range=[1, 31]),
            yaxis_title="Unidades Despachadas",
            xaxis_title="Día del Mes (1 al 31)",
            height=400,
            hovermode="x unified",
        )

        st.plotly_chart(fig_lineas, use_container_width=True)

        st.markdown("---")
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
    # 5. HISTORIAL KÁRDEX (EXCLUSIVO ADMIN)
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
            "Genera e imprime códigos QR para identificar casillas físicamente"
            " o etiquetar paletas/productos."
        )

        opcion_qr = st.radio(
            "¿Qué tipo de etiqueta deseas generar?",
            ["Ubicación / Casilla", "Producto / SKU"],
        )

        if opcion_qr == "Ubicación / Casilla":
            df_ubis = obtener_df("SELECT id_ubicacion FROM ubicaciones")
            if not df_ubis.empty:
                ubi_sel = st.selectbox(
                    "Seleccionar Casilla para Etiquetar",
                    df_ubis["id_ubicacion"],
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
