from flask import Flask, render_template, request, redirect, url_for, flash, abort, session, g
import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from pathlib import Path
from datetime import date, timedelta

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
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS intervenciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_id INTEGER NOT NULL REFERENCES ordenes_trabajo(id),
            descripcion TEXT NOT NULL,
            fecha TEXT NOT NULL,
            responsable TEXT NOT NULL
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
    supervisor_or_admin = {"activo_form", "desactivar_activo", "crear_orden"}
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
    return render_template("activo_detalle.html", activo=activo, avisos=avisos)

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

@app.route("/ordenes/<int:oid>", methods=["GET","POST"])
def orden_detalle(oid):
    with connect() as con:
        orden = con.execute("""SELECT o.*, v.fecha AS fecha_aviso, v.descripcion AS falla,
            a.codigo, a.nombre AS activo_nombre FROM ordenes_trabajo o
            JOIN avisos v ON v.id=o.aviso_id JOIN activos a ON a.id=v.activo_id WHERE o.id=?""", (oid,)).fetchone()
        if not orden: abort(404)
        if request.method == "POST":
            estado = request.form.get("estado")
            if estado not in ("Pendiente","En progreso","Finalizada"): abort(400)
            con.execute("UPDATE ordenes_trabajo SET estado=? WHERE id=?", (estado,oid))
            flash("Estado de la orden actualizado.", "success")
            return redirect(url_for("orden_detalle", oid=oid))
        intervenciones = con.execute("SELECT * FROM intervenciones WHERE orden_id=? ORDER BY id DESC", (oid,)).fetchall()
    return render_template("orden_detalle.html", orden=orden, intervenciones=intervenciones, hoy=date.today().isoformat())

@app.route("/ordenes/<int:oid>/intervencion", methods=["POST"])
def intervencion_nueva(oid):
    descripcion = request.form.get("descripcion","").strip()
    fecha = request.form.get("fecha") or date.today().isoformat()
    responsable = request.form.get("responsable","").strip()
    if not descripcion or not responsable:
        flash("Completa la descripción y el responsable.", "error")
    else:
        with connect() as con:
            exists = con.execute("SELECT id FROM ordenes_trabajo WHERE id=?", (oid,)).fetchone()
            if not exists: abort(404)
            con.execute("INSERT INTO intervenciones(orden_id,descripcion,fecha,responsable) VALUES(?,?,?,?)",
                        (oid,descripcion,fecha,responsable))
            flash("Intervención registrada.", "success")
    return redirect(url_for("orden_detalle", oid=oid))

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
