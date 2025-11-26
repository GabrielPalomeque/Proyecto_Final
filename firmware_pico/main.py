import machine
import time
import sys

# --- 1. CONFIGURACIÓN DE HARDWARE ---

# LED Onboard (Indicador de Estado)
# Pico W/2W usan "WL_GPIO0". Si usas una Pico normal, cambia a 25.
led_onboard = machine.Pin("WL_GPIO0", machine.Pin.OUT)

# Comunicación UART (Serial)
# RX de Pico va al TX de la Pi/USB-TTL
uart = machine.UART(0, baudrate=115200, tx=machine.Pin(0), rx=machine.Pin(1))

# Servomotor (Puerta)
servo = machine.PWM(machine.Pin(16))
servo.freq(50)

# LED Indicador Externo (Letra V)
led_v = machine.Pin(15, machine.Pin.OUT)

# Bombas / Salidas (Array para fácil acceso)
# Índices: 0=Bomba1 ... 4=Bomba5
pines_bombas = [18, 19, 20, 21, 22]
bombas = [machine.Pin(p, machine.Pin.OUT) for p in pines_bombas]

# --- 2. FUNCIONES DE CONTROL ---

def mover_servo(grados):
    """Mueve el servo de 0 a 180 grados"""
    # Mapeo seguro para evitar forzar el motor
    if grados < 0: grados = 0
    if grados > 180: grados = 180
    
    # Ciclo de trabajo para 50Hz (aprox 1ms a 2ms)
    min_duty = 1638
    max_duty = 8192
    duty = int(min_duty + (grados / 180) * (max_duty - min_duty))
    servo.duty_u16(duty)

def control_bomba_manual(numero):
    """
    Modo Manual: Activa SOLO una bomba, apaga el resto.
    numero: 1 a 5 (0 para apagar todo)
    """
    for i, b in enumerate(bombas):
        if (i + 1) == numero:
            b.value(1)
        else:
            b.value(0)
    
    if numero > 0:
        print(f"💧 Manual: Bomba {numero} ACTIVA")
    else:
        print("⛔ Manual: Todo apagado")

def control_fuego_zona(zona, estado):
    """
    Modo Auto: Controla zonas independientemente.
    zona: 1, 2 o 3
    estado: True (ON) / False (OFF)
    """
    if 1 <= zona <= 3:
        idx = zona - 1
        bombas[idx].value(1 if estado else 0)
        accion = "ENCENDIDA" if estado else "APAGADA"
        print(f"🔥 Fuego Zona {zona}: {accion}")

# --- 3. BUCLE PRINCIPAL ---
print("✅ Pico 2W Lista. Esperando comandos UART...")

# Secuencia de arranque (Parpadeo rápido)
for _ in range(5):
    led_onboard.toggle()
    time.sleep(0.05)
led_onboard.off()

while True:
    if uart.any():
        try:
            # Leer mensaje y limpiar espacios
            data = uart.readline()
            if not data: continue
            
            msg = data.decode('utf-8').strip()
            print(f"📨 Cmd: {msg}")

            # --- A. CAMBIO DE MODOS (Feedback Visual) ---
            if msg == "MODO_AUTO":
                # Parpadeo de advertencia (Modo Fuego)
                for _ in range(3):
                    led_onboard.on(); time.sleep(0.1); led_onboard.off(); time.sleep(0.1)
                # Apagar todo por seguridad al cambiar
                control_bomba_manual(0) 
                
            elif msg == "MODO_MANUAL":
                # Luz fija breve (Modo Gestos)
                led_onboard.on()
                time.sleep(1)
                led_onboard.off()
                control_bomba_manual(0)

            # --- B. ACCIONES MODO AUTOMÁTICO (FUEGO) ---
            elif msg.startswith("FUEGO_"):
                # Formato: FUEGO_1_ON
                partes = msg.split('_')
                zona = int(partes[1])
                estado = (partes[2] == "ON")
                control_fuego_zona(zona, estado)

            # --- C. ACCIONES MODO MANUAL (GESTOS/TARJETAS) ---
            elif msg.startswith("NUMERO_"):
                # Formato: NUMERO_3
                num = int(msg.split('_')[1])
                control_bomba_manual(num)
            
            elif msg == "PUÑO_CERRADO":
                control_bomba_manual(0)

            elif msg == "L":
                print("🚪 Puerta Abierta")
                mover_servo(90)
            
            elif msg == "O":
                print("🚪 Puerta Cerrada")
                mover_servo(0)
            
            elif msg == "V":
                print("💡 LED V")
                led_v.on(); time.sleep(0.5); led_v.off()

        except Exception as e:
            print(f"⚠️ Error procesando: {e}")
            
    # Pequeña pausa para no saturar el CPU
    time.sleep(0.01)