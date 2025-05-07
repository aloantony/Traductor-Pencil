# 📦 Pencil Text Manager v3.3 (Beta)

Herramienta para extraer, traducir y reemplazar cadenas de texto en prototipos `.epgz` de **Pencil Project**, manteniendo siempre el formato original (ZIP o GZIP‑TAR).

> No traduce todo, revisar.

---

## ⚙️ Requisitos

* **Python 3.10–3.12** instalado.
* Paquete de traducción automática:

  ```bash
  pip install googletrans==4.0.0-rc1
  ```
---

## 🚀 Uso por **doble click** (Windows)
1. Coloca `pencilTextManager.py` en la misma carpeta donde esté tu único archivo `.epgz`.
2. Asegúrate de que la extensión `.py` esté asociada con tu intérprete de Python (click derecho -> abrir con... Python).
3. Haz **doble click** sobre `pencilTextManager.py`.
4. La consola mostrará:
 1. **Paso 1/3**: extracción de textos → `texts.csv`
 2. **Paso 2/3**: traducción automática → `texts_translated.csv`
 3. **Paso 3/3**: reemplazo y reempaquetado → `<nombre>_EN.epgz`
5. Cuando termine, la ventana esperará **Enter** para cerrarse.

---

## 🖥️ Uso manual (línea de comandos)
Abre PowerShell o cmd en la carpeta del script y ejecuta:

1. **Extraer cadenas**:
 ```bash
 python pencil_text_manager.py extract Prototipo.epgz --out texts.csv
````

2. **Traducir CSV**:

   ```bash
   python pencil_text_manager.py translate texts.csv --out texts_translated.csv
   ```

3. **Reemplazar y reempaquetar**:

   ```bash
   python pencil_text_manager.py replace Prototipo.epgz texts_translated.csv --out Prototipo_EN.epgz
   ```

---

## 🔍 Verificación

* Abre **`texts.csv`** y revisa que aparecen todas las cadenas originales.
* Abre **`texts_translated.csv`** y comprueba la columna `new_text` con las traducciones.
* Abre **`<nombre>_EN.epgz`** en Pencil.

---

> *Creado con ❤️ para agilizar la traducción de textos a inglés en Pencil.*
