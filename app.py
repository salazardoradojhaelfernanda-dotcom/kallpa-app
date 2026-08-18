import streamlit as st
import pandas as pd
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import re
import rapidfuzz
from rapidfuzz import fuzz, process

# --------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA (para que se vea bien en el celular)
# --------------------------------------------
st.set_page_config(page_title="Kallpa - Cuaderno a Excel", layout="centered", initial_sidebar_state="collapsed")

# Título y diseño bonito
st.title("📸 Kallpa")
st.markdown("### De la foto de tu cuaderno al Excel en 2 minutos")

# --------------------------------------------
# INICIALIZAR LA "MEMORIA" DE LA APP (para guardar los cursos)
# --------------------------------------------
if "cursos" not in st.session_state:
    st.session_state.cursos = {}  # Aquí guardamos los Excels subidos

if "curso_actual" not in st.session_state:
    st.session_state.curso_actual = ""

# --------------------------------------------
# PASO 1: SELECCIONAR O CREAR CURSO
# --------------------------------------------
nombre_curso = st.text_input("📚 Nombre del Curso (ej: Matemáticas 1A)", value=st.session_state.curso_actual)

if nombre_curso:
    st.session_state.curso_actual = nombre_curso

# --------------------------------------------
# PASO 2: SUBIR LA PLANTILLA EXCEL (Solo 1 vez por curso)
# --------------------------------------------
st.divider()
st.subheader("📂 1. Sube tu plantilla Excel (con los nombres de tus alumnos)")

# Verificamos si ya subimos este curso antes
if nombre_curso in st.session_state.cursos:
    st.success(f"✅ Plantilla '{nombre_curso}' ya cargada. {len(st.session_state.cursos[nombre_curso])} alumnos listos.")
    df_template = st.session_state.cursos[nombre_curso]
else:
    template_file = st.file_uploader("Sube tu archivo .xlsx", type=["xlsx", "xls"])
    if template_file:
        df_template = pd.read_excel(template_file)
        st.session_state.cursos[nombre_curso] = df_template
        st.success(f"✅ Plantilla '{nombre_curso}' cargada correctamente.")
        st.dataframe(df_template.head(3))
    else:
        st.warning("Esperando la plantilla...")
        st.stop()  # No continuar si no hay plantilla

# --------------------------------------------
# PASO 3: SUBIR LA FOTO DEL CUADERNO
# --------------------------------------------
st.divider()
st.subheader("📸 2. Toma una foto de tu cuaderno")

img_file = st.file_uploader("Sube la imagen (JPG o PNG)", type=["jpg", "jpeg", "png"])

# --------------------------------------------
# PROCESAR LA IMAGEN Y EL OCR (Cuando el profe presiona el botón)
# --------------------------------------------
if img_file and st.button("🚀 Extraer Notas de la Foto"):
    with st.spinner("Kallpa está leyendo tu cuaderno... (15 segundos)"):
        
        # --- 1. Limpiar la imagen con OpenCV ---
        image = Image.open(img_file)
        img_array = np.array(image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        # Aumentar contraste y quitar rayaduras del cuaderno
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10)
        
        # --- 2. OCR (Lectura de texto) ---
        # Configuración especial para leer números y letras
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:- '
        raw_text = pytesseract.image_to_string(thresh, config=custom_config)
        
        # --- 3. Inteligencia: Ordenar el texto ---
        lineas = raw_text.split('\n')
        datos_crudos = []
        
        for linea in lineas:
            linea = linea.strip()
            # Busca patrones: "Nombre Apellido 85" o "Nombre 7.5"
            # La nota debe estar al final de la línea
            match = re.search(r'([a-zA-ZáéíóúñÁÉÍÓÚÑ\s]+)\s+([0-9]+(?:\.[0-9])?)$', linea)
            if match:
                nombre_ocr = match.group(1).strip()
                nota_ocr = match.group(2).strip()
                datos_crudos.append({"nombre_ocr": nombre_ocr, "nota_ocr": nota_ocr})
        
        if not datos_crudos:
            st.error("😅 No pude leer números en esta foto. ¿Está muy borrosa o tiene mucho rayado?")
            st.stop()
        
        # --- 4. Emparejar con el Excel (Fuzzy Matching) ---
        # Sacamos los nombres de la plantilla para comparar
        col_nombre_excel = df_template.columns[0]  # Asumimos que la 1ra columna tiene nombres
        nombres_excel = df_template[col_nombre_excel].astype(str).tolist()
        
        # Buscamos una columna vacía para poner las notas (o la creamos)
        col_nota_excel = None
        for col in df_template.columns:
            if df_template[col].isnull().all():
                col_nota_excel = col
                break
        if col_nota_excel is None:
            col_nota_excel = "Nota_Importada"
            df_template[col_nota_excel] = None
        
        # Hacemos el cruce de datos
        resultados = []
        for item in datos_crudos:
            nombre_buscado = item["nombre_ocr"]
            nota_buscada = item["nota_ocr"]
            
            # Buscar el mejor match en la lista del Excel
            match = process.extractOne(nombre_buscado, nombres_excel, scorer=fuzz.token_sort_ratio)
            
            if match and match[1] >= 70:  # Si coincide al 70% o más
                idx = nombres_excel.index(match[0])
                nombre_exacto = match[0]
                # Guardamos la fila y la nota sugerida
                resultados.append({
                    "Nombre en Excel": nombre_exacto,
                    "Nota Detectada": nota_buscada,
                    "Coincidencia": f"{match[1]}%",
                    "Fila": idx
                })
            else:
                # Si no encontró match, lo dejamos en rojo para que el profe decida
                resultados.append({
                    "Nombre en Excel": "⚠️ NO ENCONTRADO",
                    "Nota Detectada": nota_buscada,
                    "Coincidencia": "0%",
                    "Fila": -1
                })
        
        # --- 5. Mostrar tabla EDITABLE para revisión humana ---
        st.divider()
        st.subheader("✏️ 3. Revisa y corrige las notas (si es necesario)")
        
        df_resultados = pd.DataFrame(resultados)
        
        # Mostrar la tabla editable
        df_editado = st.data_editor(
            df_resultados,
            column_config={
                "Nota Detectada": "Nota (puedes cambiarla)",
                "Coincidencia": st.column_config.TextColumn("Confianza", width="small"),
            },
            hide_index=True,
            num_rows="fixed"
        )
        
        # --- 6. Volcar los datos al Excel original ---
        if st.button("✅ Confirmar y Descargar Excel Actualizado"):
            # Recorremos las filas editadas
            for _, row in df_editado.iterrows():
                if row["Fila"] != -1:  # Si encontramos la fila
                    idx = row["Fila"]
                    df_template.at[idx, col_nota_excel] = row["Nota Detectada"]
            
            # Guardar el Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_template.to_excel(writer, index=False, sheet_name="Calificaciones")
            
            output.seek(0)
            
            # Botón de descarga
            st.success("✅ ¡Excel generado! Revisa que todo esté bien y descárgalo.")
            st.download_button(
                label="📥 Descargar Excel (Listo para Secretaría)",
                data=output.getvalue(),
                file_name=f"Kallpa_{nombre_curso}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
