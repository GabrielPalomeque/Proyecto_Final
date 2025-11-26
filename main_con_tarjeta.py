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

# --- 1. CONFIGURACIÓN DE ROLES Y PERMISOS ---
ETIQUETAS_MODELO = ["Tarjeta_Maestro", "Tarjeta_Jefe", "Tarjeta_Empleado"]

# Matriz de Permisos
PERMISOS = {
    "MAESTRO":  ["1", "2", "3", "4", "5", "L", "O", "V"], 
    "JEFE":     ["1", "2", "L", "O"],                     
    "EMPLEADO": ["L", "O"],                               
    "NADIE":    []                                        
}

# Configuración General
MODELO_FILE = "modelo_tarjetas.tflite"
ANCHO_CAM, ALTO_CAM = 640, 480

class SistemaSeguridad:
    def __init__(self):
        print(f"🚀 Iniciando Sistema de Control de Acceso + Visual en {platform.system()}")
        
        # 1. Hardware y Módulos
        self.comms = GestorSerial()
        self.cerebro_ia = DetectorRoboflow(MODELO_FILE, ETIQUETAS_MODELO)
        
        # 2. Cámara
        if platform.system() == 'Windows':
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAM)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAM)

        # 3. Mediapipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False, max_num_hands=2,
            model_complexity=0, min_detection_confidence=0.5, min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils

        # 4. ESTADO DEL SISTEMA
        self.usuario_actual = "NADIE"
        self.ultimo_cambio_usuario = 0
        
        self.frame_count = 0
        self.ultimas_cajas = []
        self.ultimo_resultado_manos = None
        
        # ESTO FALTABA: Memoria para dibujar el texto sobre las manos
        self.textos_manos = {'Right': "", 'Left': ""} 
        self.mensaje_estado = "" 

    def actualizar_rol(self, detecciones):
        """Actualiza el usuario si se detecta una tarjeta"""
        for (_, nombre_etiqueta, _) in detecciones:
            nuevo_rol = None
            
            if "Maestro" in nombre_etiqueta: nuevo_rol = "MAESTRO"
            elif "Jefe" in nombre_etiqueta: nuevo_rol = "JEFE"
            elif "Empleado" in nombre_etiqueta: nuevo_rol = "EMPLEADO"
            
            if nuevo_rol and nuevo_rol != self.usuario_actual:
                self.usuario_actual = nuevo_rol
                self.ultimo_cambio_usuario = time.time()
                print(f"🔐 CAMBIO DE USUARIO: {self.usuario_actual}")

    def validar_y_enviar(self, comando_intento):
        """El Portero: Verifica permisos"""
        lista_permitida = PERMISOS.get(self.usuario_actual, [])
        
        # Extraer clave (ej: "NUMERO_1" -> "1", "L" -> "L")
        clave = comando_intento.replace("NUMERO_", "")
        
        if clave in lista_permitida:
            self.comms.enviar(comando_intento)
            return f"✅ ENVIADO: {clave}"
        else:
            print(f"⛔ Acceso denegado a {self.usuario_actual} para {comando_intento}")
            return "🚫 ACCESO DENEGADO"

    def procesar(self):
        print("✅ Sistema Listo. Muestra tarjeta para login.")
        
        while True:
            ret, frame = self.cap.read()
            if not ret: break
            
            frame = cv2.flip(frame, 1)
            self.frame_count += 1
            
            # --- LÓGICA (1 de cada 3 frames) ---
            if self.frame_count % 3 == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # A. Detectar Tarjetas (Login)
                self.ultimas_cajas = self.cerebro_ia.detectar(rgb_frame)
                self.actualizar_rol(self.ultimas_cajas)
                
                # B. Detectar Manos (Intención)
                self.ultimo_resultado_manos = self.hands.process(rgb_frame)

                # C. Procesar Intenciones
                self.mensaje_estado = "" 
                
                # Si no hay manos, limpiamos los textos
                if not self.ultimo_resultado_manos or not self.ultimo_resultado_manos.multi_hand_landmarks:
                    self.textos_manos = {'Right': "", 'Left': ""}
                else:
                    for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, 
                                                   self.ultimo_resultado_manos.multi_handedness):
                        
                        label = handedness.classification[0].label
                        dedos = manos.analizar_dedos(landmarks.landmark, label)
                        comando_candidato = None

                        # Interpretar Gesto y GUARDAR TEXTO VISUAL
                        if label == 'Right': # Mano Izq Física -> Números
                            cant = sum(dedos)
                            self.textos_manos['Right'] = f"Num: {cant}" # <--- Feedback Visual
                            if cant > 0: comando_candidato = f"NUMERO_{cant}"
                        
                        elif label == 'Left': # Mano Der Física -> Letras
                            letra = manos.identificar_letra_mano(dedos, landmarks.landmark)
                            if letra: 
                                limpio = letra.split("_")[1]
                                self.textos_manos['Left'] = f"Letra: {limpio}" # <--- Feedback Visual
                                comando_candidato = limpio
                            else:
                                self.textos_manos['Left'] = "..."

                        # VALIDACIÓN DE SEGURIDAD (Solo si hay un gesto válido)
                        if comando_candidato:
                            self.mensaje_estado = self.validar_y_enviar(comando_candidato)

            # --- DIBUJADO VISUAL (Siempre) ---
            
            # 1. Panel de Estado
            color_ui = (0, 255, 255) # Amarillo (Nadie)
            if self.usuario_actual == "MAESTRO": color_ui = (0, 255, 0) # Verde
            elif self.usuario_actual == "JEFE": color_ui = (255, 165, 0) # Naranja
            elif self.usuario_actual == "EMPLEADO": color_ui = (255, 0, 255) # Magenta
            
            cv2.rectangle(frame, (0, 0), (640, 40), (50, 50, 50), -1)
            cv2.putText(frame, f"USUARIO: {self.usuario_actual}", (10, 30), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_ui, 2)

            # 2. Tarjetas detectadas
            for (box, nombre, score) in self.ultimas_cajas:
                ymin, xmin, ymax, xmax = box
                start = (int(xmin * ANCHO_CAM), int(ymin * ALTO_CAM))
                end = (int(xmax * ANCHO_CAM), int(ymax * ALTO_CAM))
                cv2.rectangle(frame, start, end, color_ui, 2)
                cv2.putText(frame, nombre, (start[0], start[1]-10), 0, 0.5, color_ui, 2)

            # 3. Manos, Textos Flotantes y Mensajes de Estado
            if self.ultimo_resultado_manos and self.ultimo_resultado_manos.multi_hand_landmarks:
                for landmarks, handedness in zip(self.ultimo_resultado_manos.multi_hand_landmarks, 
                                               self.ultimo_resultado_manos.multi_handedness):
                    
                    # Dibujar esqueleto (Corregido el self.mp_hands)
                    self.mp_draw.draw_landmarks(frame, landmarks, self.mp_hands.HAND_CONNECTIONS)
                    
                    # DIBUJAR EL TEXTO FLOTANTE (Num/Letra)
                    lbl = handedness.classification[0].label
                    # Recuperar el texto de la memoria
                    texto_visual = self.textos_manos.get(lbl, "")
                    
                    # Calcular posición (muñeca)
                    cx, cy = int(landmarks.landmark[0].x * ANCHO_CAM), int(landmarks.landmark[0].y * ALTO_CAM)
                    
                    color_txt = (255, 255, 0) if lbl == 'Right' else (0, 255, 255)
                    cv2.putText(frame, texto_visual, (cx, cy - 20), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, color_txt, 2)
                    
                # Mensaje de Aprobación/Rechazo abajo
                if self.mensaje_estado:
                    color_msg = (0, 0, 255) if "DENEGADO" in self.mensaje_estado else (0, 255, 0)
                    cv2.putText(frame, self.mensaje_estado, (50, 400), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, color_msg, 3)

            cv2.imshow('PiArchitect - Security Access', frame)
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