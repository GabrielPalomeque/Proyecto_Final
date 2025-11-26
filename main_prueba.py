import cv2
import mediapipe as mp
import numpy as np
import time
import platform
import math
import serial
import threading
import queue

# --- 1. CONFIGURACIÓN ---
SISTEMA = platform.system()
print(f"⚙️ PiArchitect: Sistema Final con Log de Envío en {SISTEMA}")

# CONFIGURACIÓN DE RED (UART)
PUERTO_SERIAL = 'COM3' if SISTEMA == 'Windows' else '/dev/serial0'
BAUDRATE = 115200

# CONFIGURACIÓN DE MODELO
MODELO_PATH = "modelo_tarjetas.tflite"
ETIQUETAS = ["Tarjeta_L", "Tarjeta_O", "Tarjeta_V"] 
UMB_CONFIANZA = 0.6
ANCHO_CAM = 640
ALTO_CAM = 480

# Importación TFLite
try:
    if SISTEMA == 'Windows':
        import tensorflow as tf
        Interpreter = tf.lite.Interpreter
    else:
        from tflite_runtime.interpreter import Interpreter
    TFLITE_AVAILABLE = True
except ImportError:
    TFLITE_AVAILABLE = False

# --- 2. GESTOR DE COMUNICACIÓN ASÍNCRONA ---
cola_mensajes = queue.Queue()

def worker_serial():
    ser = None
    try:
        ser = serial.Serial(PUERTO_SERIAL, BAUDRATE, timeout=1)
        print(f"✅ [HARDWARE] Puerto {PUERTO_SERIAL} conectado correctamente.")
    except Exception as e:
        print(f"⚠️ [HARDWARE] Puerto serial no disponible ({e}). Modo Simulación.")

    while True:
        comando = cola_mensajes.get()
        if comando == "SALIR": break
        
        if ser and ser.is_open:
            try:
                msg = f"{comando}\n"
                ser.write(msg.encode('utf-8'))
            except: pass
        
        # (Opcional) Si quieres ver también cuando el hilo físico lo procesa:
        # elif SISTEMA == 'Windows':
        #     print(f"   [Simulación Física] Procesando: {comando}")
            
        cola_mensajes.task_done()
    
    if ser: ser.close()

hilo_red = threading.Thread(target=worker_serial, daemon=True)
hilo_red.start()

# Variables de Control
ultimo_comando = ""
tiempo_ultimo_comando = 0

def poner_en_cola(comando):
    """Filtra comandos repetidos y los envía a la cola de salida"""
    global ultimo_comando, tiempo_ultimo_comando
    ahora = time.time()
    
    # Debounce de 1.5 segundos (Evita enviar 'L' 30 veces seguidas)
    if comando != ultimo_comando or (ahora - tiempo_ultimo_comando > 1.5):
        
        # --- IMPRESIÓN SOLICITADA EN CONSOLA ---
        print(f"🚀 Enviando a Pico 2W: {comando}")
        # ---------------------------------------
        
        cola_mensajes.put(comando)
        ultimo_comando = comando
        tiempo_ultimo_comando = ahora

# --- 3. LÓGICA DE GESTOS ---
def analizar_dedos(landmarks, etiqueta_mano):
    tips = [8, 12, 16, 20]
    dedos = []
    # Pulgar (Lógica invertida por espejo)
    if etiqueta_mano == 'Right': # Izquierda Real
        dedos.append(1 if landmarks[4].x < landmarks[3].x else 0)
    else: # Derecha Real
        dedos.append(1 if landmarks[4].x > landmarks[3].x else 0)
    for id in tips:
        dedos.append(1 if landmarks[id].y < landmarks[id - 2].y else 0)
    return dedos

def identificar_letra_mano(dedos, landmarks):
    dist = math.hypot(landmarks[8].x - landmarks[4].x, landmarks[8].y - landmarks[4].y)
    if dist < 0.05: return "LETRA_O"
    if dedos == [1, 1, 0, 0, 0]: return "LETRA_L"
    if dedos == [0, 1, 1, 0, 0] or dedos == [1, 1, 1, 0, 0]: return "LETRA_V"
    return None

class SistemaVigilancia:
    def __init__(self):
        print("🎥 Iniciando cámara...")
        if SISTEMA == 'Windows':
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)
            
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAM)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAM)
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils

        self.interpreter = None
        if TFLITE_AVAILABLE:
            try:
                self.interpreter = Interpreter(model_path=MODELO_PATH)
                self.interpreter.allocate_tensors()
                self.input_details = self.interpreter.get_input_details()
                self.output_details = self.interpreter.get_output_details()
                self.input_shape = self.input_details[0]['shape']
            except: pass

        self.frame_count = 0
        self.ultimas_cajas = []
        self.ultimo_resultado_manos = None
        self.textos_manos = {'Right': "", 'Left': ""} 

    def detectar_tarjetas(self, frame_rgb):
        if not self.interpreter: return []
        h, w = self.input_shape[1], self.input_shape[2]
        img = cv2.resize(frame_rgb, (w, h))
        input_data = np.expand_dims(img, axis=0)
        if self.input_details[0]['dtype'] == np.float32:
            input_data = (np.float32(input_data) - 127.5) / 127.5

        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()

        boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]

        res = []
        for i in range(len(scores)):
            if scores[i] > UMB_CONFIANZA:
                idx = int(classes[i])
                if idx < len(ETIQUETAS):
                    nombre = ETIQUETAS[idx]
                    res.append((boxes[i], nombre, scores[i]))
                    letra = nombre.split("_")[-1] 
                    poner_en_cola(letra)
        return res

    def procesar(self):
        print("✅ Bucle principal iniciado. Observa la consola para ver envíos.")
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            
            frame = cv2.flip(frame, 1)
            self.frame_count += 1
            
            # --- LÓGICA (1 de cada 3 frames) ---
            if self.frame_count % 3 == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 1. IA Tarjetas
                self.ultimas_cajas = self.detectar_tarjetas(rgb_frame)
                
                # 2. Manos
                self.ultimo_resultado_manos = self.hands.process(rgb_frame)

                if not self.ultimo_resultado_manos or not self.ultimo_resultado_manos.multi_hand_landmarks:
                    self.textos_manos = {'Right': "", 'Left': ""}
                else:
                    for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, 
                                                   self.ultimo_resultado_manos.multi_handedness):
                        label = handedness.classification[0].label
                        dedos = analizar_dedos(landmarks.landmark, label)
                        
                        # Lógica Izq (Números)
                        if label == 'Right':
                            cant = sum(dedos)
                            self.textos_manos['Right'] = f"Num: {cant}"
                            if cant > 0: poner_en_cola(f"NUMERO_{cant}")
                            else: poner_en_cola("PUÑO_CERRADO")
                        
                        # Lógica Der (Letras)
                        elif label == 'Left':
                            letra = identificar_letra_mano(dedos, landmarks.landmark)
                            if letra:
                                txt = letra.split("_")[1]
                                self.textos_manos['Left'] = f"Letra: {txt}"
                                poner_en_cola(txt)
                            else:
                                self.textos_manos['Left'] = "..."

            # --- DIBUJADO ---
            for (box, nombre, score) in self.ultimas_cajas:
                ymin, xmin, ymax, xmax = box
                start = (int(xmin * ANCHO_CAM), int(ymin * ALTO_CAM))
                end = (int(xmax * ANCHO_CAM), int(ymax * ALTO_CAM))
                cv2.rectangle(frame, start, end, (0, 255, 0), 2)
                cv2.putText(frame, nombre, (start[0], start[1]-10), 0, 0.5, (0,255,0), 2)

            if self.ultimo_resultado_manos and self.ultimo_resultado_manos.multi_hand_landmarks:
                for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, 
                                               self.ultimo_resultado_manos.multi_handedness):
                    
                    self.mp_draw.draw_landmarks(frame, landmarks, self.mp_hands.HAND_CONNECTIONS)
                    
                    label = handedness.classification[0].label
                    texto_a_mostrar = self.textos_manos.get(label, "")
                    
                    cx, cy = int(landmarks.landmark[0].x * ANCHO_CAM), int(landmarks.landmark[0].y * ALTO_CAM)
                    
                    color = (255, 255, 0) if label == 'Right' else (0, 255, 255)
                    cv2.putText(frame, texto_a_mostrar, (cx, cy - 20), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

            cv2.imshow('PiArchitect - Final System', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
        
        self.cap.release()
        cola_mensajes.put("SALIR")
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = SistemaVigilancia()
    app.procesar()