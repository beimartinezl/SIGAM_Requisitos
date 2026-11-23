from io import BytesIO
import pytest
import app as sigam
from openpyxl import Workbook

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sigam, 'DB', tmp_path / 'sigam_test.db')
    sigam.app.config.update(TESTING=True, SECRET_KEY='test-secret', WTF_CSRF_ENABLED=False)
    sigam.init_db()
    with sigam.app.test_client() as client:
        password = 'ClaveSegura123'
        client.post('/configurar', data={'username':'admin','nombre':'Admin','password':password,'confirm':password})
        yield client

def xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(['codigo','nombre','categoria','ubicacion'])
    for row in rows:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out

def test_admin_can_download_template(client):
    response = client.get('/activos/plantilla.xlsx')
    assert response.status_code == 200
    assert response.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def test_admin_imports_valid_assets(client):
    response = client.post('/activos/importar', data={'archivo':(xlsx([
        ['EQ-101','Bomba','Equipo','Planta 1'], ['EQ-102','Motor','Equipo','Planta 2']
    ]),'activos.xlsx')}, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert '2 activo(s) incorporado(s)' in response.get_data(as_text=True)
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM activos').fetchone()[0] == 2

def test_import_skips_existing_and_duplicate_codes(client):
    client.post('/activos/nuevo', data={'codigo':'EQ-1','nombre':'Existente','categoria':'Equipo','ubicacion':'P1'})
    response = client.post('/activos/importar', data={'archivo':(xlsx([
        ['EQ-1','Duplicado DB','Equipo','P1'], ['EQ-2','Nuevo','Equipo','P2'], ['EQ-2','Duplicado archivo','Equipo','P3']
    ]),'activos.xlsx')}, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert '1 activo(s) incorporado(s)' in response.get_data(as_text=True)
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM activos').fetchone()[0] == 2

def test_import_rejects_missing_required_values(client):
    response = client.post('/activos/importar', data={'archivo':(xlsx([
        ['EQ-1','','Equipo','P1']
    ]),'activos.xlsx')}, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert 'se omitieron' in response.get_data(as_text=True).lower()
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM activos').fetchone()[0] == 0

def test_worker_is_forbidden_from_import(client):
    client.post('/usuarios', data={'username':'trabajador','nombre':'Trabajador','password':'ClaveSegura123','rol':'Trabajador'})
    client.post('/logout')
    client.post('/login', data={'username':'trabajador','password':'ClaveSegura123'})
    assert client.get('/activos/importar').status_code == 403
    assert client.post('/activos/importar').status_code == 403
