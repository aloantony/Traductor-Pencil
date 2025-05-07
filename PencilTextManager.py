#!/usr/bin/env python3
"""pencil_text_manager.py – v3.4 (all-in-one command)
========================================================
Herramienta para extraer, traducir y reemplazar textos en prototipos `.epgz` de Pencil Project.
Con un solo comando (`all`), realiza todo el flujo: extract → translate → replace.

Subcomandos:
  extract <file>        → genera `texts.csv`
  translate <csv>       → genera `<csv>_translated.csv`
  replace <file> <csv>  → genera `.epgz` con textos reemplazados

Requisitos:
  pip install googletrans==4.0.0-rc1
"""

import argparse, csv, gzip, sys, tarfile, tempfile, zipfile, time
from io import BytesIO
from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET
import re
from html import unescape

# Intenta importar el traductor de Google. Si no está instalado, Translator será None.
try:
    from googletrans import Translator
except ImportError:
    Translator = None

# Constantes para el espacio de nombres de Pencil y los formatos soportados
PENCIL_NS = "http://www.evolus.vn/Namespace/Pencil"
ET.register_namespace("p", PENCIL_NS)
FMT_ZIP = "zip"; FMT_TGZ = "tgz"

def _detect_format(path: Path) -> str:
    """
    Detecta si el archivo es ZIP o TGZ (gzip+tar) por sus bytes mágicos.
    Esto permite saber cómo descomprimir el archivo .epgz.
    """
    with path.open("rb") as f:
        magic = f.read(2)
    if magic == b"PK": return FMT_ZIP
    if magic == b"\x1F\x8B": return FMT_TGZ
    raise ValueError("Formato .epgz no reconocido")

def _safe_extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    """
    Extrae un tar.gz de forma segura evitando path traversal (ataques de seguridad).
    Solo permite extraer archivos dentro del directorio destino.
    """
    base = dest.resolve()
    for member in tar.getmembers():
        target = base / member.name
        if not target.resolve().is_relative_to(base):
            raise RuntimeError(f"Path traversal detectado: {member.name}")
        tar.extract(member, dest)

def _unpack(path: Path, workdir: Path) -> str:
    """
    Descomprime el archivo .epgz en un directorio temporal.
    Soporta tanto ZIP como TGZ.
    """
    fmt = _detect_format(path)
    if fmt == FMT_ZIP:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(workdir)
    else:
        with gzip.open(path, "rb") as gz:
            with tarfile.open(fileobj=gz, mode="r:") as tar:
                _safe_extract_tar(tar, workdir)
    return fmt

def _repack(workdir: Path, output: Path, fmt: str) -> None:
    """
    Vuelve a empaquetar el directorio temporal en .epgz (zip o tgz).
    Esto permite crear un nuevo archivo Pencil con los textos modificados.
    """
    if fmt == FMT_ZIP:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in workdir.rglob("*"):
                if p.is_file(): zf.write(p, p.relative_to(workdir))
    else:
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for p in workdir.rglob("*"):
                if p.is_file(): tar.add(p, arcname=p.relative_to(workdir))
        buf.seek(0)
        with gzip.open(output, "wb") as gz: gz.write(buf.read())

def _iter_pages(workdir: Path):
    """
    Devuelve un generador con todos los archivos XML de páginas de Pencil.
    """
    return workdir.rglob("page_*.xml")

def _strip_html(text):
    """
    Elimina etiquetas HTML simples de un texto (por ejemplo, <span>).
    Útil para limpiar textos extraídos de propiedades Pencil.
    """
    return re.sub(r'<[^>]+>', '', unescape(text or '')).strip()

def extract(epgz: Path, csv_out: Path) -> None:
    """
    Extrae textos visibles de <p:property> relevantes, <tspan>, <text> y nodos con p:name.
    Solo se extraen textos que suelen ser visibles/editables por el usuario.
    El resultado se guarda en un CSV con columnas: page, text
    """
    rows: List[Dict[str, str]] = []
    ns = {"p": PENCIL_NS}
    last_text = None  # Evita duplicados consecutivos
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        _unpack(epgz, wd)
        for xml_file in _iter_pages(wd):
            tree = ET.parse(xml_file)
            root = tree.getroot()
            # 1. Extraer de <p:property> (textos de usuario)
            for prop in tree.findall(f".//p:property", ns):
                name = prop.get("name", "")
                if name in ("text", "label", "contentText", "name", "note"):
                    txt = (prop.text or "").strip()
                    if txt and txt != last_text:
                        rows.append({"page": xml_file.name, "text": txt})
                        last_text = txt
            # 2. Extraer de nodos con atributo p:name (textos visibles)
            for elem in tree.findall(".//*[@p:name]", ns):
                txt = ''.join(elem.itertext()).strip()
                if txt and txt != last_text:
                    rows.append({"page": xml_file.name, "text": txt})
                    last_text = txt
            # 3. Extraer de <text> y <tspan> SVG (textos en gráficos)
            for text_elem in root.findall(".//{http://www.w3.org/2000/svg}text"):
                for tspan in text_elem.findall("{http://www.w3.org/2000/svg}tspan"):
                    txt = (tspan.text or "").strip()
                    if txt and txt != last_text:
                        rows.append({"page": xml_file.name, "text": txt})
                        last_text = txt
                # Si hay texto directo en <text> (sin tspan)
                if text_elem.text and text_elem.text.strip() and text_elem.text.strip() != last_text:
                    rows.append({"page": xml_file.name, "text": text_elem.text.strip()})
                    last_text = text_elem.text.strip()
    # Guarda los textos extraídos en CSV
    with csv_out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["page", "text"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] {len(rows)} cadenas exportadas → {csv_out}")

def replace(epgz: Path, csv_in: Path, output: Path) -> None:
    """
    Reemplaza los textos extraídos por sus traducciones usando el CSV traducido.
    Solo reemplaza si el texto y la página coinciden exactamente.
    """
    if not csv_in.exists():
        sys.exit("[ERR] CSV no encontrado")
    with csv_in.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, skipinitialspace=True)
        if not reader.fieldnames:
            sys.exit("[ERR] CSV sin cabeceras válidas")
        # Lee todas las filas del CSV traducido
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in reader]
    # Crea un diccionario para buscar traducciones rápidamente
    repls = {(r["page"], r["text"]): r["new_text"] for r in rows if r.get("page") and r.get("text") and r.get("new_text")}
    if not repls:
        sys.exit("[ERR] CSV sin filas válidas")
    ns = {"p": PENCIL_NS}
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        fmt = _unpack(epgz, wd)
        changes = 0
        for xml_file in _iter_pages(wd):
            tree = ET.parse(xml_file)
            mod = False
            for elem in tree.iter():
                # Reemplazo en el texto principal del nodo
                if elem.text:
                    orig = elem.text.strip()
                    key = (xml_file.name, orig)
                    if key in repls:
                        elem.text = repls[key]
                        mod = True
                        changes += 1
                # Reemplazo en el texto "tail" (después del nodo)
                if elem.tail:
                    orig_tail = elem.tail.strip()
                    key_tail = (xml_file.name, orig_tail)
                    if key_tail in repls:
                        elem.tail = repls[key_tail]
                        mod = True
                        changes += 1
            # Si hubo cambios, guarda el XML modificado
            if mod:
                tree.write(xml_file, encoding="utf-8", xml_declaration=True)
        # Si hubo cambios en algún archivo, vuelve a empaquetar el .epgz
        if changes:
            _repack(wd, output, fmt)
            print(f"[OK] {changes} reemplazos → {output}")
        else:
            print("[WARN] Sin cambios realizados.")

def translate_csv(csv_in: Path, csv_out: Path) -> None:
    """
    Traduce el CSV de textos usando Google Translate.
    Traduce solo los textos únicos y guarda el resultado en un nuevo CSV.
    """
    if Translator is None:
        sys.exit("[ERR] 'googletrans' no está instalado")
    tr = Translator()
    rows: List[Dict[str, str]] = []
    # Lee el CSV de entrada
    with csv_in.open("r", encoding="utf-8", newline="") as fh:
        reader = list(csv.DictReader(fh))
    unique_texts = {row["text"] for row in reader}
    translations = {}
    print(f"[INFO] Traduciendo {len(unique_texts)} textos únicos...")
    # Traduce cada texto único
    for idx, txt in enumerate(unique_texts, start=1):
        print(f"  → {idx}/{len(unique_texts)}: {txt[:30]}...", end="", flush=True)
        try:
            new = tr.translate(txt, src="es", dest="en").text or ""
            print(" OK")
        except Exception as ex:
            print(f" ERROR ({ex})")
            new = ""
        translations[txt] = new
        time.sleep(0.01)  # Espera para evitar bloqueos por exceso de peticiones
    # Genera el nuevo CSV con las traducciones
    for row in reader:
        txt = row.get("text", "")
        nt = translations.get(txt, "")
        rows.append({"page": row.get("page", ""), "text": txt, "new_text": nt})
    with csv_out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["page", "text", "new_text"])
        writer.writeheader(); writer.writerows(rows)

def main() -> None:
    """
    Punto de entrada principal del script y CLI.
    Permite usar el script desde la terminal con subcomandos o en modo automático.
    """
    parser = argparse.ArgumentParser(prog="pencil_text_manager.py v3.4")
    sub = parser.add_subparsers(dest="cmd")
    ex = sub.add_parser("extract", help="Extrae textos visibles del prototipo")
    ex.add_argument("epgz", type=Path); ex.add_argument("--out", type=Path, default=Path("texts.csv"))
    tr = sub.add_parser("translate", help="Traduce CSV existente")
    tr.add_argument("csv", type=Path); tr.add_argument("--out", type=Path, default=Path("texts_translated.csv"))
    rp = sub.add_parser("replace", help="Reemplaza textos y reempaqueta .epgz")
    rp.add_argument("epgz", type=Path); rp.add_argument("csv", type=Path); rp.add_argument("--out", type=Path, default=Path("output.epgz"))
    args = parser.parse_args()

    # --- AUTO MODE: si no hay argumentos, realiza todo el flujo automáticamente ---
    if args.cmd is None:
        script_dir = Path(__file__).parent
        epgz_files = list(script_dir.glob("*.epgz"))
        if len(epgz_files) != 1:
            print(f"[ERR] Esperaba un único archivo .epgz en {script_dir}, encontrados: {len(epgz_files)}")
            input("\nPresiona Enter para cerrar...")
            return
        epgz = epgz_files[0]
        csv = script_dir / "texts.csv"
        csv_trans = script_dir / "texts_translated.csv"
        out_epgz = script_dir / (epgz.stem + "_EN.epgz")
        print(f"[INFO] Procesando archivo: {epgz.name}")

        print("[INFO] Extrayendo textos...")
        extract(epgz, csv)
        print("[INFO] Traduciendo textos...")
        translate_csv(csv, csv_trans)
        print("[INFO] Reemplazando textos y generando nuevo .epgz...")
        replace(epgz, csv_trans, out_epgz)
        print(f"[OK] Proceso completo. Archivo generado: {out_epgz.name}")
        input("\nPresiona Enter para cerrar...")
        return

    # --- NORMAL CLI MODE: permite usar extract, translate o replace por separado ---
    if args.cmd == "extract":
        extract(args.epgz, args.out)
    elif args.cmd == "translate":
        translate_csv(args.csv, args.out)
        print(f"[OK] Traducción CSV → {args.out}")
    elif args.cmd == "replace":
        replace(args.epgz, args.csv, args.out)
    else:
        parser.print_help()
    input("\nPresiona Enter para cerrar...")

if __name__ == "__main__":
    main()
