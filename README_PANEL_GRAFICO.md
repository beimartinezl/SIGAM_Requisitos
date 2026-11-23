# SIGAM v4.3 · Sprint 1 + panel gráfico de escritorio

**Objetivo:** facilitar el arranque y la administración del servidor SIGAM v4.3 sin añadir funcionalidades del Sprint 2.

## Uso en Windows

1. Extrae el ZIP en una carpeta; requiere Python 3.10+ con la opción PATH activada e Internet para instalar las dependencias la primera vez.
2. Haz doble clic en `ABRIR_PANEL_SIGAM.bat`.
3. Pulsa **Iniciar servidor** y después **Abrir SIGAM en navegador**.
4. En el primer uso, crea el administrador; luego podrás entrar con usuario y contraseña.
5. Para usarlo en otros dispositivos conectados a la **misma Wi-Fi**, abre la dirección de red indicada en el panel.
6. Para detener SIGAM, utiliza **Detener servidor** antes de cerrar el panel.

**Nota:** SIGAM v4.3 no incluye acceso remoto por Internet ni funcionamiento offline. El panel se inspira en la interfaz de v4.9, pero conserva las funciones de v4.3 para que la evidencia del Sprint 1 siga siendo coherente.

## Base de datos

- Conserva tu `sigam.db` de v4.3. Si migras la carpeta, copia ese archivo con SIGAM completamente cerrado.
- **Crear copia de seguridad** genera un respaldo SQLite coherente en `respaldos/` incluso con el servidor en uso.
- **Reiniciar base de datos** solo funciona con el servidor detenido y exige dos confirmaciones; crea antes un respaldo y retira la base activa. Al iniciar nuevamente, tendrás que crear la cuenta administradora.
- El reinicio no elimina ni modifica los respaldos previos.
- Si se utilizan copias/restauraciones manuales de la BD, SIGAM debe estar detenido para evitar conflictos con archivos WAL y SHM.

## Pruebas

- `EJECUTAR_PRUEBAS.bat` permite ejecutar las pruebas originales de importación Excel de la versión 4.3 más las nuevas pruebas del panel.
- Las funciones de interfaz de escritorio requieren Windows con entorno gráfico; las pruebas incluidas se concentran en el respaldo, reinicio, configuración del servidor e integridad de archivos.

## Instalación alternativa

También puedes ejecutar el antiguo `INICIAR_SIGAM.bat` para abrir el servidor sin usar el panel gráfico.
