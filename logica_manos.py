import math

def analizar_dedos(landmarks, etiqueta_mano):
    """
    Retorna lista binaria de dedos levantados [1,0,1,0,0].
    etiqueta_mano: 'Right' (Mano Izq Física) o 'Left' (Mano Der Física)
    """
    tips = [8, 12, 16, 20] # Índices de las puntas
    dedos = []
    
    # 1. Pulgar (Eje X) - Depende de la mano
    if etiqueta_mano == 'Right': 
        # Lógica para mano izquierda en espejo
        dedos.append(1 if landmarks[4].x < landmarks[3].x else 0)
    else: 
        # Lógica para mano derecha en espejo
        dedos.append(1 if landmarks[4].x > landmarks[3].x else 0)

    # 2. Otros dedos (Eje Y) - Arriba es menor valor
    for id in tips:
        dedos.append(1 if landmarks[id].y < landmarks[id - 2].y else 0)
    
    return dedos

def identificar_letra_mano(dedos, landmarks):
    """Retorna 'LETRA_L', 'LETRA_V', 'LETRA_O' o None"""
    
    # Geometría para la 'O' (Distancia Pulgar-Índice)
    dist = math.hypot(landmarks[8].x - landmarks[4].x, landmarks[8].y - landmarks[4].y)
    if dist < 0.05: return "LETRA_O"
    
    # Patrones de dedos
    if dedos == [1, 1, 0, 0, 0]: return "LETRA_L"
    if dedos == [0, 1, 1, 0, 0] or dedos == [1, 1, 1, 0, 0]: return "LETRA_V"
    
    return None