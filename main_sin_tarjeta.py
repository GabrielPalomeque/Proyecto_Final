import cv2
import mediapipe as mp
import platform

# --- IMPORTACIÓN DE NUESTROS MÓDULOS ---
from comunicacion import GestorSerial
from detector_ia import DetectorRoboflow
import logica_manos as manos

# --- CONFIGURACIÓN ---
# Ajusta estas etiquetas a tu modelo real
ETIQUETAS_MODELO = ["Tarjeta_L", "Tarjeta_O", "Tarjeta_V"]
MODELO_FILE = "modelo_tarjetas.tflite"
ANCHO_CAM, ALTO_CAM = 640, 480

def main():
    print(f"🚀 Iniciando PiArchitect Modular en {platform.system()}")
    
    # 1. Inicializar Módulos
    comms = GestorSerial()
    cerebro_ia = DetectorRoboflow(MODELO_FILE, ETIQUETAS_MODELO)
    
    # 2. Inicializar Cámara y Mediapipe
    if platform.system() == 'Windows':
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAM)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAM)

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False, max_num_hands=2,
        model_complexity=0, min_detection_confidence=0.5, min_tracking_confidence=0.5
    )
    mp_draw = mp.solutions.drawing_utils

    # Estado
    frame_count = 0
    ultimas_cajas = []
    ultimo_resultado_manos = None
    textos_manos = {'Right': "", 'Left': ""} 

    try:
        print("✅ Bucle principal activo. Presiona 'q' para salir.")
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            frame = cv2.flip(frame, 1)
            frame_count += 1
            
            # --- LÓGICA (Frame Skipping 1/3) ---
            if frame_count % 3 == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # A. Detección IA (Tarjetas)
                ultimas_cajas = cerebro_ia.detectar(rgb_frame)
                
                # B. Detección Mediapipe (Manos)
                ultimo_resultado_manos = hands.process(rgb_frame)

                # C. Procesamiento de Lógica (Si hay manos)
                if not ultimo_resultado_manos or not ultimo_resultado_manos.multi_hand_landmarks:
                    textos_manos = {'Right': "", 'Left': ""}
                else:
                    for landmarks, handedness in zip(ultimo_resultado_manos.multi_hand_landmarks, 
                                                   ultimo_resultado_manos.multi_handedness):
                        label = handedness.classification[0].label
                        dedos_estado = manos.analizar_dedos(landmarks.landmark, label)
                        
                        # Mano Izquierda (Right en espejo) -> NÚMEROS
                        if label == 'Right':
                            cant = sum(dedos_estado)
                            textos_manos['Right'] = f"Num: {cant}"
                            if cant > 0: comms.enviar(f"NUMERO_{cant}")
                            else: comms.enviar("PUÑO_CERRADO")
                        
                        # Mano Derecha (Left en espejo) -> LETRAS
                        elif label == 'Left':
                            letra = manos.identificar_letra_mano(dedos_estado, landmarks.landmark)
                            if letra:
                                clean_letra = letra.split("_")[1]
                                textos_manos['Left'] = f"Letra: {clean_letra}"
                                comms.enviar(clean_letra)
                            else:
                                textos_manos['Left'] = "..."

            # --- PROCESAMIENTO TARJETAS (Envío directo desde resultados IA) ---
            # Lo hacemos aquí para aprovechar los datos cacheados
            if frame_count % 3 == 0:
                for (_, nombre, _) in ultimas_cajas:
                    # Ejemplo: "Tarjeta_L" -> envía "L"
                    letra_tarjeta = nombre.split("_")[-1]
                    comms.enviar(letra_tarjeta)

            # --- DIBUJADO (Renderizado en cada frame) ---
            # 1. Cajas de Tarjetas
            for (box, nombre, score) in ultimas_cajas:
                ymin, xmin, ymax, xmax = box
                start = (int(xmin * ANCHO_CAM), int(ymin * ALTO_CAM))
                end = (int(xmax * ANCHO_CAM), int(ymax * ALTO_CAM))
                cv2.rectangle(frame, start, end, (0, 255, 0), 2)
                cv2.putText(frame, f"{nombre} {int(score*100)}%", (start[0], start[1]-5), 0, 0.5, (0,255,0), 2)

            # 2. Esqueletos de Manos
            if ultimo_resultado_manos and ultimo_resultado_manos.multi_hand_landmarks:
                for landmarks, handedness in zip(ultimo_resultado_manos.multi_hand_landmarks, 
                                               ultimo_resultado_manos.multi_handedness):
                    mp_draw.draw_landmarks(frame, landmarks, mp_hands.HAND_CONNECTIONS)
                    
                    lbl = handedness.classification[0].label
                    coords = (int(landmarks.landmark[0].x * ANCHO_CAM), int(landmarks.landmark[0].y * ALTO_CAM))
                    txt = textos_manos.get(lbl, "")
                    color = (255, 255, 0) if lbl == 'Right' else (0, 255, 255)
                    cv2.putText(frame, txt, (coords[0], coords[1] - 20), 0, 1, color, 2)

            cv2.imshow('PiArchitect Modular System', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

    finally:
        cap.release()
        comms.cerrar()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()