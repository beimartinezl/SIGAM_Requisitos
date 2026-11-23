from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, g
import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from pathlib import Path
from datetime import date, timedelta
from io import BytesIO, StringIO
import csv
from datetime import datetime
from flask import Response

app = Flask(__name__)
# La clave se conserva entre reinicios. En despliegues administrados debe definirse SIGAM_SECRET_KEY.
secret_file = Path(__file__).with_name(".sigam_secret_key")
app.secret_key = os.environ.get("SIGAM_SECRET_KEY")
if not app.secret_key:
    if secret_file.exists():
        app.secret_key = secret_file.read_text(encoding="utf-8").strip()
    else:
        app.secret_key = secrets.token_hex(32)
        secret_file.write_text(app.secret_key, encoding="utf-8")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SIGAM_HTTPS", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
csrf = CSRFProtect(app)
DB = Path(__file__).with_name("sigam.db")

def connect():
    # Cada solicitud abre su propia conexión al archivo central del servidor.
    # SQLite espera brevemente si otra solicitud está realizando una escritura.
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    return con

def init_db():
    # WAL mejora la convivencia entre lecturas y escrituras concurrentes.
    # La base debe permanecer en el disco local del computador servidor,
    # no dentro de una carpeta compartida de red.
    with connect() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            nombre TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('Administrador','Supervisor','Trabajador')),
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            categoria TEXT DEFAULT '',
            ubicacion TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Activo',
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS avisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id INTEGER NOT NULL REFERENCES activos(id),
            descripcion TEXT NOT NULL,
            fecha TEXT NOT NULL,
            prioridad TEXT NOT NULL CHECK(prioridad IN ('Baja','Media','Alta')),
            estado TEXT NOT NULL DEFAULT 'Abierto'
        );
        CREATE TABLE IF NOT EXISTS ordenes_trabajo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aviso_id INTEGER NOT NULL UNIQUE REFERENCES avisos(id),
            descripcion TEXT NOT NULL,
            prioridad TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            asignado_a INTEGER REFERENCES usuarios(id),
            asignada_en TEXT,
            prueba_retorno TEXT NOT NULL DEFAULT 'Pendiente',
            observaciones_retorno TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS intervenciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_id INTEGER NOT NULL REFERENCES ordenes_trabajo(id),
            descripcion TEXT NOT NULL,
            fecha TEXT NOT NULL,
            responsable TEXT NOT NULL,
            hora_inicio TEXT NOT NULL DEFAULT '',
            hora_fin TEXT NOT NULL DEFAULT '',
            resultado TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS historial_asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_id INTEGER NOT NULL REFERENCES ordenes_trabajo(id),
            usuario_id INTEGER REFERENCES usuarios(id),
            asignado_por INTEGER REFERENCES usuarios(id),
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            observacion TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS repuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,
            nombre TEXT NOT NULL,
            unidad TEXT NOT NULL DEFAULT 'unidad',
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK(stock_minimo >= 0),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS movimientos_repuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repuesto_id INTEGER NOT NULL REFERENCES repuestos(id),
            orden_id INTEGER REFERENCES ordenes_trabajo(id),
            tipo TEXT NOT NULL CHECK(tipo IN ('Entrada','Consumo')),
            cantidad INTEGER NOT NULL CHECK(cantidad > 0),
            usuario_id INTEGER REFERENCES usuarios(id),
            observacion TEXT NOT NULL DEFAULT '',
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_movimientos_orden ON movimientos_repuestos(orden_id);
        CREATE INDEX IF NOT EXISTS idx_movimientos_repuesto ON movimientos_repuestos(repuesto_id);
        CREATE TABLE IF NOT EXISTS planes_preventivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id INTEGER NOT NULL REFERENCES activos(id),
            titulo TEXT NOT NULL,
            instrucciones TEXT NOT NULL DEFAULT '',
            frecuencia_dias INTEGER NOT NULL CHECK(frecuencia_dias BETWEEN 1 AND 3650),
            proxima_fecha TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
            creado_por INTEGER REFERENCES usuarios(id),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_preventivos_fecha ON planes_preventivos(activo,proxima_fecha);
        CREATE TABLE IF NOT EXISTS tareas_preventivas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES planes_preventivos(id),
            descripcion TEXT NOT NULL,
            orden INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ejecuciones_preventivas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES planes_preventivos(id),
            responsable_id INTEGER REFERENCES usuarios(id),
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            observaciones TEXT NOT NULL DEFAULT '',
            fecha_anterior TEXT NOT NULL,
            fecha_siguiente TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resultados_preventivos (
            ejecucion_id INTEGER NOT NULL REFERENCES ejecuciones_preventivas(id),
            tarea_id INTEGER NOT NULL REFERENCES tareas_preventivas(id),
            PRIMARY KEY (ejecucion_id,tarea_id)
        );
        CREATE TABLE IF NOT EXISTS entregas_turno (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL CHECK(turno IN ('Mañana','Tarde','Noche')),
            resumen TEXT NOT NULL,
            pendientes TEXT NOT NULL DEFAULT '',
            autor_id INTEGER REFERENCES usuarios(id),
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS suscripcion (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            plan TEXT NOT NULL,
            estado TEXT NOT NULL,
            inicio TEXT,
            fin_prueba TEXT,
            precio_clp INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS pruebas_usabilidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participante TEXT NOT NULL,
            completo INTEGER NOT NULL,
            duracion_segundos INTEGER NOT NULL,
            dificultad TEXT DEFAULT '',
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Migración incremental: preserva las bases creadas con SIGAM v4.3.
        for tabla, campos in {
            "ordenes_trabajo": {
                "asignado_a": "INTEGER REFERENCES usuarios(id)",
                "asignada_en": "TEXT",
                "prueba_retorno": "TEXT NOT NULL DEFAULT 'Pendiente'",
                "observaciones_retorno": "TEXT NOT NULL DEFAULT ''",
            },
            "intervenciones": {
                "hora_inicio": "TEXT NOT NULL DEFAULT ''",
                "hora_fin": "TEXT NOT NULL DEFAULT ''",
                "resultado": "TEXT NOT NULL DEFAULT ''",
            },
        }.items():
            actuales = {fila["name"] for fila in con.execute(f"PRAGMA table_info({tabla})")}
            for nombre, definicion in campos.items():
                if nombre not in actuales:
                    con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")

# Inicializa las tablas también al ejecutar con un servidor WSGI (por ejemplo Gunicorn).
init_db()

ROLES = ("Administrador", "Supervisor", "Trabajador")


def user_count():
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]


@app.before_request
def load_user_and_enforce_access():
    g.user = None
    uid = session.get("user_id")
    if uid:
        with connect() as con:
            g.user = con.execute("SELECT id, username, nombre, rol, activo FROM usuarios WHERE id=?", (uid,)).fetchone()
        if not g.user or not g.user["activo"]:
            session.clear()
            g.user = None

    endpoint = request.endpoint or ""
    if endpoint == "static":
        return
    if user_count() == 0:
        if endpoint != "setup":
            return redirect(url_for("setup"))
        return
    if endpoint == "setup":
        return redirect(url_for("login"))
    if endpoint in ("login",):
        return
    if endpoint == "logout":
        if not g.user:
            return redirect(url_for("login"))
        return
    if not g.user:
        return redirect(url_for("login", next=request.path))

    role = g.user["rol"]
    admin_only = {"usuarios", "usuario_nuevo", "usuario_estado", "usuario_actualizar", "prueba"}
    supervisor_or_admin = {"activo_form", "desactivar_activo", "crear_orden", "importar_activos", "asignar_orden", "prueba_retorno", "repuesto_nuevo", "repuesto_entrada", "preventivo_nuevo", "preventivo_estado", "reportes", "exportar_reporte"}
    if endpoint == "orden_detalle" and request.method == "POST":
        supervisor_or_admin.add(endpoint)
    if endpoint in admin_only and role != "Administrador":
        abort(403)
    if endpoint in supervisor_or_admin and role not in ("Administrador", "Supervisor"):
        abort(403)


@app.route("/configurar", methods=["GET", "POST"])
def setup():
    if user_count() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        nombre = request.form.get("nombre", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not username or not nombre or len(password) < 10:
            flash("Completa los datos. La contraseña debe tener al menos 10 caracteres.", "error")
        elif password != confirm:
            flash("Las contraseñas no coinciden.", "error")
        else:
            with connect() as con:
                con.execute("INSERT INTO usuarios(username,nombre,password_hash,rol) VALUES(?,?,?,'Administrador')",
                            (username, nombre, generate_password_hash(password)))
                uid = con.execute("SELECT id FROM usuarios WHERE username=?", (username,)).fetchone()[0]
            session.clear()
            session.permanent = True
            session["user_id"] = uid
            flash("Cuenta de administrador creada. Ya puedes comenzar a utilizar SIGAM.", "success")
            return redirect(url_for("index"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect() as con:
            user = con.execute("SELECT * FROM usuarios WHERE username=? COLLATE NOCASE AND activo=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            next_url = request.args.get("next", "")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("index")
            return redirect(next_url)
        flash("Usuario o contraseña incorrectos, o cuenta desactivada.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login"))


@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        nombre = request.form.get("nombre", "").strip()
        password = request.form.get("password", "")
        rol = request.form.get("rol", "")
        if not username or not nombre or rol not in ROLES or len(password) < 10:
            flash("Completa los datos y utiliza una contraseña de al menos 10 caracteres.", "error")
        else:
            try:
                with connect() as con:
                    con.execute("INSERT INTO usuarios(username,nombre,password_hash,rol) VALUES(?,?,?,?)",
                                (username, nombre, generate_password_hash(password), rol))
                flash("Usuario creado correctamente.", "success")
                return redirect(url_for("usuarios"))
            except sqlite3.IntegrityError:
                flash("Ese nombre de usuario ya existe.", "error")
    with connect() as con:
        rows = con.execute("SELECT id,username,nombre,rol,activo,creado_en FROM usuarios ORDER BY nombre").fetchall()
    return render_template("usuarios.html", usuarios=rows, roles=ROLES)


@app.route("/usuarios/<int:uid>/actualizar", methods=["POST"])
def usuario_actualizar(uid):
    rol = request.form.get("rol", "")
    password = request.form.get("password", "")
    if rol not in ROLES:
        abort(400)
    with connect() as con:
        target = con.execute("SELECT id,rol,activo FROM usuarios WHERE id=?", (uid,)).fetchone()
        if not target:
            abort(404)
        if target["rol"] == "Administrador" and target["activo"] and rol != "Administrador":
            admins = con.execute("SELECT COUNT(*) FROM usuarios WHERE rol='Administrador' AND activo=1").fetchone()[0]
            if admins <= 1:
                flash("Debe existir al menos un administrador activo.", "error")
                return redirect(url_for("usuarios"))
        if password and len(password) < 10:
            flash("La nueva contraseña debe tener al menos 10 caracteres.", "error")
            return redirect(url_for("usuarios"))
        if password:
            con.execute("UPDATE usuarios SET rol=?, password_hash=? WHERE id=?",
                        (rol, generate_password_hash(password), uid))
        else:
            con.execute("UPDATE usuarios SET rol=? WHERE id=?", (rol, uid))
    flash("Permisos y cuenta actualizados.", "success")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/estado", methods=["POST"])
def usuario_estado(uid):
    activo = 1 if request.form.get("activo") == "1" else 0
    if uid == g.user["id"] and not activo:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("usuarios"))
    with connect() as con:
        target = con.execute("SELECT id,rol,activo FROM usuarios WHERE id=?", (uid,)).fetchone()
        if not target:
            abort(404)
        if target["rol"] == "Administrador" and target["activo"] and not activo:
            admins = con.execute("SELECT COUNT(*) FROM usuarios WHERE rol='Administrador' AND activo=1").fetchone()[0]
            if admins <= 1:
                flash("Debe existir al menos un administrador activo.", "error")
                return redirect(url_for("usuarios"))
        con.execute("UPDATE usuarios SET activo=? WHERE id=?", (activo, uid))
    flash("Estado del usuario actualizado.", "success")
    return redirect(url_for("usuarios"))


@app.route("/")
def index():
    with connect() as con:
        stats = {
            "activos": con.execute("SELECT COUNT(*) FROM activos WHERE estado='Activo'").fetchone()[0],
            "avisos": con.execute("SELECT COUNT(*) FROM avisos WHERE estado='Abierto'").fetchone()[0],
            "pendientes": con.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE estado='Pendiente'").fetchone()[0],
            "progreso": con.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE estado='En progreso'").fetchone()[0],
            "finalizadas": con.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE estado='Finalizada'").fetchone()[0],
        }
        recientes = con.execute("""SELECT a.codigo, a.nombre, v.descripcion, v.fecha, v.prioridad, v.estado
            FROM avisos v JOIN activos a ON a.id=v.activo_id ORDER BY v.id DESC LIMIT 5""").fetchall()
    return render_template("index.html", stats=stats, recientes=recientes)

@app.route("/activos")
def activos():
    q = request.args.get("q", "").strip()
    with connect() as con:
        rows = con.execute("""SELECT * FROM activos
            WHERE codigo LIKE ? OR nombre LIKE ? OR ubicacion LIKE ?
            ORDER BY id DESC""", (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    return render_template("activos.html", activos=rows, q=q)

@app.route("/activos/importar", methods=["GET", "POST"])
def importar_activos():
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            flash("Selecciona un archivo Excel (.xlsx).", "error")
            return redirect(url_for("importar_activos"))
        if not archivo.filename.lower().endswith(".xlsx"):
            flash("Formato no válido. Sube un archivo .xlsx.", "error")
            return redirect(url_for("importar_activos"))
        try:
            from openpyxl import load_workbook
            libro = load_workbook(BytesIO(archivo.read()), read_only=True, data_only=True)
            hoja = libro.active
            filas = hoja.iter_rows(values_only=True)
            encabezados = next(filas, None)
            if not encabezados:
                flash("El archivo está vacío.", "error")
                return redirect(url_for("importar_activos"))
            normalizar = lambda v: str(v or "").strip().lower()
            mapa = {normalizar(v): i for i, v in enumerate(encabezados)}
            requeridas = {"codigo", "nombre", "categoria", "ubicacion"}
            if not requeridas.issubset(mapa):
                flash("La primera fila debe contener: codigo, nombre, categoria y ubicacion.", "error")
                return redirect(url_for("importar_activos"))
            validos, errores, codigos_archivo = [], [], set()
            for numero, fila in enumerate(filas, start=2):
                valores = [fila[mapa[k]] if mapa[k] < len(fila) else None for k in
                           ("codigo", "nombre", "categoria", "ubicacion")]
                codigo, nombre, categoria, ubicacion = [str(v).strip() if v is not None else "" for v in valores]
                if not any((codigo, nombre, categoria, ubicacion)):
                    continue
                if not codigo or not nombre or not ubicacion:
                    errores.append(f"Fila {numero}: código, nombre y ubicación son obligatorios.")
                    continue
                clave = codigo.casefold()
                if clave in codigos_archivo:
                    errores.append(f"Fila {numero}: código duplicado dentro del archivo ({codigo}).")
                    continue
                codigos_archivo.add(clave)
                validos.append((codigo, nombre, categoria, ubicacion, numero))
            if not validos and not errores:
                flash("No se encontraron filas para importar.", "error")
                return redirect(url_for("importar_activos"))
            importados, duplicados = 0, []
            with connect() as con:
                existentes = {r[0].casefold() for r in con.execute("SELECT codigo FROM activos")}
                for codigo, nombre, categoria, ubicacion, numero in validos:
                    if codigo.casefold() in existentes:
                        duplicados.append(f"Fila {numero}: el código {codigo} ya existe en SIGAM.")
                        continue
                    con.execute("INSERT INTO activos(codigo,nombre,categoria,ubicacion) VALUES(?,?,?,?)",
                                (codigo, nombre, categoria, ubicacion))
                    existentes.add(codigo.casefold())
                    importados += 1
            libro.close()
            if importados:
                flash(f"Importación completada: {importados} activo(s) incorporado(s).", "success")
            if duplicados or errores:
                detalle = " ".join((duplicados + errores)[:5])
                restante = len(duplicados) + len(errores) - 5
                if restante > 0:
                    detalle += f" Y {restante} error(es) adicional(es)."
                flash(f"Se omitieron {len(duplicados) + len(errores)} fila(s). {detalle}", "error")
            return redirect(url_for("activos"))
        except Exception:
            app.logger.exception("Error al importar archivo Excel")
            flash("No se pudo leer el archivo. Verifica que sea un Excel .xlsx válido y usa la plantilla SIGAM.", "error")
            return redirect(url_for("importar_activos"))
    return render_template("importar_activos.html")


@app.route("/activos/plantilla.xlsx")
def plantilla_activos():
    from openpyxl import Workbook
    from flask import send_file
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Activos"
    hoja.append(["codigo", "nombre", "categoria", "ubicacion"])
    hoja.append(["EQ-001", "Bomba de agua", "Equipo", "Planta 1"])
    hoja.append(["EQ-002", "Compresor", "Equipo", "Planta 2"])
    salida = BytesIO()
    libro.save(salida)
    salida.seek(0)
    return send_file(salida, as_attachment=True, download_name="plantilla_activos_sigam.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/activos/nuevo", methods=["GET", "POST"])
@app.route("/activos/<int:aid>/editar", methods=["GET", "POST"])
def activo_form(aid=None):
    with connect() as con:
        row = con.execute("SELECT * FROM activos WHERE id=?", (aid,)).fetchone() if aid else None
        if aid and not row: abort(404)
        if request.method == "POST":
            codigo = request.form.get("codigo","").strip()
            nombre = request.form.get("nombre","").strip()
            ubicacion = request.form.get("ubicacion","").strip()
            categoria = request.form.get("categoria","").strip()
            estado = request.form.get("estado","Activo")
            if not codigo or not nombre or not ubicacion:
                flash("Completa código, nombre y ubicación.", "error")
            else:
                try:
                    if aid:
                        con.execute("""UPDATE activos SET codigo=?, nombre=?, categoria=?, ubicacion=?, estado=? WHERE id=?""",
                                    (codigo,nombre,categoria,ubicacion,estado,aid))
                        flash("Activo actualizado correctamente.", "success")
                    else:
                        con.execute("""INSERT INTO activos(codigo,nombre,categoria,ubicacion) VALUES(?,?,?,?)""",
                                    (codigo,nombre,categoria,ubicacion))
                        flash("Activo registrado correctamente.", "success")
                    return redirect(url_for("activos"))
                except sqlite3.IntegrityError:
                    flash("Ese código ya existe. Utiliza un código único.", "error")
    return render_template("activo_form.html", activo=row)

@app.route("/activos/<int:aid>/desactivar", methods=["POST"])
def desactivar_activo(aid):
    with connect() as con:
        con.execute("UPDATE activos SET estado='Inactivo' WHERE id=?", (aid,))
    flash("Activo desactivado. Su historial se conserva.", "success")
    return redirect(url_for("activos"))

@app.route("/activos/<int:aid>")
def activo_detalle(aid):
    with connect() as con:
        activo = con.execute("SELECT * FROM activos WHERE id=?", (aid,)).fetchone()
        if not activo: abort(404)
        avisos = con.execute("""SELECT v.*, o.id AS orden_id, o.estado AS orden_estado
            FROM avisos v LEFT JOIN ordenes_trabajo o ON o.aviso_id=v.id
            WHERE v.activo_id=? ORDER BY v.id DESC""", (aid,)).fetchall()
        trabajos = con.execute("""SELECT i.*, o.id AS orden_id, o.prueba_retorno
            FROM intervenciones i JOIN ordenes_trabajo o ON o.id=i.orden_id
            JOIN avisos v ON v.id=o.aviso_id
            WHERE v.activo_id=? ORDER BY i.fecha DESC, i.id DESC""", (aid,)).fetchall()
    return render_template("activo_detalle.html", activo=activo, avisos=avisos, trabajos=trabajos)

@app.route("/avisos")
def avisos():
    with connect() as con:
        rows = con.execute("""SELECT v.*, a.codigo, a.nombre, o.id AS orden_id
            FROM avisos v JOIN activos a ON a.id=v.activo_id
            LEFT JOIN ordenes_trabajo o ON o.aviso_id=v.id ORDER BY v.id DESC""").fetchall()
    return render_template("avisos.html", avisos=rows)

@app.route("/avisos/nuevo", methods=["GET","POST"])
def aviso_nuevo():
    with connect() as con:
        activos = con.execute("SELECT id,codigo,nombre FROM activos WHERE estado='Activo' ORDER BY codigo").fetchall()
        if request.method == "POST":
            aid = request.form.get("activo_id")
            descripcion = request.form.get("descripcion","").strip()
            fecha = request.form.get("fecha") or date.today().isoformat()
            prioridad = request.form.get("prioridad","Media")
            if not aid or not descripcion:
                flash("Selecciona un activo e ingresa una descripción.", "error")
            else:
                con.execute("INSERT INTO avisos(activo_id,descripcion,fecha,prioridad) VALUES(?,?,?,?)",
                            (aid,descripcion,fecha,prioridad))
                flash("Aviso de falla registrado.", "success")
                return redirect(url_for("avisos"))
    return render_template("aviso_form.html", activos=activos, hoy=date.today().isoformat())

@app.route("/avisos/<int:vid>/orden", methods=["POST"])
def crear_orden(vid):
    with connect() as con:
        aviso = con.execute("SELECT * FROM avisos WHERE id=?", (vid,)).fetchone()
        if not aviso: abort(404)
        try:
            cur = con.execute("INSERT INTO ordenes_trabajo(aviso_id,descripcion,prioridad) VALUES(?,?,?)",
                              (vid,aviso["descripcion"],aviso["prioridad"]))
            con.execute("UPDATE avisos SET estado='En orden de trabajo' WHERE id=?", (vid,))
            oid = cur.lastrowid
            flash("Orden de trabajo creada.", "success")
            return redirect(url_for("orden_detalle", oid=oid))
        except sqlite3.IntegrityError:
            oid = con.execute("SELECT id FROM ordenes_trabajo WHERE aviso_id=?", (vid,)).fetchone()["id"]
            return redirect(url_for("orden_detalle", oid=oid))

@app.route("/ordenes")
def ordenes():
    with connect() as con:
        rows = con.execute("""SELECT o.*, v.fecha, a.codigo, a.nombre
            FROM ordenes_trabajo o JOIN avisos v ON v.id=o.aviso_id
            JOIN activos a ON a.id=v.activo_id ORDER BY o.id DESC""").fetchall()
    return render_template("ordenes.html", ordenes=rows)

@app.route("/ordenes/<int:oid>/asignar", methods=["POST"])
def asignar_orden(oid):
    usuario_id = request.form.get("usuario_id", "").strip()
    observacion = request.form.get("observacion", "").strip()
    with connect() as con:
        if not con.execute("SELECT id FROM ordenes_trabajo WHERE id=?", (oid,)).fetchone():
            abort(404)
        if usuario_id:
            usuario = con.execute("SELECT id FROM usuarios WHERE id=? AND activo=1 AND rol IN ('Supervisor','Trabajador')", (usuario_id,)).fetchone()
            if not usuario:
                flash("Selecciona un trabajador o supervisor activo.", "error")
                return redirect(url_for("orden_detalle", oid=oid))
            usuario_id = usuario["id"]
        else:
            usuario_id = None
        con.execute("UPDATE ordenes_trabajo SET asignado_a=?, asignada_en=CURRENT_TIMESTAMP WHERE id=?", (usuario_id, oid))
        con.execute("INSERT INTO historial_asignaciones(orden_id,usuario_id,asignado_por,observacion) VALUES(?,?,?,?)",
                    (oid, usuario_id, g.user["id"], observacion))
    flash("Responsable de la orden actualizado.", "success")
    return redirect(url_for("orden_detalle", oid=oid))


@app.route("/ordenes/<int:oid>/prueba-retorno", methods=["POST"])
def prueba_retorno(oid):
    resultado = request.form.get("resultado", "")
    observaciones = request.form.get("observaciones", "").strip()
    if resultado not in ("Aprobada", "Rechazada", "No aplica"):
        abort(400)
    with connect() as con:
        if not con.execute("SELECT id FROM ordenes_trabajo WHERE id=?", (oid,)).fetchone():
            abort(404)
        con.execute("UPDATE ordenes_trabajo SET prueba_retorno=?, observaciones_retorno=? WHERE id=?",
                    (resultado, observaciones, oid))
    flash("Verificación de retorno registrada.", "success")
    return redirect(url_for("orden_detalle", oid=oid))


@app.route("/ordenes/<int:oid>", methods=["GET","POST"])
def orden_detalle(oid):
    with connect() as con:
        orden = con.execute("""SELECT o.*, v.fecha AS fecha_aviso, v.descripcion AS falla,
            a.codigo, a.nombre AS activo_nombre, u.nombre AS asignado_nombre FROM ordenes_trabajo o
            JOIN avisos v ON v.id=o.aviso_id JOIN activos a ON a.id=v.activo_id
            LEFT JOIN usuarios u ON u.id=o.asignado_a WHERE o.id=?""", (oid,)).fetchone()
        if not orden: abort(404)
        if request.method == "POST":
            estado = request.form.get("estado")
            if estado not in ("Pendiente","En progreso","Finalizada"): abort(400)
            con.execute("UPDATE ordenes_trabajo SET estado=? WHERE id=?", (estado,oid))
            flash("Estado de la orden actualizado.", "success")
            return redirect(url_for("orden_detalle", oid=oid))
        intervenciones = con.execute("SELECT * FROM intervenciones WHERE orden_id=? ORDER BY id DESC", (oid,)).fetchall()
        tecnicos = con.execute("SELECT id,nombre,rol FROM usuarios WHERE activo=1 AND rol IN ('Supervisor','Trabajador') ORDER BY nombre").fetchall()
        repuestos_disponibles = con.execute("SELECT id,codigo,nombre,unidad,stock FROM repuestos ORDER BY nombre").fetchall()
        consumos = con.execute("""SELECT m.*,r.codigo,r.nombre,r.unidad,u.nombre AS usuario_nombre
            FROM movimientos_repuestos m JOIN repuestos r ON r.id=m.repuesto_id
            LEFT JOIN usuarios u ON u.id=m.usuario_id WHERE m.orden_id=? AND m.tipo='Consumo'
            ORDER BY m.id DESC""", (oid,)).fetchall()
        asignaciones = con.execute("""SELECT h.*, u.nombre AS usuario_nombre, a.nombre AS autor_nombre
            FROM historial_asignaciones h LEFT JOIN usuarios u ON u.id=h.usuario_id
            LEFT JOIN usuarios a ON a.id=h.asignado_por WHERE h.orden_id=? ORDER BY h.id DESC""", (oid,)).fetchall()
    return render_template("orden_detalle.html", orden=orden, intervenciones=intervenciones,
                           tecnicos=tecnicos, asignaciones=asignaciones,
                           repuestos_disponibles=repuestos_disponibles, consumos=consumos,
                           hoy=date.today().isoformat())

@app.route("/ordenes/<int:oid>/intervencion", methods=["POST"])
def intervencion_nueva(oid):
    descripcion = request.form.get("descripcion","").strip()
    fecha = request.form.get("fecha") or date.today().isoformat()
    responsable = request.form.get("responsable", "").strip()
    hora_inicio = request.form.get("hora_inicio", "").strip()
    hora_fin = request.form.get("hora_fin", "").strip()
    resultado = request.form.get("resultado", "").strip()
    if not descripcion or not responsable:
        flash("Completa la descripción y el responsable.", "error")
    elif bool(hora_inicio) != bool(hora_fin) or (hora_inicio and hora_fin <= hora_inicio):
        flash("Indica ambas horas y asegúrate de que el término sea posterior al inicio.", "error")
    elif resultado not in ("", "Resuelto", "Pendiente", "Requiere seguimiento"):
        flash("Resultado no válido.", "error")
    else:
        with connect() as con:
            exists = con.execute("SELECT id FROM ordenes_trabajo WHERE id=?", (oid,)).fetchone()
            if not exists: abort(404)
            con.execute("""INSERT INTO intervenciones
                (orden_id,descripcion,fecha,responsable,hora_inicio,hora_fin,resultado)
                VALUES(?,?,?,?,?,?,?)""",
                (oid,descripcion,fecha,responsable,hora_inicio,hora_fin,resultado))
            flash("Intervención registrada.", "success")
    return redirect(url_for("orden_detalle", oid=oid))

@app.route("/repuestos")
def repuestos():
    q = request.args.get("q", "").strip()
    with connect() as con:
        rows = con.execute("""SELECT * FROM repuestos WHERE codigo LIKE ? OR nombre LIKE ?
            ORDER BY nombre, codigo""", (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("repuestos.html", repuestos=rows, q=q)


@app.route("/repuestos/nuevo", methods=["POST"])
def repuesto_nuevo():
    codigo = request.form.get("codigo", "").strip()
    nombre = request.form.get("nombre", "").strip()
    unidad = request.form.get("unidad", "unidad").strip()
    try:
        minimo = int(request.form.get("stock_minimo", "0"))
    except ValueError:
        minimo = -1
    if not codigo or not nombre or not unidad or minimo < 0:
        flash("Completa código, nombre, unidad y stock mínimo válido.", "error")
        return redirect(url_for("repuestos"))
    try:
        with connect() as con:
            con.execute("INSERT INTO repuestos(codigo,nombre,unidad,stock_minimo) VALUES(?,?,?,?)",
                        (codigo,nombre,unidad,minimo))
        flash("Repuesto incorporado. Registra una entrada para agregar existencias.", "success")
    except sqlite3.IntegrityError:
        flash("El código de repuesto ya existe.", "error")
    return redirect(url_for("repuestos"))


@app.route("/repuestos/<int:rid>/entrada", methods=["POST"])
def repuesto_entrada(rid):
    try:
        cantidad = int(request.form.get("cantidad", ""))
    except ValueError:
        cantidad = 0
    if cantidad <= 0:
        flash("La cantidad de entrada debe ser un número entero positivo.", "error")
        return redirect(url_for("repuestos"))
    observacion = request.form.get("observacion", "").strip()
    with connect() as con:
        cur = con.execute("UPDATE repuestos SET stock=stock+? WHERE id=?", (cantidad,rid))
        if cur.rowcount == 0:
            abort(404)
        con.execute("""INSERT INTO movimientos_repuestos(repuesto_id,tipo,cantidad,usuario_id,observacion)
            VALUES(?,'Entrada',?,?,?)""", (rid,cantidad,g.user["id"],observacion))
    flash("Entrada registrada. El stock ha sido actualizado.", "success")
    return redirect(url_for("repuestos"))


@app.route("/repuestos/movimientos")
def movimientos_repuestos():
    with connect() as con:
        rows = con.execute("""SELECT m.*,r.codigo,r.nombre,u.nombre AS usuario_nombre
            FROM movimientos_repuestos m JOIN repuestos r ON r.id=m.repuesto_id
            LEFT JOIN usuarios u ON u.id=m.usuario_id ORDER BY m.id DESC LIMIT 300""").fetchall()
    return render_template("movimientos_repuestos.html", movimientos=rows)


@app.route("/ordenes/<int:oid>/consumir", methods=["POST"])
def consumir_repuesto(oid):
    try:
        rid = int(request.form.get("repuesto_id", ""))
        cantidad = int(request.form.get("cantidad", ""))
    except ValueError:
        abort(400)
    if cantidad <= 0:
        flash("La cantidad consumida debe ser un número entero positivo.", "error")
        return redirect(url_for("orden_detalle", oid=oid))
    observacion = request.form.get("observacion", "").strip()
    with connect() as con:
        orden = con.execute("SELECT id,asignado_a,estado FROM ordenes_trabajo WHERE id=?", (oid,)).fetchone()
        if not orden:
            abort(404)
        # Un trabajador solo registra consumos en una orden que tenga asignada.
        if g.user["rol"] == "Trabajador" and orden["asignado_a"] != g.user["id"]:
            abort(403)
        if orden["estado"] == "Finalizada":
            flash("No es posible registrar consumos en una orden finalizada.", "error")
            return redirect(url_for("orden_detalle", oid=oid))
        # Actualización atómica: jamás permite existencias negativas aun con múltiples usuarios.
        actualizado = con.execute("""UPDATE repuestos SET stock=stock-?
            WHERE id=? AND stock>=?""", (cantidad,rid,cantidad))
        if actualizado.rowcount != 1:
            flash("Repuesto inexistente o stock insuficiente. No se registró el consumo.", "error")
            return redirect(url_for("orden_detalle", oid=oid))
        con.execute("""INSERT INTO movimientos_repuestos
            (repuesto_id,orden_id,tipo,cantidad,usuario_id,observacion)
            VALUES(?,?,'Consumo',?,?,?)""", (rid,oid,cantidad,g.user["id"],observacion))
    flash("Consumo de repuesto registrado en la orden.", "success")
    return redirect(url_for("orden_detalle", oid=oid))


@app.route("/preventivos")
def preventivos():
    filtro = request.args.get("filtro", "Todos")
    if filtro not in ("Todos", "Pendientes", "Programados", "Pausados"):
        filtro = "Todos"
    hoy = date.today().isoformat()
    with connect() as con:
        planes = con.execute("""SELECT p.*, a.codigo, a.nombre AS activo_nombre,
            (SELECT COUNT(*) FROM ejecuciones_preventivas e WHERE e.plan_id=p.id) AS ejecuciones
            FROM planes_preventivos p JOIN activos a ON a.id=p.activo_id
            ORDER BY p.activo DESC, p.proxima_fecha, p.id""").fetchall()
        activos = con.execute("SELECT id,codigo,nombre FROM activos WHERE estado='Activo' ORDER BY codigo").fetchall()
    if filtro == "Pendientes":
        planes = [r for r in planes if r['activo'] and r['proxima_fecha'] <= hoy]
    elif filtro == "Programados":
        planes = [r for r in planes if r['activo'] and r['proxima_fecha'] > hoy]
    elif filtro == "Pausados":
        planes = [r for r in planes if not r['activo']]
    return render_template("preventivos.html", planes=planes, activos=activos, filtro=filtro, hoy=hoy)


@app.route("/preventivos/nuevo", methods=["POST"])
def preventivo_nuevo():
    try:
        activo_id = int(request.form.get('activo_id', ''))
        frecuencia = int(request.form.get('frecuencia_dias', ''))
        proxima = date.fromisoformat(request.form.get('proxima_fecha', ''))
    except (ValueError, TypeError):
        flash('Selecciona un equipo, una frecuencia y una fecha válidos.', 'error')
        return redirect(url_for('preventivos'))
    titulo = request.form.get('titulo', '').strip()
    instrucciones = request.form.get('instrucciones', '').strip()
    tareas = [x.strip() for x in request.form.get('tareas', '').splitlines() if x.strip()]
    if not titulo or not (1 <= frecuencia <= 3650) or not (1 <= len(tareas) <= 20) or any(len(t)>250 for t in tareas):
        flash('Indica un título, una frecuencia de 1 a 3650 días y entre 1 y 20 tareas (máximo 250 caracteres cada una).', 'error')
        return redirect(url_for('preventivos'))
    with connect() as con:
        if not con.execute("SELECT id FROM activos WHERE id=? AND estado='Activo'", (activo_id,)).fetchone():
            flash('Selecciona un equipo activo.', 'error')
            return redirect(url_for('preventivos'))
        cur = con.execute("""INSERT INTO planes_preventivos
            (activo_id,titulo,instrucciones,frecuencia_dias,proxima_fecha,creado_por)
            VALUES (?,?,?,?,?,?)""", (activo_id,titulo,instrucciones,frecuencia,proxima.isoformat(),g.user['id']))
        con.executemany("INSERT INTO tareas_preventivas(plan_id,descripcion,orden) VALUES (?,?,?)",
                        [(cur.lastrowid,t,i) for i,t in enumerate(tareas,1)])
    flash('Mantenimiento preventivo programado.', 'success')
    return redirect(url_for('preventivo_detalle', pid=cur.lastrowid))


@app.route("/preventivos/<int:pid>")
def preventivo_detalle(pid):
    with connect() as con:
        plan = con.execute("""SELECT p.*,a.codigo,a.nombre AS activo_nombre FROM planes_preventivos p
            JOIN activos a ON a.id=p.activo_id WHERE p.id=?""",(pid,)).fetchone()
        if not plan: abort(404)
        tareas = con.execute("SELECT * FROM tareas_preventivas WHERE plan_id=? ORDER BY orden",(pid,)).fetchall()
        ejecuciones = con.execute("""SELECT e.*,u.nombre AS responsable_nombre,
            (SELECT COUNT(*) FROM resultados_preventivos r WHERE r.ejecucion_id=e.id) AS marcadas
            FROM ejecuciones_preventivas e LEFT JOIN usuarios u ON u.id=e.responsable_id
            WHERE e.plan_id=? ORDER BY e.id DESC LIMIT 40""",(pid,)).fetchall()
    return render_template('preventivo_detalle.html', plan=plan, tareas=tareas, ejecuciones=ejecuciones, hoy=date.today().isoformat())


@app.route("/preventivos/<int:pid>/estado", methods=["POST"])
def preventivo_estado(pid):
    valor = request.form.get('activo')
    if valor not in ('0','1'): abort(400)
    with connect() as con:
        if con.execute('UPDATE planes_preventivos SET activo=? WHERE id=?',(int(valor),pid)).rowcount == 0:
            abort(404)
    flash('Estado del plan actualizado.', 'success')
    return redirect(url_for('preventivo_detalle',pid=pid))


@app.route("/preventivos/<int:pid>/ejecutar", methods=["POST"])
def preventivo_ejecutar(pid):
    # Solo planes activos; checklist íntegro requerido para marcar ejecución completa.
    with connect() as con:
        plan = con.execute('SELECT * FROM planes_preventivos WHERE id=?',(pid,)).fetchone()
        if not plan: abort(404)
        if not plan['activo']:
            flash('No se puede ejecutar un plan pausado.', 'error')
            return redirect(url_for('preventivo_detalle',pid=pid))
        tareas = con.execute('SELECT id FROM tareas_preventivas WHERE plan_id=?',(pid,)).fetchall()
        ids = {str(t['id']) for t in tareas}
        marcados = request.form.getlist('tarea_id')
        if not ids or set(marcados) != ids or len(marcados) != len(ids):
            flash('Debes completar todas las tareas antes de cerrar el mantenimiento.', 'error')
            return redirect(url_for('preventivo_detalle',pid=pid))
        observaciones = request.form.get('observaciones','').strip()
        # Próxima ejecución desde hoy: evita acumular avisos vencidos tras una ejecución tardía.
        anterior = plan['proxima_fecha']
        siguiente = (date.today()+timedelta(days=plan['frecuencia_dias'])).isoformat()
        # Evita dos cierres del mismo período si dos personas guardan simultáneamente.
        actualizado = con.execute("""UPDATE planes_preventivos SET proxima_fecha=?
            WHERE id=? AND activo=1 AND proxima_fecha=?""", (siguiente,pid,anterior))
        if actualizado.rowcount != 1:
            flash('El plan cambió mientras lo completabas; vuelve a revisar.', 'error')
            return redirect(url_for('preventivo_detalle',pid=pid))
        cur = con.execute("""INSERT INTO ejecuciones_preventivas
            (plan_id,responsable_id,observaciones,fecha_anterior,fecha_siguiente)
            VALUES (?,?,?,?,?)""",(pid,g.user['id'],observaciones,anterior,siguiente))
        con.executemany('INSERT INTO resultados_preventivos(ejecucion_id,tarea_id) VALUES (?,?)',
                        [(cur.lastrowid,int(i)) for i in ids])
    flash('Checklist completado y próxima fecha actualizada.', 'success')
    return redirect(url_for('preventivo_detalle',pid=pid))


@app.route("/turnos", methods=["GET","POST"])
def turnos():
    if request.method == 'POST':
        resumen = request.form.get('resumen','').strip()
        pendientes = request.form.get('pendientes','').strip()
        turno = request.form.get('turno','')
        try:
            fecha = date.fromisoformat(request.form.get('fecha',''))
        except (ValueError, TypeError):
            fecha = None
        if not resumen or turno not in ('Mañana','Tarde','Noche') or not fecha:
            flash('Completa fecha, turno y resumen.', 'error')
        else:
            with connect() as con:
                con.execute('INSERT INTO entregas_turno(fecha,turno,resumen,pendientes,autor_id) VALUES (?,?,?,?,?)',
                            (fecha.isoformat(),turno,resumen,pendientes,g.user['id']))
            flash('Entrega de turno registrada.', 'success')
        return redirect(url_for('turnos'))
    with connect() as con:
        entregas = con.execute("""SELECT t.*,u.nombre AS autor_nombre FROM entregas_turno t
            LEFT JOIN usuarios u ON u.id=t.autor_id ORDER BY t.fecha DESC,t.id DESC LIMIT 100""").fetchall()
    return render_template('turnos.html',entregas=entregas,hoy=date.today().isoformat())


def _rango_reporte():
    """Valida fecha ISO estrictamente; fechas vacías equivalen a sin filtro."""
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    for valor in (desde, hasta):
        if valor:
            try:
                if date.fromisoformat(valor).isoformat() != valor:
                    abort(400)
            except ValueError:
                abort(400)
    if desde and hasta and desde > hasta:
        abort(400)
    return desde, hasta


def _report_data(desde, hasta):
    """Indicadores simples y auditables sin mutar la base de datos."""
    f = " AND (?='' OR v.fecha>=?) AND (?='' OR v.fecha<=?)"
    params = (desde, desde, hasta, hasta)
    with connect() as con:
        avisos = con.execute("""SELECT v.fecha, a.codigo, a.nombre, v.descripcion,
            v.prioridad, v.estado, o.id AS orden_id, o.estado AS orden_estado
            FROM avisos v JOIN activos a ON a.id=v.activo_id
            LEFT JOIN ordenes_trabajo o ON o.aviso_id=v.id
            WHERE 1=1""" + f + " ORDER BY v.fecha DESC, v.id DESC", params).fetchall()
        agrupado = con.execute("""SELECT v.prioridad, COUNT(*) AS total
            FROM avisos v WHERE 1=1""" + f +
            " GROUP BY v.prioridad", params).fetchall()
        # Las órdenes se incluyen según la fecha del aviso que las originó.
        estados = con.execute("""SELECT o.estado, COUNT(*) AS total
            FROM ordenes_trabajo o JOIN avisos v ON v.id=o.aviso_id
            WHERE 1=1""" + f + " GROUP BY o.estado", params).fetchall()
        preventivos = con.execute("""SELECT COUNT(*) FROM planes_preventivos
            WHERE activo=1 AND proxima_fecha < ?""", (date.today().isoformat(),)).fetchone()[0]
        stock_bajo = con.execute("""SELECT COUNT(*) FROM repuestos
            WHERE stock <= stock_minimo""").fetchone()[0]
        activos = con.execute("SELECT COUNT(*) FROM activos WHERE estado='Activo'").fetchone()[0]
    conteo_estados = {r['estado']: r['total'] for r in estados}
    return {
        'avisos': avisos,
        'total_avisos': len(avisos),
        'total_ordenes': sum(conteo_estados.values()),
        'pendientes': conteo_estados.get('Pendiente', 0),
        'en_progreso': conteo_estados.get('En progreso', 0),
        'finalizadas': conteo_estados.get('Finalizada', 0),
        'prioridades': {r['prioridad']: r['total'] for r in agrupado},
        'preventivos_vencidos': preventivos,
        'repuestos_bajos': stock_bajo,
        'activos': activos,
    }


@app.route('/reportes')
def reportes():
    desde, hasta = _rango_reporte()
    data = _report_data(desde, hasta)
    return render_template('reportes.html', datos=data, desde=desde, hasta=hasta)


def _celda_csv(valor):
    """Evita interpretación de fórmulas al abrir un CSV con Excel."""
    texto = str(valor if valor is not None else '')
    if texto.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + texto
    return texto


@app.route('/reportes/exportar.csv')
def exportar_reporte():
    desde, hasta = _rango_reporte()
    datos = _report_data(desde, hasta)
    salida = StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(['Fecha aviso', 'Código activo', 'Activo', 'Descripción',
                       'Prioridad', 'Estado aviso', 'Orden', 'Estado orden'])
    for r in datos['avisos']:
        escritor.writerow([_celda_csv(v) for v in (r['fecha'], r['codigo'], r['nombre'],
            r['descripcion'], r['prioridad'], r['estado'], r['orden_id'], r['orden_estado'])])
    # UTF-8 BOM mejora la lectura de acentos en Excel para Windows.
    return Response('\ufeff' + salida.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="sigam_reporte_avisos.csv"',
                             'Cache-Control': 'no-store'})


@app.route("/historial")
def historial():
    q = request.args.get("q","").strip()
    with connect() as con:
        rows = con.execute("""SELECT a.id,a.codigo,a.nombre,a.ubicacion,COUNT(v.id) AS total
            FROM activos a LEFT JOIN avisos v ON v.activo_id=a.id
            WHERE a.codigo LIKE ? OR a.nombre LIKE ? OR a.ubicacion LIKE ?
            GROUP BY a.id ORDER BY a.codigo""", (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    return render_template("historial.html", activos=rows, q=q)

@app.route("/prueba", methods=["GET", "POST"])
def prueba():
    with connect() as con:
        if request.method == "POST":
            accion = request.form.get("accion")
            if accion == "iniciar_prueba":
                inicio = date.today()
                fin = inicio + timedelta(days=14)
                con.execute("""INSERT INTO suscripcion(id,plan,estado,inicio,fin_prueba,precio_clp)
                    VALUES(1,'Prueba gratuita','En prueba',?,?,0)
                    ON CONFLICT(id) DO UPDATE SET plan='Prueba gratuita',estado='En prueba',
                    inicio=excluded.inicio,fin_prueba=excluded.fin_prueba,precio_clp=0""",
                    (inicio.isoformat(), fin.isoformat()))
                flash("Tu prueba gratuita de 14 días está activa en esta demostración.", "success")
            elif accion == "seleccionar_plan":
                plan = request.form.get("plan")
                precios = {"Básico": 19990, "Pyme": 39990}
                if plan not in precios:
                    abort(400)
                con.execute("""INSERT INTO suscripcion(id,plan,estado,precio_clp)
                    VALUES(1,?,'Pendiente de contratación',?)
                    ON CONFLICT(id) DO UPDATE SET plan=excluded.plan,estado='Pendiente de contratación',
                    precio_clp=excluded.precio_clp,inicio=NULL,fin_prueba=NULL""", (plan,precios[plan]))
                flash("Plan seleccionado. Esta demostración no realiza cobros.", "success")
            elif accion == "guardar_prueba":
                participante = request.form.get("participante", "").strip()
                dificultad = request.form.get("dificultad", "").strip()
                try:
                    duracion = int(request.form.get("duracion", "0"))
                except ValueError:
                    duracion = 0
                completo = 1 if request.form.get("completo") == "si" else 0
                if not participante or duracion < 0:
                    flash("Indica un participante y una duración válida.", "error")
                else:
                    con.execute("INSERT INTO pruebas_usabilidad(participante,completo,duracion_segundos,dificultad) VALUES(?,?,?,?)",
                                (participante,completo,duracion,dificultad))
                    flash("Resultado de prueba de usabilidad guardado.", "success")
            return redirect(url_for("prueba"))
        suscripcion = con.execute("SELECT * FROM suscripcion WHERE id=1").fetchone()
        if suscripcion and suscripcion["estado"] == "En prueba" and suscripcion["fin_prueba"] < date.today().isoformat():
            con.execute("UPDATE suscripcion SET estado='Prueba finalizada' WHERE id=1")
            suscripcion = con.execute("SELECT * FROM suscripcion WHERE id=1").fetchone()
        pruebas = con.execute("SELECT * FROM pruebas_usabilidad ORDER BY id DESC LIMIT 8").fetchall()
    dias_restantes = None
    if suscripcion and suscripcion["estado"] == "En prueba":
        dias_restantes = max(0, (date.fromisoformat(suscripcion["fin_prueba"]) - date.today()).days)
    return render_template("prueba.html", suscripcion=suscripcion, dias_restantes=dias_restantes, pruebas=pruebas)


if __name__ == "__main__":
    init_db()
    # 0.0.0.0 permite que otros dispositivos de la LAN lleguen al servidor.
    # No publicar este servidor de demostración directamente en Internet.
    host = os.environ.get("SIGAM_HOST", "0.0.0.0")
    port = int(os.environ.get("SIGAM_PORT", "5000"))
    app.run(host=host, port=port, debug=False, threaded=True)
