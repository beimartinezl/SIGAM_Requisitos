"""SIGAM v4.7: panel de indicadores, filtros, CSV y permisos."""
from datetime import date, timedelta
import csv
from io import StringIO
import pytest
import app as sigam


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sigam, 'DB', tmp_path / 'pruebas_reportes.db')
    sigam.app.config.update(TESTING=True, SECRET_KEY='pruebas', WTF_CSRF_ENABLED=False)
    sigam.init_db()
    with sigam.app.test_client() as c:
        c.post('/configurar', data={'username':'admin', 'nombre':'Administrador',
                                    'password':'ClaveSegura123','confirm':'ClaveSegura123'})
        c.post('/usuarios', data={'username':'worker','nombre':'Técnico',
                                  'password':'ClaveSegura123','rol':'Trabajador'})
        c.post('/usuarios', data={'username':'super','nombre':'Supervisor',
                                  'password':'ClaveSegura123','rol':'Supervisor'})
        c.post('/activos/nuevo', data={'codigo':'EQ-01','nombre':'Bomba', 'ubicacion':'Planta'})
        yield c


def crear_aviso(c, fecha=None, desc='Falla de bomba', prioridad='Alta'):
    c.post('/avisos/nuevo', data={'activo_id':'1','descripcion':desc,
                                  'fecha': fecha or date.today().isoformat(), 'prioridad':prioridad})


def test_dashboard_renders_without_data(client):
    respuesta=client.get('/reportes')
    assert respuesta.status_code==200
    assert 'Indicadores y reportes' in respuesta.get_data(as_text=True)
    assert 'No hay avisos' in respuesta.get_data(as_text=True)


def test_counts_orders_and_priorities(client):
    crear_aviso(client)
    client.post('/avisos/1/orden')
    pagina=client.get('/reportes').get_data(as_text=True)
    assert 'Falla de bomba' in pagina
    assert 'OT-1' in pagina
    assert 'Alta:' in pagina
    assert 'Órdenes generadas' in pagina


def test_date_filters_only_selected_alerts(client):
    crear_aviso(client, fecha='2026-01-10', desc='Primer aviso')
    crear_aviso(client, fecha='2026-03-10', desc='Segundo aviso')
    r=client.get('/reportes?desde=2026-03-01&hasta=2026-03-31')
    html=r.get_data(as_text=True)
    assert 'Segundo aviso' in html
    assert 'Primer aviso' not in html


def test_invalid_date_and_inverted_range_rejected(client):
    assert client.get('/reportes?desde=2026-13-90').status_code==400
    assert client.get('/reportes/exportar.csv?desde=2026-03-10&hasta=2026-01-01').status_code==400


def test_csv_export_has_bom_headers_and_rows(client):
    crear_aviso(client, desc='Fuga de agua')
    r=client.get('/reportes/exportar.csv')
    assert r.status_code==200
    assert r.data.startswith(b'\xef\xbb\xbf')
    assert 'attachment' in r.headers['Content-Disposition']
    reader=csv.reader(StringIO(r.get_data(as_text=True).lstrip('\ufeff')),delimiter=';')
    filas=list(reader)
    assert filas[0][0]=='Fecha aviso'
    assert filas[1][3]=='Fuga de agua'


def test_csv_escapes_spreadsheet_formula(client):
    crear_aviso(client,desc='=1+1')
    r=client.get('/reportes/exportar.csv')
    filas=list(csv.reader(StringIO(r.get_data(as_text=True).lstrip('\ufeff')),delimiter=';'))
    assert filas[1][3]=="'=1+1"


def test_worker_denied_reports_and_supervisor_allowed(client):
    client.post('/logout')
    client.post('/login', data={'username':'worker','password':'ClaveSegura123'})
    assert client.get('/reportes').status_code==403
    assert client.get('/reportes/exportar.csv').status_code==403
    client.post('/logout')
    client.post('/login', data={'username':'super','password':'ClaveSegura123'})
    assert client.get('/reportes').status_code==200


def test_no_db_change_after_render_and_export(client):
    crear_aviso(client)
    with sigam.connect() as con:
        anterior=con.execute('SELECT COUNT(*) FROM avisos').fetchone()[0]
    client.get('/reportes')
    client.get('/reportes/exportar.csv')
    with sigam.connect() as con:
        despues=con.execute('SELECT COUNT(*) FROM avisos').fetchone()[0]
    assert anterior==despues
