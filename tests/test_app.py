import pytest
import app as sigam

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test_sigam.db"
    monkeypatch.setattr(sigam, "DB", db)
    sigam.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    sigam.init_db()
    with sigam.app.test_client() as client:
        yield client

def crear_activo(client, codigo="EQ-001", nombre="Bomba de agua"):
    return client.post("/activos/nuevo", data={"codigo": codigo, "nombre": nombre, "categoria": "Equipo", "ubicacion": "Planta 1"}, follow_redirects=True)

def crear_aviso(client, descripcion="Vibración anormal"):
    return client.post("/avisos/nuevo", data={"activo_id": "1", "descripcion": descripcion, "fecha": "2026-11-22", "prioridad": "Alta"}, follow_redirects=True)

def test_inicio_y_paginas_principales(client):
    for path in ["/", "/activos", "/avisos", "/ordenes", "/historial", "/prueba"]:
        assert client.get(path).status_code == 200, path

def test_registrar_y_buscar_activo(client):
    response = crear_activo(client)
    assert response.status_code == 200
    assert "EQ-001" in response.get_data(as_text=True)
    assert client.get("/activos?q=EQ-001").status_code == 200

def test_no_permite_activo_sin_campos_obligatorios(client):
    response = client.post("/activos/nuevo", data={"codigo": "", "nombre": "", "ubicacion": ""}, follow_redirects=True)
    assert response.status_code == 200
    assert "Completa código, nombre y ubicación." in response.get_data(as_text=True)

def test_no_permite_codigo_duplicado(client):
    crear_activo(client)
    response = crear_activo(client, codigo="EQ-001", nombre="Otro equipo")
    assert "Ese código ya existe" in response.get_data(as_text=True)

def test_editar_y_desactivar_activo(client):
    crear_activo(client)
    response = client.post("/activos/1/editar", data={"codigo": "EQ-001", "nombre": "Bomba editada", "categoria": "Equipo", "ubicacion": "Planta 2", "estado": "Activo"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Bomba editada" in response.get_data(as_text=True)
    assert client.post("/activos/1/desactivar", follow_redirects=True).status_code == 200
    with sigam.connect() as con:
        row = con.execute("SELECT estado FROM activos WHERE id=1").fetchone()
    assert row["estado"] == "Inactivo"

def test_flujo_aviso_orden_intervencion_y_estado(client):
    crear_activo(client)
    crear_aviso(client)
    response = client.post("/avisos/1/orden", follow_redirects=True)
    assert response.status_code == 200
    with sigam.connect() as con:
        orden = con.execute("SELECT id, estado FROM ordenes_trabajo").fetchone()
    assert orden["estado"] == "Pendiente"
    response = client.post(f"/ordenes/{orden['id']}/intervencion", data={"descripcion": "Ajuste realizado", "fecha": "2026-11-22", "responsable": "Técnico 1"}, follow_redirects=True)
    assert response.status_code == 200
    with sigam.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM intervenciones").fetchone()[0] == 1
    response = client.post(f"/ordenes/{orden['id']}", data={"estado": "En progreso"}, follow_redirects=True)
    assert response.status_code == 200
    with sigam.connect() as con:
        assert con.execute("SELECT estado FROM ordenes_trabajo").fetchone()["estado"] == "En progreso"

def test_no_permite_estado_de_orden_invalido(client):
    crear_activo(client)
    crear_aviso(client)
    client.post("/avisos/1/orden", follow_redirects=True)
    assert client.post("/ordenes/1", data={"estado": "Cualquier estado"}).status_code == 400

def test_no_permite_aviso_sin_descripcion_o_activo(client):
    response = client.post("/avisos/nuevo", data={"activo_id": "", "descripcion": ""}, follow_redirects=True)
    assert response.status_code == 200
    assert "Selecciona un activo e ingresa una descripción." in response.get_data(as_text=True)

def test_rutas_inexistentes_responden_404(client):
    assert client.get("/activos/99999").status_code == 404
    assert client.get("/ordenes/99999").status_code == 404

def test_registro_de_resultado_de_usabilidad(client):
    response = client.post("/prueba", data={"accion": "guardar_prueba", "participante": "P1", "duracion": "95", "completo": "si", "dificultad": "Ninguna"}, follow_redirects=True)
    assert response.status_code == 200
    with sigam.connect() as con:
        row = con.execute("SELECT participante, completo, duracion_segundos FROM pruebas_usabilidad").fetchone()
    assert (row["participante"], row["completo"], row["duracion_segundos"]) == ("P1", 1, 95)
