"""Panel gráfico de SIGAM v4.3 para Windows, sin funciones posteriores al Sprint 1."""
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from GESTION_BD import respaldar, reiniciar, BACKUPS

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('SIGAM_PORT','5000'))

def ip_local():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return 'IP no detectada: ejecutar ipconfig'

def puerto_ocupado():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(('127.0.0.1', PORT)) == 0

class PanelSIGAM(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SIGAM v4.3 · Panel de administración · Sprint 1')
        self.geometry('610x510')
        self.minsize(540,460)
        self.configure(bg='#f2f6fb')
        self.proceso = None
        self.modo_lan = tk.BooleanVar(value=True)
        self.estado = tk.StringVar(value='Comprobando servidor...')
        self.direccion = tk.StringVar(value=f'Acceso local: http://127.0.0.1:{PORT}')
        self.red = tk.StringVar(value=f'Acceso desde la misma Wi-Fi: http://{ip_local()}:{PORT}')
        self._interfaz()
        self.protocol('WM_DELETE_WINDOW', self.cerrar)
        self.after(300,self.actualizar_estado)

    def _interfaz(self):
        style = ttk.Style(self)
        style.configure('Primary.TButton',padding=12,font=('Segoe UI',11,'bold'))
        style.configure('Tool.TButton',padding=11,font=('Segoe UI',10))
        tk.Label(self,text='SIGAM',bg='#f2f6fb',fg='#12395a',font=('Segoe UI',27,'bold')).pack(anchor='w',padx=27,pady=(22,0))
        tk.Label(self,text='Panel del servidor · v4.3 · Cierre del Sprint 1',bg='#f2f6fb',fg='#4b6074',font=('Segoe UI',11)).pack(anchor='w',padx=27,pady=(0,18))
        bloque=tk.Frame(self,bg='white',padx=20,pady=17)
        bloque.pack(fill='x',padx=27)
        tk.Label(bloque,textvariable=self.estado,bg='white',fg='#12395a',font=('Segoe UI',13,'bold')).pack(anchor='w')
        tk.Label(bloque,textvariable=self.direccion,bg='white',fg='#41576a',font=('Segoe UI',10)).pack(anchor='w',pady=(10,0))
        tk.Label(bloque,textvariable=self.red,bg='white',fg='#41576a',font=('Segoe UI',10),wraplength=465,justify='left').pack(anchor='w')
        tk.Checkbutton(self,text='Permitir acceso desde otros dispositivos en la misma Wi-Fi',variable=self.modo_lan,bg='#f2f6fb',fg='#41576a').pack(anchor='w',padx=27,pady=(9,0))
        zona=tk.Frame(self,bg='#f2f6fb')
        zona.pack(fill='x',padx=27,pady=20)
        for c in (0,1): zona.grid_columnconfigure(c,weight=1)
        botones=[
            ('▶  Iniciar servidor',self.iniciar),('■  Detener servidor',self.detener),
            ('Abrir SIGAM en navegador',self.abrir),('Crear copia de seguridad',self.respaldar),
            ('Ver respaldos',self.ver_respaldos),('Reiniciar base de datos',self.reiniciar_bd),
        ]
        for i,(etiqueta,accion) in enumerate(botones):
            ttk.Button(zona,text=etiqueta,style='Primary.TButton' if i<2 else 'Tool.TButton',command=accion).grid(row=i//2,column=i%2,sticky='ew',padx=6,pady=7)
        tk.Label(self,text='Los teléfonos se conectan por navegador en la misma red.\nEsta versión no incorpora acceso remoto por Internet ni módulos del Sprint 2.',
            bg='#f2f6fb',fg='#64748b',justify='left',font=('Segoe UI',9)).pack(anchor='w',padx=27)

    def actualizar_estado(self):
        if self.proceso is not None and self.proceso.poll() is not None:
            self.proceso = None
        self.estado.set('● Servidor activo' if puerto_ocupado() else '○ Servidor detenido')
        self.after(1400,self.actualizar_estado)

    def iniciar(self):
        if puerto_ocupado():
            messagebox.showwarning('Puerto ocupado','Ya hay un programa escuchando en este puerto. Cierra SIGAM si está iniciado en otra ventana.')
            return
        ambiente = dict(os.environ)
        ambiente['SIGAM_BIND_LAN']='1' if self.modo_lan.get() else '0'
        try:
            self.proceso=subprocess.Popen([sys.executable,str(ROOT/'SERVIDOR_SIGAM.py')],cwd=ROOT,env=ambiente,
                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.after(1400,self.comprobar_inicio)
        except Exception as error:
            messagebox.showerror('Error al iniciar',str(error))

    def comprobar_inicio(self):
        if not puerto_ocupado():
            messagebox.showerror('SIGAM no inició','Revisa que estén instaladas las dependencias. Puedes ejecutar INICIAR_SIGAM.bat para ver el error.')

    def detener(self):
        if self.proceso is not None and self.proceso.poll() is None:
            self.proceso.terminate()
            try: self.proceso.wait(timeout=6)
            except subprocess.TimeoutExpired:
                messagebox.showerror('SIGAM','No se pudo detener el servidor. Ciérralo manualmente antes de gestionar la base.')
                return False
            self.proceso=None
            return True
        if puerto_ocupado():
            messagebox.showwarning('Servidor externo','El puerto está en uso, pero este panel no inició ese proceso. Ciérralo desde su propia ventana.')
            return False
        messagebox.showinfo('SIGAM','El servidor ya está detenido.')
        return True

    def abrir(self):
        if not puerto_ocupado():
            messagebox.showinfo('SIGAM','Inicia el servidor primero.')
            return
        webbrowser.open(f'http://127.0.0.1:{PORT}')

    def respaldar(self):
        def tarea():
            try:
                archivo=respaldar()
                texto=f'Respaldo guardado y verificado en:\n{archivo}'
                self.after(0,lambda: messagebox.showinfo('Respaldo creado',texto))
            except Exception as error:
                texto=str(error)
                self.after(0,lambda: messagebox.showerror('Error al respaldar',texto))
        threading.Thread(target=tarea,daemon=True).start()

    def ver_respaldos(self):
        BACKUPS.mkdir(exist_ok=True)
        if hasattr(os,'startfile'):
            os.startfile(str(BACKUPS))
        else:
            messagebox.showinfo('Respaldos',str(BACKUPS))

    def reiniciar_bd(self):
        if puerto_ocupado() or (self.proceso is not None and self.proceso.poll() is None):
            messagebox.showerror('SIGAM en ejecución','Detén el servidor antes de reiniciar la base de datos.')
            return
        aviso=('Esta operación retira la base de datos activa: equipos, usuarios, avisos y órdenes.\n'
               'Se creará antes una copia de seguridad.\n\n¿Deseas continuar?')
        if not messagebox.askyesno('Reinicio de datos',aviso,icon='warning'):
            return
        texto=simpledialog.askstring('Confirmación final','Escribe REINICIAR para confirmar:',parent=self)
        if texto!='REINICIAR':
            messagebox.showinfo('Cancelado','No se hicieron cambios.')
            return
        try:
            archivo=reiniciar()
            mensaje=(f'Reinicio completado. Respaldo:\n{archivo}' if archivo else 'No había base de datos activa que reiniciar.')
            messagebox.showinfo('SIGAM',mensaje+'\nAl iniciar, tendrás que crear un administrador nuevamente.')
        except Exception as error:
            messagebox.showerror('No se pudo reiniciar',str(error))

    def cerrar(self):
        if self.proceso is not None and self.proceso.poll() is None:
            if not messagebox.askyesno('Cerrar SIGAM','Al cerrar el panel también se detendrá el servidor. ¿Continuar?'):
                return
            if not self.detener():
                return
        self.destroy()

if __name__=='__main__':
    PanelSIGAM().mainloop()
