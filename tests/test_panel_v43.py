import sys
import sqlite3
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import GESTION_BD
import SERVIDOR_SIGAM

def test_servidor_lan_por_defecto(monkeypatch):
    monkeypatch.delenv('SIGAM_BIND_LAN',raising=False)
    monkeypatch.delenv('SIGAM_PORT',raising=False)
    assert SERVIDOR_SIGAM.configuracion_servidor()==('0.0.0.0',5000)

def test_servidor_local(monkeypatch):
    monkeypatch.setenv('SIGAM_BIND_LAN','0')
    monkeypatch.setenv('SIGAM_PORT','5077')
    assert SERVIDOR_SIGAM.configuracion_servidor()==('127.0.0.1',5077)

def test_puerto_invalido(monkeypatch):
    monkeypatch.setenv('SIGAM_PORT','65536')
    try: SERVIDOR_SIGAM.configuracion_servidor()
    except ValueError: pass
    else: assert False, 'Debe rechazar un puerto fuera de rango'

def test_respaldo_y_reinicio_preservan_copia(tmp_path):
    db=tmp_path/'sigam.db'
    backups=tmp_path/'respaldos'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE ejemplo(valor TEXT)')
        con.execute('INSERT INTO ejemplo VALUES (?)',('dato del sprint 1',))
    copia=GESTION_BD.respaldar(db,backups)
    assert copia.exists()
    with sqlite3.connect(copia) as con:
        assert con.execute('SELECT valor FROM ejemplo').fetchone()[0]=='dato del sprint 1'
    segunda=GESTION_BD.reiniciar(db,backups)
    assert segunda.exists() and not db.exists()
    with sqlite3.connect(segunda) as con:
        assert con.execute('SELECT valor FROM ejemplo').fetchone()[0]=='dato del sprint 1'

def test_reiniciar_sin_base(tmp_path):
    assert GESTION_BD.reiniciar(tmp_path/'sin.db',tmp_path/'backups') is None
    assert not (tmp_path/'backups').exists()

def test_errores_de_respaldo_no_generan_base(tmp_path):
    db=tmp_path/'no_existe.db'
    try: GESTION_BD.respaldar(db,tmp_path/'backups')
    except FileNotFoundError: pass
    else: assert False
    assert not db.exists()
