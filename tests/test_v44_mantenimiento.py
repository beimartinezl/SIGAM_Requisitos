"""Pruebas de asignaciones, intervenciones y verificación de retorno (v4.4)."""
import pytest
import app as sigam


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sigam, 'DB', tmp_path / 'sigam_test.db')
    sigam.app.config.update(TESTING=True, SECRET_KEY='clave-prueba', WTF_CSRF_ENABLED=False)
    sigam.init_db()
    with sigam.app.test_client() as c:
        c.post('/configurar', data={
            'username': 'admin', 'nombre': 'Admin',
            'password': 'ClaveSegura123', 'confirm': 'ClaveSegura123'
        })
        c.post('/usuarios', data={
            'username': 'tecnico', 'nombre': 'Técnico 1',
            'password': 'ClaveSegura123', 'rol': 'Trabajador'
        })
        c.post('/activos/nuevo', data={
            'codigo': 'EQ-001', 'nombre': 'Compresor',
            'categoria': 'Equipo', 'ubicacion': 'Planta 1'
        })
        c.post('/avisos/nuevo', data={
            'activo_id': '1', 'descripcion': 'Falla de prueba',
            'prioridad': 'Alta', 'fecha': '2026-11-23'
        })
        c.post('/avisos/1/orden')
        yield c


def test_admin_assigns_worker_and_records_history(client):
    r = client.post('/ordenes/1/asignar', data={'usuario_id': '2', 'observacion': 'Turno mañana'})
    assert r.status_code == 302
    with sigam.connect() as con:
        assert con.execute('SELECT asignado_a FROM ordenes_trabajo WHERE id=1').fetchone()[0] == 2
        row = con.execute('SELECT observacion,asignado_por FROM historial_asignaciones WHERE orden_id=1').fetchone()
        assert row['observacion'] == 'Turno mañana'
        assert row['asignado_por'] == 1


def test_invalid_or_inactive_worker_is_rejected(client):
    client.post('/ordenes/1/asignar', data={'usuario_id': '999'}, follow_redirects=True)
    with sigam.connect() as con:
        assert con.execute('SELECT asignado_a FROM ordenes_trabajo WHERE id=1').fetchone()[0] is None


def test_worker_cannot_assign_or_verify_return(client):
    client.post('/logout')
    client.post('/login', data={'username': 'tecnico', 'password': 'ClaveSegura123'})
    assert client.post('/ordenes/1/asignar', data={'usuario_id': '2'}).status_code == 403
    assert client.post('/ordenes/1/prueba-retorno', data={'resultado': 'Aprobada'}).status_code == 403


def test_intervention_stores_times_and_result(client):
    response = client.post('/ordenes/1/intervencion', data={
        'descripcion': 'Cambio de correa', 'fecha': '2026-11-23',
        'responsable': 'Técnico 1', 'hora_inicio': '09:00',
        'hora_fin': '10:30', 'resultado': 'Resuelto'
    })
    assert response.status_code == 302
    with sigam.connect() as con:
        row = con.execute('SELECT hora_inicio,hora_fin,resultado FROM intervenciones').fetchone()
    assert tuple(row) == ('09:00', '10:30', 'Resuelto')


def test_invalid_intervention_times_rejected(client):
    client.post('/ordenes/1/intervencion', data={
        'descripcion': 'Prueba', 'responsable': 'Técnico 1',
        'hora_inicio': '11:00', 'hora_fin': '10:00'
    })
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM intervenciones').fetchone()[0] == 0


def test_return_verification_is_saved(client):
    assert client.post('/ordenes/1/prueba-retorno', data={
        'resultado': 'Aprobada', 'observaciones': 'Equipo funcionando'
    }).status_code == 302
    with sigam.connect() as con:
        row = con.execute('SELECT prueba_retorno,observaciones_retorno FROM ordenes_trabajo WHERE id=1').fetchone()
    assert tuple(row) == ('Aprobada', 'Equipo funcionando')


def test_order_page_displays_assignment_and_interventions(client):
    assert client.get('/ordenes/1').status_code == 200
    client.post('/ordenes/1/asignar', data={'usuario_id': '2'})
    html = client.get('/ordenes/1').get_data(as_text=True)
    assert 'Técnico 1' in html
    assert 'Historial de asignaciones' in html
