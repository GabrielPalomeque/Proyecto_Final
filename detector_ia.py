import cv2
import numpy as np
import platform

class DetectorRoboflow:
    def __init__(self, modelo_path, etiquetas, umbral=0.6):
        self.modelo_path = modelo_path
        self.etiquetas = etiquetas
        self.umbral = umbral
        self.interpreter = None
        self.input_shape = (320, 320) # Default por seguridad

        self._cargar_motor()

    def _cargar_motor(self):
        sistema = platform.system()
        try:
            if sistema == 'Windows':
                import tensorflow as tf
                Interpreter = tf.lite.Interpreter
            else:
                from tflite_runtime.interpreter import Interpreter
            
            self.interpreter = Interpreter(model_path=self.modelo_path)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self.input_shape = self.input_details[0]['shape']
            print(f"🧠 [IA] Modelo cargado. Input: {self.input_shape}")
            
        except ImportError:
            print("⚠️ [IA] Librerías TensorFlow no encontradas.")
        except Exception as e:
            print(f"⚠️ [IA] Error cargando modelo: {e}")

    def detectar(self, frame_rgb):
        """Retorna lista de tuplas: (caja, nombre, score)"""
        if not self.interpreter: return []

        # Preprocesamiento
        h, w = self.input_shape[1], self.input_shape[2]
        img_resized = cv2.resize(frame_rgb, (w, h))
        input_data = np.expand_dims(img_resized, axis=0)

        if self.input_details[0]['dtype'] == np.float32:
            input_data = (np.float32(input_data) - 127.5) / 127.5

        # Inferencia
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()

        # Resultados
        boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]

        resultados = []
        for i in range(len(scores)):
            if scores[i] > self.umbral:
                idx = int(classes[i])
                if idx < len(self.etiquetas):
                    resultados.append((boxes[i], self.etiquetas[idx], scores[i]))
        
        return resultados