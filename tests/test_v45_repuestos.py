"""Pruebas de catálogo, entradas y consumo de repuestos (SIGAM v4.5)."""
import pytest
import app as sigam


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sigam, 'DB', tmp_path / 'sigam_test.db')
    sigam.app.config.update(TESTING=True, SECRET_KEY='test', WTF_CSRF_ENABLED=False)
    sigam.init_db()
    with sigam.app.test_client() as c:
        c.post('/configurar', data={'username': 'admin', 'nombre': 'Admin', 'password': 'ClaveSegura123', 'confirm': 'ClaveSegura123'})
        c.post('/usuarios', data={'username': 'tecnico', 'nombre': 'Técnico', 'password': 'ClaveSegura123', 'rol': 'Trabajador'})
        c.post('/activos/nuevo', data={'codigo': 'EQ-001', 'nombre': 'Compresor', 'ubicacion': 'Planta 1'})
        c.post('/avisos/nuevo', data={'activo_id': '1', 'descripcion': 'Falla', 'prioridad': 'Alta'})
        c.post('/avisos/1/orden')
        yield c


def create_part(client):
    assert client.post('/repuestos/nuevo', data={
        'codigo': 'R-001', 'nombre': 'Correa', 'unidad': 'unidad', 'stock_minimo': '2'}).status_code == 302


def test_create_part_starts_with_zero_stock(client):
    create_part(client)
    with sigam.connect() as con:
        r = con.execute('SELECT stock,stock_minimo FROM repuestos WHERE codigo=?', ('R-001',)).fetchone()
        assert tuple(r) == (0, 2)


def test_reject_duplicate_code_case_insensitive(client):
    create_part(client)
    client.post('/repuestos/nuevo', data={'codigo': 'r-001', 'nombre': 'Duplicado', 'unidad': 'unidad', 'stock_minimo': '0'})
    with sigam.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM repuestos').fetchone()[0] == 1


def test_entry_updates_stock_and_audit(client):
    create_part(client)
    assert client.post('/repuestos/1/entrada', data={'cantidad': '10', 'observacion': 'Compra inicial'}).status_code == 302
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos WHERE id=1').fetchone()[0] == 10
        row = con.execute('SELECT tipo,cantidad,usuario_id,observacion FROM movimientos_repuestos').fetchone()
        assert tuple(row) == ('Entrada', 10, 1, 'Compra inicial')


def test_invalid_entry_does_not_change_stock(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '-4'})
    client.post('/repuestos/1/entrada', data={'cantidad': '1.5'})
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM movimientos_repuestos').fetchone()[0] == 0


def test_consumption_decrements_stock_and_links_order(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '9'})
    assert client.post('/ordenes/1/consumir', data={'repuesto_id': '1', 'cantidad': '4', 'observacion': 'Sustitución'}).status_code == 302
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 5
        row = con.execute("SELECT orden_id,tipo,cantidad FROM movimientos_repuestos WHERE tipo='Consumo'").fetchone()
        assert tuple(row) == (1, 'Consumo', 4)


def test_insufficient_stock_does_not_register_consumption(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '3'})
    client.post('/ordenes/1/consumir', data={'repuesto_id': '1', 'cantidad': '4'})
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM movimientos_repuestos WHERE tipo='Consumo'").fetchone()[0] == 0


def test_worker_cannot_create_or_add_stock(client):
    client.post('/logout')
    client.post('/login', data={'username': 'tecnico', 'password': 'ClaveSegura123'})
    assert client.post('/repuestos/nuevo', data={'codigo': 'XX', 'nombre': 'X', 'unidad': 'unidad', 'stock_minimo': '0'}).status_code == 403
    assert client.post('/repuestos/1/entrada', data={'cantidad': '10'}).status_code == 403


def test_worker_must_be_assigned_to_consume(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '10'})
    client.post('/logout')
    client.post('/login', data={'username': 'tecnico', 'password': 'ClaveSegura123'})
    assert client.post('/ordenes/1/consumir', data={'repuesto_id': '1', 'cantidad': '1'}).status_code == 403
    client.post('/logout')
    client.post('/login', data={'username': 'admin', 'password': 'ClaveSegura123'})
    client.post('/ordenes/1/asignar', data={'usuario_id': '2'})
    client.post('/logout')
    client.post('/login', data={'username': 'tecnico', 'password': 'ClaveSegura123'})
    assert client.post('/ordenes/1/consumir', data={'repuesto_id': '1', 'cantidad': '2'}).status_code == 302
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 8


def test_finalized_order_refuses_consumption(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '5'})
    client.post('/ordenes/1', data={'estado': 'Finalizada'})
    client.post('/ordenes/1/consumir', data={'repuesto_id': '1', 'cantidad': '1'})
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 5


def test_inventory_and_order_pages_render(client):
    create_part(client)
    assert client.get('/repuestos').status_code == 200
    assert 'Stock bajo' in client.get('/repuestos').get_data(as_text=True)
    assert client.get('/repuestos/movimientos').status_code == 200
    assert 'Repuestos utilizados' in client.get('/ordenes/1').get_data(as_text=True)


def test_repeated_init_db_preserves_stock(client):
    create_part(client)
    client.post('/repuestos/1/entrada', data={'cantidad': '5'})
    sigam.init_db()
    with sigam.connect() as con:
        assert con.execute('SELECT stock FROM repuestos').fetchone()[0] == 5
