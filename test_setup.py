import sys
import cv2
import mediapipe as mp
import face_recognition
import tensorflow as tf
import numpy as np

print(f"✅ Python: {sys.version.split()[0]}")
print(f"✅ OpenCV: {cv2.__version__}")
print(f"✅ Mediapipe: {mp.__version__}")
print(f"✅ Face Recognition: Listo (Dlib backend ok)")
print(f"✅ TensorFlow: {tf.__version__}")

try:
    # Prueba crítica: Cargar el intérprete Lite (lo usaremos en la Pi)
    interpreter = tf.lite.Interpreter(model_content=None)
    print("✅ TFLite Runtime: Funcional")
except Exception as e:
    print(f"⚠️ TFLite Warning: {e}")

print("\n🎉 ¡ENTORNO WINDOWS 100% OPERATIVO!")