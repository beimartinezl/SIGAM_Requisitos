"""Panel local (Windows) para SIGAM v4.8. La app web sigue sirviendo a la LAN."""
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'sigam.db'
BACKUPS = ROOT / 'respaldos'
PORT = int(os.environ.get('SIGAM_PORT', '5000'))


def ip_local():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return 'IP no detectada (usar ipconfig)'


def puerto_ocupado():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(('127.0.0.1', PORT)) == 0


def respaldo_verificado():
    """Respaldo SQLite transaccional incluso cuando el servidor está funcionando."""
    if not DB.exists():
        raise FileNotFoundError('Aún no hay base de datos activa.')
    BACKUPS.mkdir(exist_ok=True)
    ruta = BACKUPS / f'sigam_respaldo_{datetime.now():%Y%m%d_%H%M%S_%f}.db'
    try:
        with sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True, timeout=10) as origen:
            with sqlite3.connect(ruta, timeout=10) as copia:
                origen.backup(copia)
                if copia.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('El respaldo no pasó la verificación de integridad.')
    except Exception:
        ruta.unlink(missing_ok=True)
        raise
    return ruta


class PanelSIGAM(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SIGAM v4.8 · Panel de control')
        self.geometry('580x490')
        self.minsize(530, 450)
        self.configure(bg='#f2f6fb')
        self.proceso = None
        self.estado = tk.StringVar(value='Comprobando el servidor...')
        self.direccion = tk.StringVar(value=f'Acceso local: http://127.0.0.1:{PORT}')
        self.red = tk.StringVar(value=f'En teléfonos (misma Wi-Fi): http://{ip_local()}:{PORT}')
        self._interfaz()
        self.protocol('WM_DELETE_WINDOW', self.cerrar)
        self.after(250, self.actualizar_estado)

    def _interfaz(self):
        style = ttk.Style(self)
        style.configure('Primary.TButton', padding=11, font=('Segoe UI', 11, 'bold'))
        style.configure('Tool.TButton', padding=10, font=('Segoe UI', 10))
        tk.Label(self, text='SIGAM', bg='#f2f6fb', fg='#12395a',
                 font=('Segoe UI', 27, 'bold')).pack(anchor='w', padx=28, pady=(22, 0))
        tk.Label(self, text='Panel de control del servidor · v4.8', bg='#f2f6fb',
                 fg='#4b6074', font=('Segoe UI', 11)).pack(anchor='w', padx=28, pady=(0, 18))
        bloque=tk.Frame(self,bg='white', padx=20, pady=17)
        bloque.pack(fill='x',padx=28)
        tk.Label(bloque,textvariable=self.estado,bg='white',fg='#12395a',
                 font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        tk.Label(bloque,textvariable=self.direccion,bg='white',fg='#41576a',
                 font=('Segoe UI', 10)).pack(anchor='w',pady=(10,0))
        tk.Label(bloque,textvariable=self.red,bg='white',fg='#41576a',
                 font=('Segoe UI', 10),wraplength=465,justify='left').pack(anchor='w')
        zona=tk.Frame(self,bg='#f2f6fb')
        zona.pack(fill='x',padx=28,pady=22)
        for col in (0,1): zona.grid_columnconfigure(col,weight=1)
        ttk.Button(zona,text='▶  Iniciar servidor',style='Primary.TButton',command=self.iniciar).grid(row=0,column=0,sticky='ew',padx=(0,6),pady=6)
        ttk.Button(zona,text='■  Detener servidor',style='Primary.TButton',command=self.detener).grid(row=0,column=1,sticky='ew',padx=(6,0),pady=6)
        ttk.Button(zona,text='🌐  Abrir SIGAM',style='Tool.TButton',command=self.abrir).grid(row=1,column=0,sticky='ew',padx=(0,6),pady=6)
        ttk.Button(zona,text='💾  Crear respaldo',style='Tool.TButton',command=self.respaldar).grid(row=1,column=1,sticky='ew',padx=(6,0),pady=6)
        ttk.Button(zona,text='📁  Ver respaldos',style='Tool.TButton',command=self.ver_respaldos).grid(row=2,column=0,sticky='ew',padx=(0,6),pady=6)
        ttk.Button(zona,text='⚠  Reiniciar base de datos',style='Tool.TButton',command=self.reiniciar_bd).grid(row=2,column=1,sticky='ew',padx=(6,0),pady=6)
        tk.Label(self,text='Uso solo en red privada. Para compartir con teléfonos, mantén el servidor encendido.\nPara comenzar sin datos, reinicia la base únicamente con el servidor detenido.',
                 bg='#f2f6fb',fg='#64748b',justify='left',font=('Segoe UI', 9)).pack(anchor='w',padx=28)

    def actualizar_estado(self):
        if self.proceso is not None and self.proceso.poll() is not None:
            self.proceso=None
        self.estado.set('● Servidor activo' if puerto_ocupado() else '○ Servidor detenido')
        self.after(1400,self.actualizar_estado)

    def iniciar(self):
        if puerto_ocupado():
            messagebox.showinfo('SIGAM','El puerto ya está ocupado. SIGAM podría estar iniciado en otra ventana.')
            return
        try:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            self.proceso=subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT,
                                          creationflags=flags, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
            self.after(1100,self._verificar_inicio)
        except Exception as ex:
            messagebox.showerror('No se pudo iniciar SIGAM',str(ex))

    def _verificar_inicio(self):
        if not puerto_ocupado():
            messagebox.showerror('SIGAM no inició','Comprueba que las dependencias estén instaladas y que el puerto esté libre.\nPrueba INICIAR_SIGAM.bat para ver el error.')

    def detener(self):
        if self.proceso is not None and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=5)
            except subprocess.TimeoutExpired:
                messagebox.showwarning('SIGAM','El servidor no respondió al cierre. Revísalo en el Administrador de tareas.')
            self.proceso=None
        elif puerto_ocupado():
            messagebox.showwarning('Servidor externo','Hay un servicio en el puerto, pero este panel no lo inició. Ciérralo desde su propia ventana.')
        else:
            messagebox.showinfo('SIGAM','El servidor ya está detenido.')

    def abrir(self):
        if not puerto_ocupado():
            messagebox.showinfo('SIGAM','Inicia el servidor primero.')
            return
        webbrowser.open(f'http://127.0.0.1:{PORT}')

    def respaldar(self):
        def tarea():
            try:
                resultado=respaldo_verificado()
                self.after(0,lambda: messagebox.showinfo('Respaldo creado',f'Se guardó una copia verificada en:\n{resultado}'))
            except Exception as exc:
                texto=str(exc)
                self.after(0,lambda:messagebox.showerror('Error al respaldar',texto))
        threading.Thread(target=tarea,daemon=True).start()

    def ver_respaldos(self):
        BACKUPS.mkdir(exist_ok=True)
        os.startfile(str(BACKUPS)) if hasattr(os,'startfile') else messagebox.showinfo('Respaldos',str(BACKUPS))

    def reiniciar_bd(self):
        if puerto_ocupado() or (self.proceso and self.proceso.poll() is None):
            messagebox.showerror('Servidor en ejecución','Primero detén SIGAM. No se reinició la base de datos.')
            return
        if not messagebox.askyesno('Reinicio de base de datos','Se borrarán activos, usuarios, órdenes y todo el contenido activo.\nSe creará un respaldo antes. ¿Deseas continuar?',icon='warning'):
            return
        try:
            import REINICIAR_BASE_DATOS
            resultado=REINICIAR_BASE_DATOS.main()
            if resultado==0:
                messagebox.showinfo('Reinicio completado','Base de datos reiniciada o vacía. Al iniciar, configura de nuevo el administrador. Revisa la carpeta respaldos.')
            else:
                messagebox.showerror('No se pudo reiniciar','La base no fue reiniciada. Revisa que SIGAM esté completamente cerrado.')
        except Exception as exc:
            messagebox.showerror('Error',str(exc))

    def cerrar(self):
        if self.proceso and self.proceso.poll() is None:
            if not messagebox.askyesno('Cerrar SIGAM','Al cerrar este panel también se detendrá el servidor. ¿Continuar?'):
                return
            self.detener()
        self.destroy()


if __name__=='__main__':
    PanelSIGAM().mainloop()
