import serial
import threading
import queue
import time
import platform

class GestorSerial:
    def __init__(self, baudrate=115200):
        self.sistema = platform.system()
        self.puerto = 'COM3' if self.sistema == 'Windows' else '/dev/serial0'
        self.baudrate = baudrate
        
        # Cola de mensajes (Thread-safe)
        self.cola = queue.Queue()
        self.running = True
        
        # Variables para Debounce (Anti-spam)
        self.ultimo_comando = ""
        self.tiempo_ultimo = 0
        
        # Iniciar el hilo cartero
        self.hilo = threading.Thread(target=self._worker_serial, daemon=True)
        self.hilo.start()

    def _worker_serial(self):
        """Proceso en segundo plano que gestiona el hardware"""
        ser = None
        try:
            # Timeout 1s para no bloquear
            ser = serial.Serial(self.puerto, self.baudrate, timeout=1)
            print(f"✅ [COMUNICACION] Puerto {self.puerto} abierto.")
        except Exception as e:
            print(f"⚠️ [COMUNICACION] Error puerto ({e}). Modo Simulación.")

        while self.running:
            try:
                # Esperar mensaje (bloqueante con timeout para permitir salir)
                comando = self.cola.get(timeout=1)
                
                if ser and ser.is_open:
                    msg = f"{comando}\n"
                    ser.write(msg.encode('utf-8'))
                elif self.sistema == 'Windows':
                    # Feedback visual solo en Windows si no hay serial
                    pass 
                
                self.cola.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error enviando: {e}")

        if ser: ser.close()
        print("🛑 [COMUNICACION] Hilo detenido.")

    def enviar(self, comando):
        """Método público para encolar comandos con filtro de tiempo"""
        ahora = time.time()
        # Debounce de 1.5 segundos
        if comando != self.ultimo_comando or (ahora - self.tiempo_ultimo > 1.5):
            print(f"📤 [UART] Enviando: '{comando}'")
            self.cola.put(comando)
            self.ultimo_comando = comando
            self.tiempo_ultimo = ahora

    def cerrar(self):
        self.running = False
        if self.hilo.is_alive():
            self.hilo.join(timeout=1)