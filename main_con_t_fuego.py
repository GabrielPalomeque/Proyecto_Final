import cv2
import mediapipe as mp
import platform
import time
import socket
import numpy as np
import math

# --- IMPORTACIÓN DE MÓDULOS ---
from comunicacion import GestorSerial
from detector_ia import DetectorRoboflow
import logica_manos as manos

# --- CONFIGURACIÓN ---
ETIQUETAS_MODELO = ["Tarjeta_Maestro", "Tarjeta_Jefe", "Tarjeta_Empleado"]
PERMISOS = {
    "MAESTRO": ["1", "2", "3", "4", "5", "L", "O", "V"],
    "JEFE":    ["1", "2", "L", "O"],
    "EMPLEADO":["L", "O"],
    "NADIE":   []
}
MODELO_FILE = "modelo_tarjetas.tflite"
ANCHO_CAM, ALTO_CAM = 640, 480

class SistemaSeguridad:
    def __init__(self):
        print(f"🚀 Iniciando Sistema Final (Logs Activados) en {platform.system()}")
        
        self.comms = GestorSerial()
        self.cerebro_ia = DetectorRoboflow(MODELO_FILE, ETIQUETAS_MODELO)
        
        if platform.system() == 'Windows':
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAM)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAM)

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False, max_num_hands=2,
            model_complexity=0, min_detection_confidence=0.6, min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils

        # ESTADO
        self.usuario_actual = "NADIE"
        self.modo_automatico = False
        self.ultimo_cambio_modo = 0
        
        self.frame_count = 0
        self.ultimas_cajas = []
        self.ultimo_resultado_manos = None
        self.estado_fuego = [False, False, False]
        
        self.textos_manos = {'Right': "", 'Left': ""}
        self.mensaje_centro = "" 
        self.tiempo_mensaje = 0

    def toggle_modo(self):
        ahora = time.time()
        if ahora - self.ultimo_cambio_modo > 2.0:
            self.modo_automatico = not self.modo_automatico
            self.ultimo_cambio_modo = ahora
            
            if self.modo_automatico:
                print("\n🔄 CAMBIO A MODO: AUTOMÁTICO (Detección de Fuego)")
                self.comms.enviar("MODO_AUTO")
                self.mostrar_mensaje("MODO AUTOMATICO")
            else:
                print("\n🔄 CAMBIO A MODO: MANUAL (Control por Gestos)")
                self.comms.enviar("MODO_MANUAL")
                self.estado_fuego = [False, False, False]
                self.comms.enviar("PUÑO_CERRADO")
                self.mostrar_mensaje("MODO MANUAL")

    def mostrar_mensaje(self, texto):
        self.mensaje_centro = texto
        self.tiempo_mensaje = time.time()

    def validar_y_enviar_manual(self, comando_intento):
        """Valida permisos y envía con log"""
        lista = PERMISOS.get(self.usuario_actual, [])
        clave = comando_intento.replace("NUMERO_", "")
        
        if clave in lista:
            # --- LOG RESTAURADO AQUÍ ---
            print(f"🚀 Enviando a Pico 2W: {comando_intento}")
            self.comms.enviar(comando_intento)
            return True
        else:
            print(f"⛔ Acceso DENEGADO para: {comando_intento}")
            self.mostrar_mensaje("ACCESO DENEGADO")
            return False

    def procesar_zonas_fuego(self, frame):
        alto, ancho, _ = frame.shape
        tercio = ancho // 3
        zonas = [frame[:, 0:tercio], frame[:, tercio:2*tercio], frame[:, 2*tercio:]]
        coords_x = [0, tercio, 2*tercio]

        for i, roi in enumerate(zonas):
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([18, 50, 50]), np.array([35, 255, 255]))
            hay_fuego = cv2.countNonZero(mask) > 2000

            if hay_fuego and not self.estado_fuego[i]:
                cmd = f"FUEGO_{i+1}_ON"
                print(f"🔥 ¡ALERTA! Enviando a Pico 2W: {cmd}") # Log de Fuego
                self.comms.enviar(cmd)
                self.estado_fuego[i] = True
            elif not hay_fuego and self.estado_fuego[i]:
                cmd = f"FUEGO_{i+1}_OFF"
                print(f"💨 Fuego extinguido. Enviando: {cmd}") # Log de apagado
                self.comms.enviar(cmd)
                self.estado_fuego[i] = False

            if self.estado_fuego[i]:
                cv2.rectangle(frame, (coords_x[i], 0), (coords_x[i]+tercio, alto), (0, 0, 255), 5)
                cv2.putText(frame, f"FUEGO Z{i+1}", (coords_x[i]+10, alto//2), 1, 2, (0,0,255), 3)
            
            cv2.line(frame, (coords_x[i], 0), (coords_x[i], alto), (200, 200, 200), 2)

    def procesar(self):
        print("✅ Sistema Listo. Esperando input...")
        
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            
            frame = cv2.flip(frame, 1)
            self.frame_count += 1
            
            # --- LÓGICA (1 de cada 3 frames) ---
            if self.frame_count % 3 == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # A. Tarjetas
                self.ultimas_cajas = self.cerebro_ia.detectar(rgb_frame)
                for (_, nombre, _) in self.ultimas_cajas:
                    if "Maestro" in nombre: self.usuario_actual = "MAESTRO"
                    elif "Jefe" in nombre: self.usuario_actual = "JEFE"
                    elif "Empleado" in nombre: self.usuario_actual = "EMPLEADO"
                    
                    if not self.modo_automatico:
                        letra = nombre.split("_")[-1]
                        if letra in ["L", "O", "V"]: 
                            print(f"🚀 Enviando a Pico 2W (Tarjeta): {letra}") # Log Tarjeta
                            self.comms.enviar(letra)

                # B. Manos
                self.ultimo_resultado_manos = self.hands.process(rgb_frame)
                
                if not self.ultimo_resultado_manos or not self.ultimo_resultado_manos.multi_hand_landmarks:
                    self.textos_manos = {'Right': "", 'Left': ""}
                else:
                    for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, self.ultimo_resultado_manos.multi_handedness):
                        label = handedness.classification[0].label
                        dedos = manos.analizar_dedos(landmarks.landmark, label)
                        
                        # Cambio Modo
                        if dedos == [1, 1, 0, 0, 1]:
                            self.toggle_modo()
                        
                        # Modo Manual
                        elif not self.modo_automatico:
                            if label == 'Right': # Números
                                cant = sum(dedos)
                                self.textos_manos['Right'] = f"#{cant}"
                                if cant > 0: 
                                    if not self.validar_y_enviar_manual(f"NUMERO_{cant}"):
                                        self.textos_manos['Right'] += " (X)"
                                else: 
                                    # Evitar spam de puño cerrado en consola
                                    self.comms.enviar("PUÑO_CERRADO")

                            elif label == 'Left': # Letras
                                letra = manos.identificar_letra_mano(dedos, landmarks.landmark)
                                if letra: 
                                    txt = letra.split("_")[1]
                                    self.textos_manos['Left'] = f"{txt}"
                                    if not self.validar_y_enviar_manual(txt):
                                        self.textos_manos['Left'] += " (X)"
                                else:
                                    self.textos_manos['Left'] = "..."

            # --- AUTO (Fuego) ---
            if self.modo_automatico:
                self.procesar_zonas_fuego(frame)
                cv2.putText(frame, "MODO AUTOMATICO (FUEGO)", (10, 460), 1, 2, (0, 0, 255), 3)
            else:
                cv2.putText(frame, "MANUAL", (10, 460), 1, 2, (255, 255, 0), 3)

            # --- DIBUJADO ---
            col = (0,255,255) 
            if self.usuario_actual=="MAESTRO": col=(0,255,0)
            elif self.usuario_actual=="JEFE": col=(0,165,255)
            elif self.usuario_actual=="EMPLEADO": col=(255,0,255)
            
            cv2.rectangle(frame, (0,0), (640,50), (0,0,0), -1)
            cv2.putText(frame, f"USUARIO: {self.usuario_actual}", (20,35), 1, 1, col, 2)

            for (box, nombre, score) in self.ultimas_cajas:
                ymin, xmin, ymax, xmax = box
                start = (int(xmin * ANCHO_CAM), int(ymin * ALTO_CAM))
                end = (int(xmax * ANCHO_CAM), int(ymax * ALTO_CAM))
                cv2.rectangle(frame, start, end, col, 3)
                cv2.putText(frame, nombre.split("_")[-1], (start[0], start[1]-10), 1, 1, col, 2)

            if self.ultimo_resultado_manos and self.ultimo_resultado_manos.multi_hand_landmarks:
                for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, 
                                               self.ultimo_resultado_manos.multi_handedness):
                    self.mp_draw.draw_landmarks(frame, landmarks, self.mp_hands.HAND_CONNECTIONS)
                    lbl = handedness.classification[0].label
                    coord = (int(landmarks.landmark[0].x * ANCHO_CAM), int(landmarks.landmark[0].y * ALTO_CAM))
                    txt = self.textos_manos.get(lbl, "")
                    color_txt = (0, 255, 0) if "(X)" not in txt else (0, 0, 255)
                    cv2.putText(frame, txt, (coord[0]-50, coord[1]-30), 1, 1.5, color_txt, 3)

            if time.time() - self.tiempo_mensaje < 2.0:
                textSize = cv2.getTextSize(self.mensaje_centro, 1, 2, 3)[0]
                textX = (frame.shape[1] - textSize[0]) // 2
                textY = (frame.shape[0] + textSize[1]) // 2
                cv2.putText(frame, self.mensaje_centro, (textX, textY), 1, 2, (0,0,255), 4)

            cv2.imshow('PiArchitect Final', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

    def cerrar(self):
        self.cap.release()
        self.comms.cerrar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = SistemaSeguridad()
    try:
        app.procesar()
    except KeyboardInterrupt:
        app.cerrar()