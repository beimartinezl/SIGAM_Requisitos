from flask import Flask, render_template, request, redirect, url_for, flash, abort
import sqlite3
from pathlib import Path
from datetime import date

app = Flask(__name__)
app.secret_key = "sigam-demo-local"
DB = Path(__file__).with_name("sigam.db")

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    with connect() as con:
        con.executescript("""
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
        """)

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

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
