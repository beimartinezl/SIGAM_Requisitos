"""Pruebas SIGAM v4.6: planes preventivos, checklist y entregas de turno."""
from datetime import date, timedelta
import pytest
import app as sigam


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sigam, 'DB', tmp_path / 'sigam_test.db')
    sigam.app.config.update(TESTING=True, SECRET_KEY='test', WTF_CSRF_ENABLED=False)
    sigam.init_db()
    with sigam.app.test_client() as c:
        c.post('/configurar', data={'username':'admin','nombre':'Administrador','password':'ClaveSegura123','confirm':'ClaveSegura123'})
        c.post('/usuarios', data={'username':'worker','nombre':'Técnico','password':'ClaveSegura123','rol':'Trabajador'})
        c.post('/activos/nuevo', data={'codigo':'EQ-01','nombre':'Motor','ubicacion':'Taller'})
        yield c


def crear_plan(c, tareas='Revisar filtro\nRevisar correa', frecuencia='30', fecha=None):
    return c.post('/preventivos/nuevo', data={
        'activo_id':'1','titulo':'Revisión mensual','instrucciones':'Desconectar equipo',
        'frecuencia_dias':frecuencia,'proxima_fecha':fecha or date.today().isoformat(),'tareas':tareas})


def test_admin_creates_preventive_plan_and_checklist(client):
    assert crear_plan(client).status_code == 302
    with sigam.connect() as con:
        r=con.execute('SELECT titulo,frecuencia_dias FROM planes_preventivos').fetchone()
        assert tuple(r)==('Revisión mensual',30)
        assert con.execute('SELECT COUNT(*) FROM tareas_preventivas').fetchone()[0] == 2


def test_invalid_frequency_and_empty_checklist_rejected(client):
    crear_plan(client, frecuencia='0')
    crear_plan(client, tareas='\n\n')
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM planes_preventivos').fetchone()[0]==0


def test_worker_cannot_create_or_pause_plan(client):
    crear_plan(client)
    client.post('/logout')
    client.post('/login',data={'username':'worker','password':'ClaveSegura123'})
    assert crear_plan(client).status_code == 403
    assert client.post('/preventivos/1/estado',data={'activo':'0'}).status_code == 403


def test_all_checklist_items_required(client):
    crear_plan(client)
    client.post('/preventivos/1/ejecutar', data={'tarea_id':['1'],'observaciones':'Incompleto'})
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM ejecuciones_preventivas').fetchone()[0] == 0


def test_completed_plan_updates_next_date_and_audits(client):
    crear_plan(client,frecuencia='10')
    client.post('/preventivos/1/ejecutar',data={'tarea_id':['1','2'],'observaciones':'Todo correcto'})
    with sigam.connect() as con:
        plan=con.execute('SELECT proxima_fecha FROM planes_preventivos').fetchone()
        assert plan['proxima_fecha']==(date.today()+timedelta(days=10)).isoformat()
        reg=con.execute('SELECT responsable_id,observaciones FROM ejecuciones_preventivas').fetchone()
        assert tuple(reg)==(1,'Todo correcto')
        assert con.execute('SELECT COUNT(*) FROM resultados_preventivos').fetchone()[0]==2


def test_paused_plan_blocks_execution_and_can_reactivate(client):
    crear_plan(client)
    client.post('/preventivos/1/estado',data={'activo':'0'})
    client.post('/preventivos/1/ejecutar',data={'tarea_id':['1','2']})
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM ejecuciones_preventivas').fetchone()[0]==0
    client.post('/preventivos/1/estado',data={'activo':'1'})
    client.post('/preventivos/1/ejecutar',data={'tarea_id':['1','2']})
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM ejecuciones_preventivas').fetchone()[0]==1


def test_due_filter_shows_overdue_and_excludes_future(client):
    crear_plan(client, fecha=(date.today()-timedelta(days=2)).isoformat())
    crear_plan(client, fecha=(date.today()+timedelta(days=5)).isoformat())
    response=client.get('/preventivos?filtro=Pendientes')
    text=response.get_data(as_text=True)
    assert response.status_code==200
    assert text.count('Abrir →')==1


def test_worker_can_complete_checklist(client):
    crear_plan(client)
    client.post('/logout')
    client.post('/login',data={'username':'worker','password':'ClaveSegura123'})
    assert client.post('/preventivos/1/ejecutar',data={'tarea_id':['1','2']}).status_code==302
    with sigam.connect() as con:
        assert con.execute('SELECT responsable_id FROM ejecuciones_preventivas').fetchone()[0]==2


def test_shift_handover_saved_with_author(client):
    r=client.post('/turnos',data={'fecha':date.today().isoformat(),'turno':'Noche','resumen':'Inspección','pendientes':'Revisar bomba'})
    assert r.status_code == 302
    with sigam.connect() as con:
        item=con.execute('SELECT turno,resumen,pendientes,autor_id FROM entregas_turno').fetchone()
        assert tuple(item)==('Noche','Inspección','Revisar bomba',1)
    assert 'Revisar bomba' in client.get('/turnos').get_data(as_text=True)


def test_invalid_shift_rejected(client):
    client.post('/turnos',data={'fecha':date.today().isoformat(),'turno':'Desconocido','resumen':'Informe'})
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM entregas_turno').fetchone()[0]==0


def test_repeated_init_db_keeps_existing_plans(client):
    crear_plan(client)
    sigam.init_db()
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM planes_preventivos').fetchone()[0]==1
        assert con.execute('SELECT COUNT(*) FROM tareas_preventivas').fetchone()[0]==2


def test_preventive_and_shift_pages_render(client):
    crear_plan(client)
    for path in ('/preventivos','/preventivos/1','/turnos','/'):
        assert client.get(path).status_code==200
